from __future__ import annotations

from app.core.loop_detector import (
    error_fingerprint,
    repeated_sequence,
    request_fingerprint,
    tool_call_fingerprints,
)


def test_request_fingerprint_ignores_dynamic_ids_and_whitespace() -> None:
    left = {
        "model": "demo",
        "messages": [{"role": "user", "content": "hello\n   world"}],
        "request_id": "one",
    }
    right = {
        "request_id": "two",
        "messages": [{"content": "hello world", "role": "user"}],
        "model": "demo",
    }
    assert request_fingerprint(left) == request_fingerprint(right)


def test_tool_call_fingerprints_canonicalize_arguments() -> None:
    body = {
        "tool_calls": [
            {"tool_name": "read_file", "arguments": {"path": "README.md", "line": 1}},
            {"tool_name": "read_file", "arguments": '{"line":1,"path":"README.md"}'},
        ]
    }
    calls = tool_call_fingerprints(body)
    assert calls[0] == calls[1]


def test_repeated_sequence_detects_ababab() -> None:
    assert repeated_sequence(["A", "B", "A", "B", "A", "B"], repeats=3)


def test_error_fingerprint_normalizes_provider_errors() -> None:
    assert error_fingerprint(500, {"error": {"type": "server", "message": "boom   now"}}) == error_fingerprint(
        500, {"error": {"type": "server", "message": "boom now"}}
    )

