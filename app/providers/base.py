from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ProviderResult:
    status_code: int
    headers: dict[str, str]
    content: bytes
    json_body: Any | None = None
    media_type: str | None = None


@dataclass(slots=True)
class ProviderStream:
    status_code: int
    headers: dict[str, str]
    chunks: AsyncIterator[bytes]
    media_type: str = "text/event-stream"

