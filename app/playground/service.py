from __future__ import annotations

from typing import Any

from app.core.demo import run_demo
from app.db.repository import (
    Repository,
    event_dict,
    request_dict,
    session_dict,
    trace_event_dict,
    trace_run_dict,
    trace_span_dict,
)

SCENARIOS = [
    {
        "id": "normal",
        "name": "Normal request flow",
        "description": "Unique requests pass without loop findings.",
        "signals": ["requests", "tokens", "replay"],
    },
    {
        "id": "exact-loop",
        "name": "Exact request loop",
        "description": "The same model request repeats until the guard flags or blocks it.",
        "signals": ["requests", "policy.decision", "loop", "replay"],
    },
    {
        "id": "tool-loop",
        "name": "Repeated tool call",
        "description": "An agent repeatedly reads the same path with identical arguments.",
        "signals": ["tool.call", "policy.decision", "loop", "replay"],
    },
    {
        "id": "error-retry",
        "name": "Upstream error retry",
        "description": "A deterministic upstream error repeats until it becomes a failure tag.",
        "signals": ["requests", "errors", "policy.decision", "replay"],
    },
    {
        "id": "streaming",
        "name": "Streaming requests",
        "description": "Short unique streaming requests exercise the normal proxy path.",
        "signals": ["requests", "tokens", "replay"],
    },
]
SCENARIO_IDS = {item["id"] for item in SCENARIOS}


def list_scenarios() -> list[dict[str, Any]]:
    return [dict(item) for item in SCENARIOS]


def run_scenario(repo: Repository, scenario: str, mode: str) -> dict[str, Any]:
    if scenario not in SCENARIO_IDS:
        raise ValueError(f"Unknown playground scenario: {scenario}")
    if mode not in {"shadow", "enforce"}:
        raise ValueError(f"Unsupported playground mode: {mode}")
    agents = repo.list_agents()
    if not agents:
        raise RuntimeError("No local agent is available. Run alg setup first.")
    session = run_demo(repo, agents[-1], scenario, mode)
    return playground_run(repo, session.id)


def playground_run(repo: Repository, session_id: str) -> dict[str, Any]:
    session = repo.get_session(session_id)
    if session is None:
        raise KeyError(session_id)
    trace = repo.trace_for_session(session_id)
    payload: dict[str, Any] = {
        "schema_version": "playground.run.v1",
        "id": session.id,
        "status": "complete",
        "scenario": (session.external_session_id or "").removeprefix("demo-"),
        "session": session_dict(session),
        "requests": [request_dict(item) for item in repo.requests_for_session(session.id)],
        "events": [event_dict(item) for item in repo.events_for_session(session.id)],
        "trace": None,
        "spans": [],
        "trace_events": [],
    }
    if trace is not None:
        payload["trace"] = trace_run_dict(trace)
        payload["spans"] = [trace_span_dict(item) for item in repo.trace_spans(trace.id)]
        payload["trace_events"] = [
            trace_event_dict(item) for item in repo.trace_events(trace.id)
        ]
    return payload

