from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppConfig
from app.main import create_app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    config = AppConfig(
        storage_url="sqlite:///:memory:",
        default_provider="mock",
        gateway_key="alg_test_key",
        admin_ui=True,
    )
    with TestClient(create_app(config)) as test_client:
        yield test_client


def _headers(session_id: str = "test-session", mode: str | None = None) -> dict[str, str]:
    headers = {"authorization": "Bearer alg_test_key", "x-alg-session-id": session_id}
    if mode:
        headers["x-alg-mode"] = mode
    return headers


def test_exact_repeat_flags_third_request_in_shadow(client: TestClient) -> None:
    body = {"model": "demo-model", "input": "repeat me"}
    decisions = []
    for _ in range(3):
        response = client.post("/v1/responses", json=body, headers=_headers("exact-shadow"))
        assert response.status_code == 200
        decisions.append(response.headers["x-alg-decision"])
    assert decisions == ["allow", "allow", "shadow_flag"]
    assert response.headers["x-alg-reason"] == "LOOP_EXACT"


def test_enforce_blocks_third_exact_repeat(client: TestClient) -> None:
    body = {"model": "demo-model", "input": "stop me"}
    for _ in range(2):
        assert client.post("/v1/responses", json=body, headers=_headers("exact-enforce", "enforce")).status_code == 200
    blocked = client.post("/v1/responses", json=body, headers=_headers("exact-enforce", "enforce"))
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "LOOP_EXACT"


def test_repeated_tool_call_is_detected(client: TestClient) -> None:
    for index in range(3):
        body = {
            "model": "demo-model",
            "messages": [{"role": "user", "content": f"call tool {index}"}],
            "tool_calls": [{"tool_name": "read_file", "arguments": {"path": "README.md"}}],
        }
        response = client.post("/v1/chat/completions", json=body, headers=_headers("tool-shadow"))
    assert response.headers["x-alg-reason"] == "LOOP_TOOL_CALL"


def test_streaming_response_records_after_chunks_are_read(client: TestClient) -> None:
    body = {"model": "demo-model", "messages": [{"role": "user", "content": "stream"}], "stream": True}
    with client.stream("POST", "/v1/chat/completions", json=body, headers=_headers("stream")) as response:
        payload = b"".join(response.iter_bytes())
    assert response.status_code == 200
    assert b"data:" in payload
    sessions = client.get("/api/sessions").json()
    stream_session = next(item for item in sessions if item["external_session_id"] == "stream")
    assert stream_session["request_count"] == 1


def test_anthropic_messages_and_count_tokens(client: TestClient) -> None:
    headers = _headers("anthropic")
    body = {
        "model": "demo-model",
        "messages": [{"role": "user", "content": "hello anthropic"}],
    }
    response = client.post("/v1/messages", json=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["type"] == "message"
    counted = client.post("/v1/messages/count_tokens", json=body, headers=headers)
    assert counted.status_code == 200
    assert counted.json()["input_tokens"] > 0


def test_repeated_upstream_error_is_detected(client: TestClient) -> None:
    headers = _headers("error-retry")
    for index in range(5):
        body = {
            "model": "demo-model",
            "input": f"retry failing call {index}",
            "mock_status": 500,
            "mock_error": "stable failure",
        }
        response = client.post("/v1/responses", json=body, headers=headers)
    assert response.status_code == 500
    assert response.headers["x-alg-decision"] == "shadow_flag"
    assert response.headers["x-alg-reason"] == "LOOP_ERROR_RETRY"


def test_manual_session_pause_blocks_next_request(client: TestClient) -> None:
    response = client.post("/v1/responses", json={"model": "demo-model", "input": "first"}, headers=_headers("pause-me"))
    assert response.status_code == 200
    session = next(item for item in client.get("/api/sessions").json() if item["external_session_id"] == "pause-me")
    client.post(f"/api/sessions/{session['id']}/pause")
    blocked = client.post("/v1/responses", json={"model": "demo-model", "input": "second"}, headers=_headers("pause-me"))
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "SESSION_PAUSED"


def test_demo_and_export_do_not_leak_gateway_key(client: TestClient) -> None:
    demo = client.post("/api/demo/run", json={"scenario": "exact-loop", "mode": "shadow"})
    assert demo.status_code == 200
    session_id = demo.json()["session"]["id"]
    exported = client.get(f"/api/export/sessions/{session_id}.json")
    assert exported.status_code == 200
    text = exported.text
    assert '"schema_version":"1.0"' in text
    assert "alg_test_key" not in text


def test_models_endpoint_uses_local_mock_provider(client: TestClient) -> None:
    response = client.get("/v1/models", headers=_headers("models"))
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "demo-model"
