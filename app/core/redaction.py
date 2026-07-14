from __future__ import annotations

import json
import re
from typing import Any

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{16,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{16,}"),
    re.compile(r"alg_[A-Za-z0-9_]{12,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|token|secret)\s*[:=]\s*['\"]?[^'\"\s,}]+"),
]

SENSITIVE_HEADERS = {
    "authorization",
    "x-api-key",
    "api-key",
    "anthropic-api-key",
    "openai-api-key",
    "proxy-authorization",
}


def redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            safe[key] = "[REDACTED]"
        else:
            safe[key] = redact_text(value) or ""
    return safe


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if str(key).lower() in SENSITIVE_HEADERS
            or any(part in str(key).lower() for part in ("token", "secret", "password", "api_key"))
            else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def safe_preview(value: Any, full_content_logging: bool = False, max_chars: int = 500) -> str:
    if not full_content_logging:
        if isinstance(value, dict):
            keys = ", ".join(sorted(str(k) for k in value.keys())[:12])
            return f"metadata-only keys=[{keys}]"
        return "metadata-only"
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(value)
    text = redact_text(text) or ""
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text


def safe_json_bytes(content: bytes, max_chars: int = 500) -> str:
    text = content.decode("utf-8", errors="replace")
    text = redact_text(text) or ""
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text
