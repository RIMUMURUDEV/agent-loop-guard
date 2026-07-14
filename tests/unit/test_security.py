from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.security import bearer_token, external_session_id, filtered_upstream_headers


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        }
    )


def test_bearer_and_api_key_authentication() -> None:
    assert bearer_token(_request({"Authorization": "Bearer token-value"})) == "token-value"
    assert bearer_token(_request({"x-api-key": " api-value "})) == "api-value"
    assert bearer_token(_request({"api-key": "fallback"})) == "fallback"


def test_missing_authentication_has_structured_error() -> None:
    with pytest.raises(HTTPException) as raised:
        bearer_token(_request({}))

    assert raised.value.status_code == 401
    assert raised.value.detail["error"]["type"] == "agent_loop_guard_auth"


def test_external_session_header_precedence() -> None:
    assert external_session_id(_request({"x-alg-session-id": " alg "}), "anthropic") == "alg"
    assert (
        external_session_id(_request({"x-claude-code-session-id": " claude "}), "anthropic")
        == "claude"
    )
    assert external_session_id(_request({"x-claude-code-session-id": "claude"}), "openai") is None


def test_filtered_headers_remove_credentials_internal_and_hop_by_hop_values() -> None:
    filtered = filtered_upstream_headers(
        {
            "Host": "local",
            "Connection": "keep-alive",
            "Authorization": "Bearer secret",
            "x-api-key": "secret",
            "x-alg-session-id": "internal",
            "User-Agent": "agent-test",
            "Accept": "application/json",
        }
    )

    assert filtered == {"User-Agent": "agent-test", "Accept": "application/json"}
