from __future__ import annotations

from fastapi import HTTPException, Request


def bearer_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    api_key = request.headers.get("x-api-key") or request.headers.get("api-key")
    if api_key:
        return api_key.strip()
    raise HTTPException(
        status_code=401,
        detail={"error": {"type": "agent_loop_guard_auth", "message": "Missing gateway key."}},
    )


def external_session_id(request: Request, protocol: str) -> str | None:
    explicit = request.headers.get("x-alg-session-id")
    if explicit:
        return explicit.strip()
    if protocol == "anthropic":
        claude_id = request.headers.get("x-claude-code-session-id")
        if claude_id:
            return claude_id.strip()
    return None


def filtered_upstream_headers(headers: dict[str, str]) -> dict[str, str]:
    hop_by_hop = {
        "host",
        "content-length",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
    result: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in hop_by_hop:
            continue
        if lower.startswith("x-alg-"):
            continue
        if lower in {"authorization", "x-api-key", "api-key"}:
            continue
        result[key] = value
    return result

