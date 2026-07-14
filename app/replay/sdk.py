from __future__ import annotations

import time
import uuid
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.redaction import redact_value


class ReplayClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8787", timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def trace(self, **attributes: Any) -> TraceContext:
        return TraceContext(self, attributes)

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/api/v1/traces", json=redact_value(payload), timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()


@dataclass
class SpanContext(AbstractContextManager["SpanContext"]):
    trace: TraceContext
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    parent_span_id: str | None = None
    span_id: str = field(default_factory=lambda: f"spn_{uuid.uuid4().hex[:24]}")
    start_ns: int = field(default_factory=time.time_ns)
    end_ns: int | None = None
    status: str = "ok"
    events: list[dict[str, Any]] = field(default_factory=list)

    def event(self, name: str, severity: str = "info", **attributes: Any) -> None:
        self.events.append(
            {
                "name": name,
                "severity": severity,
                "timestamp_ns": time.time_ns(),
                "attributes": attributes,
            }
        )

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.end_ns = time.time_ns()
        if exc is not None:
            self.status = "error"
            self.event("exception", "error", type=type(exc).__name__, message=str(exc))
        self.trace.spans.append(
            {
                "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "name": self.name,
                "status": self.status,
                "start_ns": self.start_ns,
                "end_ns": self.end_ns,
                "attributes": self.attributes,
                "events": self.events,
            }
        )
        return False


@dataclass
class TraceContext(AbstractContextManager["TraceContext"]):
    client: ReplayClient
    attributes: dict[str, Any] = field(default_factory=dict)
    trace_id: str = field(default_factory=lambda: f"trc_{uuid.uuid4().hex[:24]}")
    start_ns: int = field(default_factory=time.time_ns)
    spans: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None

    def span(
        self,
        name: str,
        *,
        parent_span_id: str | None = None,
        **attributes: Any,
    ) -> SpanContext:
        return SpanContext(self, name, attributes, parent_span_id)

    def __exit__(self, exc_type, exc, traceback) -> bool:
        status = "error" if exc is not None else "ok"
        self.result = self.client.ingest(
            {
                "trace_id": self.trace_id,
                "status": status,
                "start_ns": self.start_ns,
                "end_ns": time.time_ns(),
                "attributes": self.attributes,
                "spans": self.spans,
            }
        )
        return False
