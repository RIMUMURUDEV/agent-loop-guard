from __future__ import annotations

from typing import Any


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_strings(item))
        return result
    return []


def estimate_tokens(value: Any) -> int:
    chars = sum(len(item) for item in _strings(value))
    return max(1, (chars + 3) // 4)


def usage_from_response(protocol: str, response_json: dict[str, Any] | None) -> dict[str, int | bool] | None:
    if not response_json:
        return None
    usage = response_json.get("usage")
    if not isinstance(usage, dict):
        return None
    if protocol == "anthropic":
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "estimated": False,
        }
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "estimated": False,
    }


def usage_or_estimate(
    protocol: str, request_body: Any, response_json: dict[str, Any] | None = None
) -> dict[str, int | bool]:
    usage = usage_from_response(protocol, response_json)
    if usage is not None and int(usage["total_tokens"]) > 0:
        return usage
    input_tokens = estimate_tokens(request_body)
    output_tokens = estimate_tokens(response_json or "")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated": True,
    }

