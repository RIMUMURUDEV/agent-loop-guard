from __future__ import annotations

from typing import Any

from app.core.loop_detector import error_fingerprint, request_fingerprint, tool_call_fingerprints
from app.core.policy_engine import PolicyDecision, evaluate
from app.core.redaction import safe_preview
from app.core.token_meter import usage_or_estimate
from app.db.models import Agent, GuardSession
from app.db.repository import Repository


def _body_for(scenario: str, index: int) -> dict[str, Any]:
    if scenario == "normal":
        return {"model": "demo-model", "input": f"Write a short unique demo line {index}."}
    if scenario == "tool-loop":
        return {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "Inspect the same file again."}],
            "tool_calls": [{"tool_name": "read_file", "arguments": {"path": "README.md"}}],
        }
    if scenario == "error-retry":
        return {
            "model": "demo-model",
            "messages": [{"role": "user", "content": "Retry the failing upstream call."}],
            "mock_status": 500,
            "mock_error": "deterministic demo failure",
        }
    if scenario == "streaming":
        return {"model": "demo-model", "input": f"Stream demo chunk {index}.", "stream": True}
    return {"model": "demo-model", "input": "Repeat this exact request."}


def _event(repo: Repository, session: GuardSession, request_id: str, decision: PolicyDecision) -> None:
    if decision.reason_code:
        repo.event(
            session.id,
            request_id,
            "policy_triggered",
            "error" if decision.blocked else "warning",
            decision.reason_code,
            decision.mode,
            decision.details or {},
            decision.rule_id,
        )


def run_demo(repo: Repository, agent: Agent, scenario: str, mode: str) -> GuardSession:
    scenario = scenario if scenario in {"normal", "exact-loop", "tool-loop", "error-retry", "streaming"} else "exact-loop"
    count = {"normal": 12, "error-retry": 5, "streaming": 3}.get(scenario, 3)
    session = repo.get_or_create_session(agent.project_id, agent.id, f"demo-{scenario}", 0)
    if session.status == "paused":
        session.status = "active"
    policies = repo.policies(agent.project_id)
    previous_error: tuple[str | None, int] = (None, 0)

    for index in range(count):
        body = _body_for(scenario, index)
        req_fp = request_fingerprint(body)
        tools = tool_call_fingerprints(body)
        decision = evaluate(
            mode=mode,
            session=session,
            agent=agent,
            policies=policies,
            request_fp=req_fp,
            tool_fps=[f"{name}:{args_hash}" for name, args_hash in tools],
            recent_request_fps=repo.recent_request_fingerprints(session.id, 30),
            recent_tool_fps=repo.recent_tool_fingerprints(session.id, 30),
            last_error_count=repo.consecutive_error_count(session.id)[1],
        )
        status = 500 if scenario == "error-retry" else decision.http_status if decision.blocked else 200
        response: dict[str, Any] = {"ok": status < 400, "demo": scenario, "index": index}
        err_fp = None
        if scenario == "error-retry":
            response = {"error": {"type": "mock_error", "message": "deterministic demo failure"}}
            err_fp = error_fingerprint(status, response)
            previous_fp, previous_count = previous_error
            current_count = previous_count + 1 if previous_fp == err_fp else 1
            previous_error = (err_fp, current_count)
            if current_count >= 5 and not decision.reason_code:
                decision = PolicyDecision(
                    decision="shadow_flag",
                    mode=mode,
                    reason_code="LOOP_ERROR_RETRY",
                    rule_id="rule_error_retry",
                    message="The same upstream error repeated consecutively.",
                    details={"count": current_count, "threshold": 5, "fingerprint": err_fp},
                )
        record = repo.record_request(
            session=session,
            protocol="openai",
            endpoint="/api/demo/run",
            model=str(body.get("model")),
            fingerprint=req_fp,
            status=status,
            latency_ms=1,
            tokens=usage_or_estimate("openai", body, response),
            decision=decision.decision,
            reason_code=decision.reason_code,
            request_preview=safe_preview(body, False),
            response_preview=safe_preview(response, False),
            tool_calls=tools,
            error_fingerprint=err_fp,
        )
        _event(repo, session, record.id, decision)
        session = repo.get_session(session.id) or session
    return session

