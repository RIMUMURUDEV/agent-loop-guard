from __future__ import annotations

from app.core.redaction import (
    redact_headers,
    redact_text,
    redact_value,
    safe_json_bytes,
    safe_preview,
)


def test_redact_text_removes_common_secrets() -> None:
    text = "token=sk-abcdefghijklmnopqrstuvwxyz and github=ghp_abcdefghijklmnopqrstuvwxyz"
    redacted = redact_text(text)
    assert "sk-" not in redacted
    assert "ghp_" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_headers_hides_authorization() -> None:
    headers = redact_headers({"Authorization": "Bearer alg_secret", "x-trace": "ok"})
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["x-trace"] == "ok"


def test_safe_preview_defaults_to_metadata_only() -> None:
    preview = safe_preview({"prompt": "secret business data", "model": "demo"}, False)
    assert "secret business data" not in preview
    assert "metadata-only" in preview


def test_recursive_redaction_hides_nested_values_and_sensitive_keys() -> None:
    value = redact_value(
        {
            "password": "plain text",
            "nested": ["sk-abcdefghijklmnopqrstuvwxyz", {"access_token": "hidden"}],
            "tuple": ("safe", "ghp_abcdefghijklmnopqrstuvwxyz"),
            "count": 2,
        }
    )

    assert value["password"] == "[REDACTED]"
    assert value["nested"] == ["[REDACTED]", {"access_token": "[REDACTED]"}]
    assert value["tuple"] == ["safe", "[REDACTED]"]
    assert value["count"] == 2


def test_full_preview_redacts_truncates_and_handles_non_json_values() -> None:
    preview = safe_preview({"value": "x" * 100, "key": "sk-abcdefghijklmnopqrstuvwxyz"}, True, 40)
    fallback = safe_preview({"values": {1, 2}}, True)

    assert "sk-" not in preview
    assert preview.endswith("...[truncated]")
    assert "{1, 2}" in fallback or "{2, 1}" in fallback


def test_safe_json_bytes_replaces_invalid_utf8_and_truncates() -> None:
    result = safe_json_bytes(
        b"prefix-\xff-" + b"x" * 100 + b"-sk-abcdefghijklmnopqrstuvwxyz",
        max_chars=24,
    )

    assert "sk-" not in result
    assert result.endswith("...[truncated]")


def test_none_text_stays_none_and_metadata_scalar_is_hidden() -> None:
    assert redact_text(None) is None
    assert safe_preview("private prompt") == "metadata-only"
