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


def test_playground_contract_and_ui(client: TestClient) -> None:
    scenarios = client.get("/api/v1/playground/scenarios")
    assert scenarios.status_code == 200
    assert {item["id"] for item in scenarios.json()} >= {"normal", "exact-loop", "tool-loop"}

    created = client.post(
        "/api/v1/playground/runs",
        json={"scenario": "tool-loop", "mode": "shadow"},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["schema_version"] == "playground.run.v1"
    assert payload["session"]["request_count"] == 3
    assert payload["trace"]["source_session_id"] == payload["id"]
    assert any(event["name"] == "tool.reference" for event in payload["trace_events"])

    fetched = client.get(f"/api/v1/playground/runs/{payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == payload["id"]

    page = client.get("/playground")
    assert page.status_code == 200
    assert "Agent Playground" in page.text
    assert "/api/v1/playground/runs" in page.text


def test_playground_rejects_unknown_scenario(client: TestClient) -> None:
    response = client.post(
        "/api/v1/playground/runs",
        json={"scenario": "unknown", "mode": "shadow"},
    )
    assert response.status_code == 422
