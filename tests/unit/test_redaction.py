from __future__ import annotations

from app.core.redaction import redact_headers, redact_text, safe_preview


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

