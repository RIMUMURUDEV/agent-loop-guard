from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import AppConfig
from app.main import create_app


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    config = AppConfig(
        storage_url="sqlite:///:memory:",
        default_provider="mock",
        gateway_key="alg_test_key",
        admin_ui=True,
        mcp_policy_path=str(tmp_path / "missing-policy.yml"),
        mcp_approval_timeout_seconds=60,
    )
    with TestClient(create_app(config)) as test_client:
        yield test_client


def _headers(session_id: str | None = None, origin: str | None = None) -> dict[str, str]:
    headers = {
        "authorization": "Bearer alg_test_key",
        "accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
        headers["mcp-protocol-version"] = "2025-11-25"
    if origin:
        headers["origin"] = origin
    return headers


def _initialize(client: TestClient) -> str:
    response = client.post(
        "/mcp/filesystem",
        headers=_headers(),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "clientInfo": {"name": "pytest", "version": "1"},
                "capabilities": {},
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["protocolVersion"] == "2025-11-25"
    return response.headers["mcp-session-id"]


def test_mcp_discovery_filter_policy_and_approval_flow(client: TestClient) -> None:
    session_id = _initialize(client)
    listed = client.post(
        "/mcp/filesystem",
        headers=_headers(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names == {"read_file", "write_file"}

    read = client.post(
        "/mcp/filesystem",
        headers=_headers(session_id),
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "README.md"}},
        },
    )
    assert read.json()["result"]["isError"] is False

    write_body = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "write_file",
            "arguments": {"path": "notes.txt", "content": "hello"},
        },
    }
    pending = client.post("/mcp/filesystem", headers=_headers(session_id), json=write_body)
    approval_id = pending.json()["result"]["structuredContent"]["approval_id"]
    approved = client.post(
        f"/api/v1/mcp/approvals/{approval_id}", json={"action": "allow", "scope": "once"}
    )
    assert approved.status_code == 200

    retried = client.post("/mcp/filesystem", headers=_headers(session_id), json=write_body)
    assert retried.json()["result"]["isError"] is False

    events = client.get("/api/v1/mcp/events").json()
    assert {event["action"] for event in events} >= {"allow", "confirm"}
    assert all(event["trace_id"] for event in events)


def test_mcp_rejects_origin_spoofing_and_path_traversal(client: TestClient) -> None:
    rejected = client.post(
        "/mcp/filesystem",
        headers=_headers(origin="https://evil.example"),
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert rejected.status_code == 403

    session_id = _initialize(client)
    blocked = client.post(
        "/mcp/filesystem",
        headers=_headers(session_id),
        json={
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "../secret.txt"}},
        },
    )
    assert blocked.json()["result"]["isError"] is True
    assert blocked.json()["result"]["structuredContent"]["action"] == "deny"


def test_mcp_schema_validation_and_ui(client: TestClient) -> None:
    session_id = _initialize(client)
    client.post(
        "/mcp/filesystem",
        headers=_headers(session_id),
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    invalid = client.post(
        "/mcp/filesystem",
        headers=_headers(session_id),
        json={
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {}},
        },
    )
    assert invalid.json()["result"]["isError"] is True
    assert client.get("/mcp").status_code == 200
