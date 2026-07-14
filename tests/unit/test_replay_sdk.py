from __future__ import annotations

from typing import Any

import httpx

from app.replay.sdk import ReplayClient


def test_sdk_builds_nested_trace_and_redacts_before_transport(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs):
        captured["url"] = url
        captured["payload"] = kwargs["json"]
        return httpx.Response(200, json={"run": {"id": kwargs["json"]["trace_id"]}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    client = ReplayClient("http://localhost:8787")

    with client.trace(project_id="demo", api_key="sk-abcdefghijklmnopqrstuvwxyz") as trace:
        with trace.span("tool.call", tool_name="read_file") as span:
            span.event("file.change", path="README.md")

    assert captured["url"].endswith("/api/v1/traces")
    assert captured["payload"]["attributes"]["api_key"] == "[REDACTED]"
    assert captured["payload"]["spans"][0]["events"][0]["name"] == "file.change"
    assert trace.result["run"]["id"] == trace.trace_id
