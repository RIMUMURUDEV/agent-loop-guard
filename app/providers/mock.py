from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.core.token_meter import estimate_tokens
from app.providers.base import ProviderResult, ProviderStream


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _text_from_body(body: dict[str, Any]) -> str:
    for key in ("input", "prompt"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = body.get("messages")
    if isinstance(messages, list):
        for item in reversed(messages):
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                if isinstance(content, list):
                    parts = [
                        str(part.get("text"))
                        for part in content
                        if isinstance(part, dict) and part.get("text")
                    ]
                    if parts:
                        return " ".join(parts)
    return "mock request"


def _usage(protocol: str, body: dict[str, Any], output: str) -> dict[str, int]:
    input_tokens = estimate_tokens(body)
    output_tokens = estimate_tokens(output)
    if protocol == "anthropic":
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


class MockProvider:
    """Deterministic local provider used for demos and tests."""

    async def models(self) -> ProviderResult:
        payload = {
            "object": "list",
            "data": [
                {"id": "demo-model", "object": "model", "created": 0, "owned_by": "agent-loop-guard"},
                {"id": "mock-loop-model", "object": "model", "created": 0, "owned_by": "agent-loop-guard"},
            ],
        }
        return ProviderResult(200, {"content-type": "application/json"}, _json_bytes(payload), payload)

    async def count_tokens(self, body: dict[str, Any]) -> ProviderResult:
        payload = {"input_tokens": estimate_tokens(body)}
        return ProviderResult(200, {"content-type": "application/json"}, _json_bytes(payload), payload)

    async def request(self, protocol: str, endpoint: str, body: dict[str, Any]) -> ProviderResult:
        if endpoint.endswith("/models"):
            return await self.models()
        if endpoint.endswith("/messages/count_tokens"):
            return await self.count_tokens(body)

        status = int(body.get("mock_status") or 200)
        if body.get("mock_error") or status >= 400:
            payload = {
                "error": {
                    "type": "mock_error",
                    "code": "mock_error",
                    "message": str(body.get("mock_error") or "mock upstream error"),
                }
            }
            return ProviderResult(status, {"content-type": "application/json"}, _json_bytes(payload), payload)

        prompt = _text_from_body(body)
        output = f"Mock response for: {prompt[:120]}"
        model = str(body.get("model") or "demo-model")
        if protocol == "anthropic":
            payload = {
                "id": f"msg_{uuid.uuid4().hex[:16]}",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": output}],
                "stop_reason": "end_turn",
                "usage": _usage(protocol, body, output),
            }
        elif endpoint.endswith("/responses"):
            payload = {
                "id": f"resp_{uuid.uuid4().hex[:16]}",
                "object": "response",
                "model": model,
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": output}],
                    }
                ],
                "usage": _usage(protocol, body, output),
            }
        else:
            payload = {
                "id": f"chatcmpl_{uuid.uuid4().hex[:16]}",
                "object": "chat.completion",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": output},
                    }
                ],
                "usage": _usage(protocol, body, output),
            }
        return ProviderResult(200, {"content-type": "application/json"}, _json_bytes(payload), payload)

    async def stream(self, protocol: str, endpoint: str, body: dict[str, Any]) -> ProviderStream:
        prompt = _text_from_body(body)
        model = str(body.get("model") or "demo-model")
        chunks = [
            f"Mock streaming response for: {prompt[:80]}",
            " -- guarded by Agent Loop Guard.",
        ]

        async def iterator() -> AsyncIterator[bytes]:
            if protocol == "anthropic":
                yield b"event: message_start\n"
                start = {"type": "message_start", "message": {"id": "msg_mock", "model": model}}
                yield b"data: " + _json_bytes(start) + b"\n\n"
                for chunk in chunks:
                    await asyncio.sleep(0)
                    payload = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": chunk}}
                    yield b"event: content_block_delta\n"
                    yield b"data: " + _json_bytes(payload) + b"\n\n"
                usage = _usage(protocol, body, "".join(chunks))
                yield b"event: message_delta\n"
                yield b"data: " + _json_bytes({"type": "message_delta", "usage": usage}) + b"\n\n"
                yield b"event: message_stop\n"
                yield b"data: {\"type\":\"message_stop\"}\n\n"
                return

            for chunk in chunks:
                await asyncio.sleep(0)
                if endpoint.endswith("/responses"):
                    payload = {"type": "response.output_text.delta", "delta": chunk}
                else:
                    payload = {
                        "id": "chatcmpl_mock",
                        "object": "chat.completion.chunk",
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
                    }
                yield b"data: " + _json_bytes(payload) + b"\n\n"
            yield b"data: [DONE]\n\n"

        return ProviderStream(200, {"content-type": "text/event-stream"}, iterator())

