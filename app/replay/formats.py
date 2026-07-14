from __future__ import annotations

import hashlib
import json
from typing import Any


def trace_to_jsonl(bundle: dict[str, Any]) -> str:
    rows = [{"record_type": "run", **bundle["run"]}]
    rows.extend({"record_type": "span", **item} for item in bundle.get("spans", []))
    rows.extend({"record_type": "event", **item} for item in bundle.get("events", []))
    rows.extend({"record_type": "artifact", **item} for item in bundle.get("artifacts", []))
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)


def trace_to_otel(bundle: dict[str, Any]) -> dict[str, Any]:
    run = bundle["run"]
    trace_id = hashlib.sha256(str(run["id"]).encode("utf-8")).hexdigest()[:32]

    def otel_span_id(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    spans = []
    events_by_span: dict[str, list[dict[str, Any]]] = {}
    for event in bundle.get("events", []):
        if event.get("span_id"):
            events_by_span.setdefault(event["span_id"], []).append(event)
    for span in bundle.get("spans", []):
        spans.append(
            {
                "traceId": trace_id,
                "spanId": otel_span_id(span["id"]),
                "parentSpanId": (
                    otel_span_id(span["parent_span_id"])
                    if span.get("parent_span_id")
                    else ""
                ),
                "name": span["name"],
                "startTimeUnixNano": str(span["start_ns"]),
                "endTimeUnixNano": str(span.get("end_ns") or span["start_ns"]),
                "status": {"code": "STATUS_CODE_ERROR" if span["status"] in {"error", "blocked"} else "STATUS_CODE_OK"},
                "attributes": [
                    {"key": str(key), "value": {"stringValue": str(value)}}
                    for key, value in span.get("attributes", {}).items()
                ],
                "events": [
                    {
                        "timeUnixNano": str(event["timestamp_ns"]),
                        "name": event["name"],
                        "attributes": [
                            {"key": str(key), "value": {"stringValue": str(value)}}
                            for key, value in event.get("attributes", {}).items()
                        ],
                    }
                    for event in events_by_span.get(span["id"], [])
                ],
            }
        )
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "agent-loop-guard"}},
                        {"key": "project.id", "value": {"stringValue": run["project_id"]}},
                    ]
                },
                "scopeSpans": [{"scope": {"name": "agent-loop-guard.replay"}, "spans": spans}],
            }
        ]
    }


def jsonl_to_trace(text: str) -> dict[str, Any]:
    bundle: dict[str, Any] = {"spans": [], "events": [], "artifacts": []}
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        record_type = row.pop("record_type", None)
        if record_type == "run":
            bundle["run"] = row
        elif record_type in {"span", "event", "artifact"}:
            bundle[f"{record_type}s"].append(row)
    if "run" not in bundle:
        raise ValueError("JSONL bundle does not contain a run record.")
    return bundle
