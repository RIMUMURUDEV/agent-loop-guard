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


def _headers(session_id: str = "trace-session") -> dict[str, str]:
    return {"authorization": "Bearer alg_test_key", "x-alg-session-id": session_id}


def test_trace_ingest_export_and_compare(client: TestClient) -> None:
    first = client.post(
        "/api/v1/traces",
        json={
            "trace_id": "trace_baseline",
            "task_id": "task-1",
            "agent_name": "mock-agent",
            "model": "demo-model",
            "attributes": {"api_key": "sk-1234567890abcdef"},
            "spans": [
                {
                    "span_id": "span_baseline_tool",
                    "name": "tool.call",
                    "start_ns": 1_000_000,
                    "end_ns": 3_000_000,
                    "attributes": {"tool.name": "read_file"},
                    "events": [{"name": "tool.result", "attributes": {"status": "ok"}}],
                }
            ],
        },
    )
    second = client.post(
        "/api/v1/traces",
        json={
            "trace_id": "trace_candidate",
            "task_id": "task-1",
            "agent_name": "mock-agent",
            "model": "demo-model",
            "spans": [
                {
                    "span_id": "span_candidate_tool",
                    "name": "tool.call",
                    "start_ns": 1_000_000,
                    "end_ns": 6_000_000,
                    "attributes": {"tool.name": "read_file"},
                }
            ],
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert {span["name"] for span in first.json()["spans"]} == {"agent.run", "tool.call"}

    runs = client.get("/api/v1/runs").json()
    assert {run["id"] for run in runs} >= {"trace_baseline", "trace_candidate"}

    exported = client.get("/api/v1/runs/trace_baseline/export")
    assert exported.status_code == 200
    assert "sk-1234567890abcdef" not in exported.text
    assert "[REDACTED]" in exported.text

    compared = client.post(
        "/api/v1/compare",
        json={"left_trace_id": "trace_baseline", "right_trace_id": "trace_candidate"},
    )
    assert compared.status_code == 200
    assert compared.json()["delta"]["duration_ms"] > 0


def test_proxy_requests_create_replay_trace(client: TestClient) -> None:
    response = client.post(
        "/v1/responses",
        json={"model": "demo-model", "input": "record this request"},
        headers=_headers(),
    )
    assert response.status_code == 200

    runs = client.get("/api/v1/runs").json()
    run = next(item for item in runs if item["source_session_id"])
    detail = client.get(f"/api/v1/runs/{run['id']}").json()
    span_names = {span["name"] for span in detail["spans"]}

    assert "agent.run" in span_names
    assert "gen_ai.request" in span_names
    assert detail["run"]["total_tokens"] > 0


def test_replay_ui_pages_render(client: TestClient) -> None:
    client.post(
        "/v1/responses",
        json={"model": "demo-model", "input": "show in replay ui"},
        headers=_headers("ui-trace"),
    )
    run = client.get("/api/v1/runs").json()[0]

    listing = client.get("/replay")
    detail = client.get(f"/replay/{run['id']}")

    assert listing.status_code == 200
    assert "Trace Runs" in listing.text
    assert detail.status_code == 200
    assert "Timeline" in detail.text


def test_replay_formats_pin_and_repeatable_import(client: TestClient) -> None:
    created = client.post(
        "/api/v1/traces",
        json={
            "trace_id": "trace_portable",
            "task_id": "portable-task",
            "spans": [
                {
                    "span_id": "portable_parent",
                    "name": "tool.call",
                    "start_ns": 10,
                    "end_ns": 20,
                    "events": [{"name": "file.change"}],
                },
                {
                    "span_id": "portable_child",
                    "parent_span_id": "portable_parent",
                    "name": "command.exec",
                    "start_ns": 12,
                    "end_ns": 18,
                },
            ],
        },
    )
    assert created.status_code == 200

    pinned = client.post("/api/v1/runs/trace_portable/pin", json={"pinned": True})
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True

    jsonl = client.get("/api/v1/runs/trace_portable/export?format=jsonl")
    assert jsonl.status_code == 200
    assert '"record_type": "run"' in jsonl.text

    otel = client.get("/api/v1/runs/trace_portable/export?format=otel")
    assert otel.status_code == 200
    otel_spans = otel.json()["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert all(len(span["traceId"]) == 32 for span in otel_spans)
    assert all(len(span["spanId"]) == 16 for span in otel_spans)

    bundle = created.json()
    first_import = client.post("/api/v1/runs/import", json={"bundle": bundle})
    second_import = client.post("/api/v1/runs/import", json={"bundle": bundle})
    assert first_import.status_code == 200
    assert second_import.status_code == 200
    assert first_import.json()["run"]["id"] != second_import.json()["run"]["id"]
    for imported in (first_import.json(), second_import.json()):
        span_ids = {span["id"] for span in imported["spans"]}
        assert all(
            span["parent_span_id"] is None or span["parent_span_id"] in span_ids
            for span in imported["spans"]
        )
        assert all(event["span_id"] in span_ids for event in imported["events"])
