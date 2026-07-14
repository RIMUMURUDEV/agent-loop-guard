from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import bearer_token, filtered_upstream_headers
from app.db.repository import (
    Repository,
    mcp_approval_dict,
    mcp_event_dict,
    mcp_server_dict,
)
from app.db.session import get_db
from app.mcp.gateway import MCPGateway, jsonrpc_error, mock_response
from app.mcp.policy import MCPPolicyEngine, validate_policy

router = APIRouter()


class ApprovalDecision(BaseModel):
    action: str
    scope: str = "once"


class PolicyValidation(BaseModel):
    policy: dict[str, Any]


def _authenticate(repo: Repository, request: Request) -> None:
    if repo.agent_for_key(bearer_token(request)) is None:
        raise HTTPException(403, "Invalid gateway key.")


def _valid_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    for allowed in request.app.state.config.mcp_allowed_origins:
        if origin == allowed or origin.startswith(allowed.rstrip("/") + ":"):
            return True
    return False


def _gateway(request: Request, db: Session, server_id: str) -> tuple[Repository, MCPGateway]:
    repo = Repository(db)
    server = repo.mcp_server(server_id)
    if server is None or not server.enabled:
        raise HTTPException(404, "MCP server not found.")
    policy = MCPPolicyEngine(request.app.state.config.mcp_policy_path)
    session_id = request.headers.get("mcp-session-id")
    gateway = MCPGateway(
        repo,
        policy,
        server_id,
        session_id=session_id,
        approval_timeout_seconds=request.app.state.config.mcp_approval_timeout_seconds,
    )
    return repo, gateway


@router.api_route("/mcp/{server_id}", methods=["GET", "DELETE"])
async def mcp_stream(server_id: str, request: Request, db: Session = Depends(get_db)):
    repo, gateway = _gateway(request, db, server_id)
    _authenticate(repo, request)
    if not _valid_origin(request):
        return Response(status_code=403)
    if request.method == "DELETE":
        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            return Response(status_code=404)
        server = repo.mcp_server(server_id)
        assert server is not None
        upstream_session = request.app.state.mcp_upstream_sessions.pop(session_id, None)
        if server.transport != "mock" and not server.target.startswith("mock://"):
            headers = filtered_upstream_headers(dict(request.headers))
            if upstream_session:
                headers["mcp-session-id"] = upstream_session
            async with httpx.AsyncClient(timeout=15) as client:
                await client.delete(server.target, headers=headers)
        if repo.end_mcp_session(session_id) is None:
            return Response(status_code=404)
        return Response(status_code=204)

    server = repo.mcp_server(server_id)
    assert server is not None
    if server.transport != "mock" and not server.target.startswith("mock://"):
        headers = filtered_upstream_headers(dict(request.headers))
        if gateway.session_id:
            upstream_session = request.app.state.mcp_upstream_sessions.get(gateway.session_id)
            if upstream_session:
                headers["mcp-session-id"] = upstream_session

        async def upstream_events():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", server.target, headers=headers) as upstream:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk

        return StreamingResponse(upstream_events(), media_type="text/event-stream")

    async def ping():
        yield "event: ping\ndata:\n\n"

    return StreamingResponse(ping(), media_type="text/event-stream")


@router.post("/mcp/{server_id}")
async def mcp_post(server_id: str, request: Request, db: Session = Depends(get_db)):
    repo, gateway = _gateway(request, db, server_id)
    _authenticate(repo, request)
    if not _valid_origin(request):
        return Response(status_code=403)
    try:
        message = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(jsonrpc_error(None, -32700, "Parse error"), status_code=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return JSONResponse(jsonrpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request"), status_code=400)

    method = message.get("method")
    if method != "initialize" and not gateway.session_id:
        return JSONResponse(jsonrpc_error(message.get("id"), -32001, "MCP-Session-Id is required"), status_code=400)
    if method == "initialize":
        params = message.get("params") or {}
        client = params.get("clientInfo") or {}
        gateway.ensure_session(
            client_name=str(client.get("name") or "unknown"),
            protocol_version=str(params.get("protocolVersion") or "2025-11-25"),
        )

    interception = gateway.intercept(message)
    if not interception.forward:
        return JSONResponse(interception.response or {}, headers={"MCP-Session-Id": gateway.session_id or ""})

    server = repo.mcp_server(server_id)
    assert server is not None
    if server.transport == "mock" or server.target.startswith("mock://"):
        response_message = mock_response(interception.message)
        if response_message is None:
            return Response(status_code=202)
        if method == "tools/list":
            response_message = gateway.filter_tools(response_message)
        return JSONResponse(response_message, headers={"MCP-Session-Id": gateway.session_id or ""})

    headers = filtered_upstream_headers(dict(request.headers))
    headers["accept"] = "application/json, text/event-stream"
    if gateway.session_id and method != "initialize":
        upstream_session = request.app.state.mcp_upstream_sessions.get(gateway.session_id)
        if upstream_session:
            headers["mcp-session-id"] = upstream_session
    async with httpx.AsyncClient(timeout=60) as client:
        upstream = await client.post(server.target, json=interception.message, headers=headers)
    content_type = upstream.headers.get("content-type", "application/json")
    if "application/json" not in content_type:
        return Response(upstream.content, status_code=upstream.status_code, media_type=content_type)
    response_message = upstream.json()
    if method == "initialize" and gateway.session_id:
        upstream_session = upstream.headers.get("mcp-session-id")
        if upstream_session:
            request.app.state.mcp_upstream_sessions[gateway.session_id] = upstream_session
    if method == "tools/list" and isinstance(response_message, dict):
        response_message = gateway.filter_tools(response_message)
    response_headers = {}
    if gateway.session_id:
        response_headers["MCP-Session-Id"] = gateway.session_id
    return JSONResponse(response_message, status_code=upstream.status_code, headers=response_headers)


@router.get("/api/v1/mcp/servers")
def mcp_servers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [mcp_server_dict(item) for item in Repository(db).list_mcp_servers()]


@router.get("/api/v1/mcp/events")
def mcp_events(limit: int = 200, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [mcp_event_dict(item) for item in Repository(db).list_mcp_events(min(limit, 1000))]


@router.get("/api/v1/mcp/approvals")
def mcp_approvals(pending: bool = False, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [mcp_approval_dict(item) for item in Repository(db).list_mcp_approvals(pending)]


@router.post("/api/v1/mcp/approvals/{approval_id}")
def decide_mcp_approval(
    approval_id: str, payload: ApprovalDecision, db: Session = Depends(get_db)
) -> dict[str, Any]:
    if payload.action not in {"allow", "deny"}:
        raise HTTPException(422, "action must be allow or deny")
    approval = Repository(db).decide_mcp_approval(approval_id, payload.action, payload.scope)
    if approval is None:
        raise HTTPException(404, "Approval is missing, expired, or already decided.")
    return mcp_approval_dict(approval)


@router.post("/api/v1/mcp/policies/validate")
def validate_mcp_policy(payload: PolicyValidation) -> dict[str, Any]:
    errors = validate_policy(payload.policy)
    return {"valid": not errors, "errors": errors}


@router.get("/api/v1/mcp/export")
def export_mcp_events(db: Session = Depends(get_db)) -> JSONResponse:
    repo = Repository(db)
    return JSONResponse(
        {
            "schema_version": "mcp.audit.v1",
            "servers": [mcp_server_dict(item) for item in repo.list_mcp_servers()],
            "events": [mcp_event_dict(item) for item in repo.list_mcp_events(10000)],
            "approvals": [mcp_approval_dict(item) for item in repo.list_mcp_approvals()],
        }
    )
