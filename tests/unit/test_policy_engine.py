from __future__ import annotations

from app.core.policy_engine import evaluate
from app.db.models import Agent, GuardSession, Policy


def _session(**overrides) -> GuardSession:
    data = {
        "id": "ses_test",
        "project_id": "default",
        "agent_id": "agt_test",
        "request_count": 0,
        "total_tokens": 0,
        "status": "active",
    }
    data.update(overrides)
    return GuardSession(**data)


def _agent(**overrides) -> Agent:
    data = {
        "id": "agt_test",
        "project_id": "default",
        "name": "Test agent",
        "protocol": "openai",
        "key_hash": "hash",
        "enabled": True,
        "paused": False,
    }
    data.update(overrides)
    return Agent(**data)


def _policy(rule_type: str, threshold: int, window_size: int = 8) -> Policy:
    return Policy(
        id=f"rule_{rule_type}",
        project_id="default",
        rule_type=rule_type,
        threshold=threshold,
        window_size=window_size,
        action="block",
        enabled=True,
    )


def test_shadow_flags_exact_repeat_without_blocking() -> None:
    decision = evaluate(
        mode="shadow",
        session=_session(),
        agent=_agent(),
        policies=[_policy("exact_repeat", 3)],
        request_fp="same",
        tool_fps=[],
        recent_request_fps=["same", "same"],
        recent_tool_fps=[],
        last_error_count=0,
    )
    assert decision.decision == "shadow_flag"
    assert decision.reason_code == "LOOP_EXACT"
    assert decision.http_status == 200


def test_enforce_blocks_request_limit() -> None:
    decision = evaluate(
        mode="enforce",
        session=_session(request_count=50),
        agent=_agent(),
        policies=[_policy("max_requests", 50, 0)],
        request_fp="new",
        tool_fps=[],
        recent_request_fps=[],
        recent_tool_fps=[],
        last_error_count=0,
    )
    assert decision.blocked
    assert decision.reason_code == "LIMIT_REQUESTS"
    assert decision.http_status == 429


def test_paused_agent_blocks_even_in_shadow() -> None:
    decision = evaluate(
        mode="shadow",
        session=_session(),
        agent=_agent(paused=True),
        policies=[],
        request_fp="new",
        tool_fps=[],
        recent_request_fps=[],
        recent_tool_fps=[],
        last_error_count=0,
    )
    assert decision.blocked
    assert decision.reason_code == "AGENT_PAUSED"

