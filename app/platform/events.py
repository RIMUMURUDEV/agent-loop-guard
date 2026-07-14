from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.redaction import redact_value


@dataclass(slots=True)
class EventEnvelope:
    """Stable, redacted event contract shared by all local modules."""

    source: str
    type: str
    project_id: str = "default"
    trace_id: str | None = None
    span_id: str | None = None
    severity: str = "info"
    timestamp_ns: int = field(default_factory=time.time_ns)
    attributes: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:24]}")
    schema_version: str = "event.v1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["attributes"] = redact_value(self.attributes)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EventEnvelope:
        return cls(
            event_id=str(payload.get("event_id") or f"evt_{uuid.uuid4().hex[:24]}"),
            source=str(payload.get("source") or "unknown"),
            type=str(payload.get("type") or "event"),
            project_id=str(payload.get("project_id") or "default"),
            trace_id=payload.get("trace_id"),
            span_id=payload.get("span_id"),
            severity=str(payload.get("severity") or "info"),
            timestamp_ns=int(payload.get("timestamp_ns") or time.time_ns()),
            attributes=dict(payload.get("attributes") or {}),
            schema_version=str(payload.get("schema_version") or "event.v1"),
        )
