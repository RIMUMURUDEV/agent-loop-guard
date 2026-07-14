from __future__ import annotations

import hashlib
import json
import re
from typing import Any

DEFAULT_IGNORE_KEYS = {
    "id",
    "request_id",
    "created",
    "created_at",
    "updated_at",
    "timestamp",
    "trace_id",
}


def _normalize_string(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _canonical(value: Any, ignore_keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonical(value[key], ignore_keys)
            for key in sorted(value)
            if key not in ignore_keys
        }
    if isinstance(value, list):
        return [_canonical(item, ignore_keys) for item in value]
    if isinstance(value, str):
        return _normalize_string(value)
    return value


def canonical_json(value: Any, ignore_keys: set[str] | None = None) -> str:
    ignore = DEFAULT_IGNORE_KEYS if ignore_keys is None else DEFAULT_IGNORE_KEYS | ignore_keys
    return json.dumps(_canonical(value, ignore), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def relevant_request_body(body: dict[str, Any]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for key in ("model", "messages", "input", "system", "tools", "tool_choice"):
        if key in body:
            selected[key] = body[key]
    return selected


def request_fingerprint(body: dict[str, Any], ignore_keys: set[str] | None = None) -> str:
    return sha256_text(canonical_json(relevant_request_body(body), ignore_keys))


def _canonical_arg_hash(value: Any) -> str:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
    else:
        parsed = value
    return sha256_text(canonical_json(parsed))


def tool_call_fingerprints(body: Any) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            function = value.get("function")
            if isinstance(function, dict) and "name" in function:
                calls.append((str(function["name"]), _canonical_arg_hash(function.get("arguments", {}))))
            elif value.get("type") == "tool_use" and "name" in value:
                calls.append((str(value["name"]), _canonical_arg_hash(value.get("input", {}))))
            elif "tool_name" in value and ("arguments" in value or "args" in value or "input" in value):
                args = value.get("arguments", value.get("args", value.get("input", {})))
                calls.append((str(value["tool_name"]), _canonical_arg_hash(args)))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(body)
    return calls


def error_fingerprint(status_code: int, body: Any) -> str:
    error_type = None
    message = None
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            error_type = error.get("type") or error.get("code")
            message = error.get("message") or error.get("detail")
    if message is None:
        message = str(body)
    normalized = {
        "status": status_code,
        "type": _normalize_string(str(error_type or "unknown")),
        "message": _normalize_string(str(message))[:500],
    }
    return sha256_text(canonical_json(normalized))


def repeated_sequence(sequence: list[str], min_len: int = 2, max_len: int = 5, repeats: int = 3) -> bool:
    if len(sequence) < min_len * repeats:
        return False
    upper = min(max_len, len(sequence) // repeats)
    for size in range(min_len, upper + 1):
        suffix = sequence[-size * repeats :]
        pattern = suffix[:size]
        if all(suffix[i : i + size] == pattern for i in range(0, len(suffix), size)):
            return True
    return False

