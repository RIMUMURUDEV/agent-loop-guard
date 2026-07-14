from __future__ import annotations

from dataclasses import dataclass

from app.core.loop_detector import repeated_sequence
from app.db.models import Agent, GuardSession, Policy

REASON_BY_RULE = {
    "exact_repeat": "LOOP_EXACT",
    "tool_repeat": "LOOP_TOOL_CALL",
    "error_retry": "LOOP_ERROR_RETRY",
    "sequence_repeat": "LOOP_SEQUENCE",
    "max_requests": "LIMIT_REQUESTS",
    "max_tokens": "LIMIT_TOKENS",
}

MESSAGE_BY_REASON = {
    "LOOP_EXACT": "The same normalized request repeated in the recent window.",
    "LOOP_TOOL_CALL": "The same tool call and arguments repeated in the recent window.",
    "LOOP_ERROR_RETRY": "The same upstream error repeated consecutively.",
    "LOOP_SEQUENCE": "A short sequence of request fingerprints repeated.",
    "LIMIT_REQUESTS": "The session request limit has been reached.",
    "LIMIT_TOKENS": "The session token limit has been reached.",
    "SESSION_PAUSED": "The session is paused.",
    "AGENT_PAUSED": "The agent key is paused.",
}


@dataclass(slots=True)
class PolicyDecision:
    decision: str
    mode: str
    reason_code: str | None = None
    rule_id: str | None = None
    message: str = "Allowed."
    details: dict | None = None
    http_status: int = 200

    @property
    def blocked(self) -> bool:
        return self.decision == "block"


def _policy_map(policies: list[Policy]) -> dict[str, Policy]:
    return {policy.rule_type: policy for policy in policies if policy.enabled}


def _finish(mode: str, policy: Policy, reason_code: str, details: dict) -> PolicyDecision:
    decision = "shadow_flag"
    status = 200
    if mode == "enforce" and policy.action == "block":
        decision = "block"
        status = 429
    return PolicyDecision(
        decision=decision,
        mode=mode,
        reason_code=reason_code,
        rule_id=policy.id,
        message=MESSAGE_BY_REASON[reason_code],
        details=details,
        http_status=status,
    )


def evaluate(
    *,
    mode: str,
    session: GuardSession,
    agent: Agent,
    policies: list[Policy],
    request_fp: str,
    tool_fps: list[str],
    recent_request_fps: list[str],
    recent_tool_fps: list[str],
    last_error_count: int,
) -> PolicyDecision:
    mode = "enforce" if mode == "enforce" else "shadow"

    if agent.paused:
        return PolicyDecision(
            decision="block",
            mode=mode,
            reason_code="AGENT_PAUSED",
            rule_id="manual_agent_pause",
            message=MESSAGE_BY_REASON["AGENT_PAUSED"],
            details={},
            http_status=409,
        )
    if session.status == "paused":
        return PolicyDecision(
            decision="block",
            mode=mode,
            reason_code="SESSION_PAUSED",
            rule_id="manual_session_pause",
            message=MESSAGE_BY_REASON["SESSION_PAUSED"],
            details={},
            http_status=409,
        )

    rules = _policy_map(policies)

    max_requests = rules.get("max_requests")
    if max_requests and session.request_count >= max_requests.threshold:
        return _finish(
            mode,
            max_requests,
            "LIMIT_REQUESTS",
            {"count": session.request_count, "threshold": max_requests.threshold},
        )

    max_tokens = rules.get("max_tokens")
    if max_tokens and session.total_tokens >= max_tokens.threshold:
        return _finish(
            mode,
            max_tokens,
            "LIMIT_TOKENS",
            {"tokens": session.total_tokens, "threshold": max_tokens.threshold},
        )

    exact = rules.get("exact_repeat")
    if exact:
        window = max(1, exact.window_size - 1)
        recent = recent_request_fps[-window:]
        count = recent.count(request_fp) + 1
        if count >= exact.threshold:
            return _finish(
                mode,
                exact,
                "LOOP_EXACT",
                {"count": count, "window": exact.window_size, "fingerprint": request_fp},
            )

    tool = rules.get("tool_repeat")
    if tool and tool_fps:
        recent = recent_tool_fps[-tool.window_size :]
        for fp in tool_fps:
            count = recent.count(fp) + tool_fps.count(fp)
            if count >= tool.threshold:
                return _finish(
                    mode,
                    tool,
                    "LOOP_TOOL_CALL",
                    {"count": count, "window": tool.window_size, "fingerprint": fp},
                )

    error_retry = rules.get("error_retry")
    if error_retry and last_error_count >= error_retry.threshold:
        return _finish(
            mode,
            error_retry,
            "LOOP_ERROR_RETRY",
            {"count": last_error_count, "threshold": error_retry.threshold},
        )

    sequence = rules.get("sequence_repeat")
    if sequence:
        values = recent_request_fps[-sequence.window_size :] + [request_fp]
        if repeated_sequence(values, repeats=sequence.threshold):
            return _finish(
                mode,
                sequence,
                "LOOP_SEQUENCE",
                {"window": sequence.window_size, "threshold": sequence.threshold},
            )

    return PolicyDecision(decision="allow", mode=mode)

