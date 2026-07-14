from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import AppConfig
from app.core.loop_detector import (
    error_fingerprint,
    request_fingerprint,
    tool_call_fingerprints,
)
from app.core.policy_engine import MESSAGE_BY_REASON, PolicyDecision, evaluate
from app.core.redaction import safe_json_bytes, safe_preview
from app.core.security import bearer_token, external_session_id
from app.core.token_meter import estimate_tokens, usage_or_estimate
from app.db.models import Agent, GuardSession, Policy, Project
from app.db.repository import Repository, new_id
from app.providers import MockProvider, ProviderResult, ProviderStream, UpstreamProvider


def _incoming_headers(request: Request) -> dict[str, str]:
    return {key: value for key, value in request.headers.items()}


async def read_json_body(request: Request, config: AppConfig) -> tuple[bytes, dict[str, Any]]:
    raw = await request.body()
    if len(raw) > config.body_limit_bytes:
        raise HTTPException(status_code=413, detail={"error": "Request body too large."})
    if not raw:
        return raw, {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={"error": "Malformed JSON body."}) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail={"error": "JSON body must be an object."})
    return raw, parsed


def mode_for_request(request: Request, config: AppConfig, project: Project) -> str:
    mode = project.mode or config.default_mode
    if config.allow_mode_header:
        requested = request.headers.get("x-alg-mode")
        if requested in {"shadow", "enforce"}:
            mode = requested
    return "enforce" if mode == "enforce" else "shadow"


def provider_for(project: Project, config: AppConfig, protocol: str):
    if (project.provider or config.default_provider) == "mock":
        return MockProvider()
    if protocol == "anthropic":
        return UpstreamProvider(
            base_url=config.anthropic_base_url,
            api_key=config.anthropic_api_key,
            protocol="anthropic",
        )
    return UpstreamProvider(
        base_url=config.openai_base_url,
        api_key=config.openai_api_key,
        protocol="openai",
    )


def response_headers(base: dict[str, str], decision: PolicyDecision, request_id: str) -> dict[str, str]:
    headers = dict(base)
    headers["x-alg-request-id"] = request_id
    headers["x-alg-decision"] = decision.decision
    if decision.reason_code:
        headers["x-alg-reason"] = decision.reason_code
    return headers


def _block_payload(decision: PolicyDecision, session: GuardSession) -> dict[str, Any]:
    return {
        "error": {
            "type": "agent_loop_guard_block",
            "code": decision.reason_code,
            "message": decision.message,
            "session_id": session.id,
            "rule_id": decision.rule_id,
        }
    }


def block_response(decision: PolicyDecision, session: GuardSession, request_id: str) -> JSONResponse:
    payload = _block_payload(decision, session)
    return JSONResponse(
        payload,
        status_code=decision.http_status,
        headers=response_headers({}, decision, request_id),
    )


def _record_policy_event(repo: Repository, record_id: str | None, session_id: str, decision: PolicyDecision) -> None:
    if not decision.reason_code:
        return
    repo.event(
        session_id,
        record_id,
        "policy_triggered",
        "error" if decision.blocked else "warning",
        decision.reason_code,
        decision.mode,
        decision.details or {},
        decision.rule_id,
    )


def _policies_by_type(policies: list[Policy]) -> dict[str, Policy]:
    return {policy.rule_type: policy for policy in policies if policy.enabled}


def _post_error_decision(
    *,
    mode: str,
    policies: list[Policy],
    error_fp: str | None,
    previous_error: tuple[str | None, int],
) -> PolicyDecision | None:
    if not error_fp:
        return None
    policy = _policies_by_type(policies).get("error_retry")
    if policy is None:
        return None
    previous_fp, previous_count = previous_error
    count = previous_count + 1 if previous_fp == error_fp else 1
    if count < policy.threshold:
        return None
    return PolicyDecision(
        decision="shadow_flag",
        mode=mode,
        reason_code="LOOP_ERROR_RETRY",
        rule_id=policy.id,
        message=MESSAGE_BY_REASON["LOOP_ERROR_RETRY"],
        details={"count": count, "threshold": policy.threshold, "fingerprint": error_fp},
        http_status=200,
    )


def _preview_response(result: ProviderResult, config: AppConfig) -> str:
    if result.json_body is not None:
        return safe_preview(result.json_body, config.full_content_logging)
    if config.full_content_logging:
        return safe_json_bytes(result.content)
    return safe_preview(
        {"bytes": len(result.content), "content_type": result.media_type or "unknown"},
        full_content_logging=False,
    )


def _model_from_body(body: dict[str, Any]) -> str | None:
    model = body.get("model")
    return str(model) if model is not None else None


def _tool_policy_fps(tool_calls: list[tuple[str, str]]) -> list[str]:
    return [f"{name}:{args_hash}" for name, args_hash in tool_calls]


def _authenticate(repo: Repository, request: Request) -> Agent:
    raw_key = bearer_token(request)
    agent = repo.agent_for_key(raw_key)
    if agent is None:
        raise HTTPException(
            status_code=403,
            detail={"error": {"type": "agent_loop_guard_auth", "message": "Invalid gateway key."}},
        )
    return agent


def _project(repo: Repository, request: Request, agent: Agent) -> Project:
    requested = request.headers.get("x-alg-project-id")
    project_id = requested.strip() if requested else agent.project_id
    project = repo.project(project_id)
    if project is None or project.id != agent.project_id:
        raise HTTPException(
            status_code=403,
            detail={"error": {"type": "agent_loop_guard_auth", "message": "Project is not available."}},
        )
    return project


def _initial_decision(
    *,
    mode: str,
    repo: Repository,
    session: GuardSession,
    agent: Agent,
    policies: list[Policy],
    body: dict[str, Any],
    req_fp: str,
    tool_fps: list[str],
) -> PolicyDecision:
    return evaluate(
        mode=mode,
        session=session,
        agent=agent,
        policies=policies,
        request_fp=req_fp,
        tool_fps=tool_fps,
        recent_request_fps=repo.recent_request_fingerprints(session.id, limit=30),
        recent_tool_fps=repo.recent_tool_fingerprints(session.id, limit=30),
        last_error_count=repo.consecutive_error_count(session.id)[1],
    )


def _final_decision(
    *,
    current: PolicyDecision,
    mode: str,
    policies: list[Policy],
    error_fp: str | None,
    previous_error: tuple[str | None, int],
) -> PolicyDecision:
    if current.reason_code:
        return current
    error_decision = _post_error_decision(
        mode=mode, policies=policies, error_fp=error_fp, previous_error=previous_error
    )
    return error_decision or current


def _record_request(
    *,
    repo: Repository,
    session: GuardSession,
    protocol: str,
    endpoint: str,
    model: str | None,
    req_fp: str,
    status: int,
    latency_ms: int,
    tokens: dict[str, int | bool],
    decision: PolicyDecision,
    request_preview: str | None,
    response_preview: str | None,
    tool_calls: list[tuple[str, str]],
    error_fp: str | None,
) -> None:
    record = repo.record_request(
        session=session,
        protocol=protocol,
        endpoint=endpoint,
        model=model,
        fingerprint=req_fp,
        status=status,
        latency_ms=latency_ms,
        tokens=tokens,
        decision=decision.decision,
        reason_code=decision.reason_code,
        request_preview=request_preview,
        response_preview=response_preview,
        tool_calls=tool_calls,
        error_fingerprint=error_fp,
    )
    _record_policy_event(repo, record.id, session.id, decision)


async def guarded_proxy(request: Request, db: Session, protocol: str, endpoint: str) -> Response:
    config: AppConfig = request.app.state.config
    request_id = new_id("algreq")
    raw_body, body = await read_json_body(request, config)
    repo = Repository(db)
    agent = _authenticate(repo, request)
    project = _project(repo, request, agent)
    session = repo.get_or_create_session(
        project.id,
        agent.id,
        external_session_id(request, protocol),
        config.inactive_timeout_seconds,
    )
    mode = mode_for_request(request, config, project)
    policies = repo.policies(project.id)
    req_fp = request_fingerprint(body)
    tool_calls = tool_call_fingerprints(body)
    tool_fps = _tool_policy_fps(tool_calls)
    decision = _initial_decision(
        mode=mode,
        repo=repo,
        session=session,
        agent=agent,
        policies=policies,
        body=body,
        req_fp=req_fp,
        tool_fps=tool_fps,
    )
    request_preview = safe_preview(body, config.full_content_logging)

    if decision.blocked:
        payload = _block_payload(decision, session)
        _record_request(
            repo=repo,
            session=session,
            protocol=protocol,
            endpoint=endpoint,
            model=_model_from_body(body),
            req_fp=req_fp,
            status=decision.http_status,
            latency_ms=0,
            tokens=usage_or_estimate(protocol, body, payload),
            decision=decision,
            request_preview=request_preview,
            response_preview=safe_preview(payload, config.full_content_logging),
            tool_calls=tool_calls,
            error_fp=None,
        )
        return block_response(decision, session, request_id)

    provider = provider_for(project, config, protocol)
    wants_stream = bool(body.get("stream"))
    if wants_stream:
        if isinstance(provider, MockProvider):
            stream = await provider.stream(protocol, endpoint, body)
        else:
            stream = await provider.stream(endpoint, raw_body, _incoming_headers(request))
        return streaming_response(
            request=request,
            stream=stream,
            protocol=protocol,
            endpoint=endpoint,
            body=body,
            session_id=session.id,
            model=_model_from_body(body),
            req_fp=req_fp,
            decision=decision,
            policies=policies,
            previous_error=repo.consecutive_error_count(session.id),
            request_preview=request_preview,
            tool_calls=tool_calls,
            started_at=time.perf_counter(),
            request_id=request_id,
        )

    started_at = time.perf_counter()
    if isinstance(provider, MockProvider):
        result = await provider.request(protocol, endpoint, body)
    else:
        result = await provider.request(endpoint, raw_body, _incoming_headers(request))
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    err_fp = error_fingerprint(result.status_code, result.json_body or result.content.decode("utf-8", "replace")) if result.status_code >= 400 else None
    final = _final_decision(
        current=decision,
        mode=mode,
        policies=policies,
        error_fp=err_fp,
        previous_error=repo.consecutive_error_count(session.id),
    )
    _record_request(
        repo=repo,
        session=session,
        protocol=protocol,
        endpoint=endpoint,
        model=_model_from_body(body),
        req_fp=req_fp,
        status=result.status_code,
        latency_ms=latency_ms,
        tokens=usage_or_estimate(protocol, body, result.json_body),
        decision=final,
        request_preview=request_preview,
        response_preview=_preview_response(result, config),
        tool_calls=tool_calls,
        error_fp=err_fp,
    )
    return Response(
        content=result.content,
        status_code=result.status_code,
        headers=response_headers(result.headers, final, request_id),
        media_type=result.media_type,
    )


def streaming_response(
    *,
    request: Request,
    stream: ProviderStream,
    protocol: str,
    endpoint: str,
    body: dict[str, Any],
    session_id: str,
    model: str | None,
    req_fp: str,
    decision: PolicyDecision,
    policies: list[Policy],
    previous_error: tuple[str | None, int],
    request_preview: str | None,
    tool_calls: list[tuple[str, str]],
    started_at: float,
    request_id: str,
) -> StreamingResponse:
    config: AppConfig = request.app.state.config
    session_factory = request.app.state.SessionLocal

    async def iterator() -> AsyncIterator[bytes]:
        total_bytes = 0
        preview = bytearray()
        try:
            async for chunk in stream.chunks:
                total_bytes += len(chunk)
                if len(preview) < 1000:
                    preview.extend(chunk[: 1000 - len(preview)])
                yield chunk
        finally:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            preview_text = bytes(preview).decode("utf-8", "replace")
            err_fp = error_fingerprint(stream.status_code, preview_text) if stream.status_code >= 400 else None
            final = _final_decision(
                current=decision,
                mode=decision.mode,
                policies=policies,
                error_fp=err_fp,
                previous_error=previous_error,
            )
            tokens = {
                "input_tokens": estimate_tokens(body),
                "output_tokens": max(1, (total_bytes + 3) // 4),
                "total_tokens": estimate_tokens(body) + max(1, (total_bytes + 3) // 4),
                "estimated": True,
            }
            response_preview = (
                safe_json_bytes(bytes(preview))
                if config.full_content_logging
                else safe_preview({"stream_bytes": total_bytes, "status": stream.status_code}, False)
            )
            with session_factory() as db:
                repo = Repository(db)
                session = repo.get_session(session_id)
                if session is not None:
                    _record_request(
                        repo=repo,
                        session=session,
                        protocol=protocol,
                        endpoint=endpoint,
                        model=model,
                        req_fp=req_fp,
                        status=stream.status_code,
                        latency_ms=latency_ms,
                        tokens=tokens,
                        decision=final,
                        request_preview=request_preview,
                        response_preview=response_preview,
                        tool_calls=tool_calls,
                        error_fp=err_fp,
                    )

    return StreamingResponse(
        iterator(),
        status_code=stream.status_code,
        headers=response_headers(stream.headers, decision, request_id),
        media_type=stream.media_type,
    )
