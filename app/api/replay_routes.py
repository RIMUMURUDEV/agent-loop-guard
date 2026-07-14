from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.repository import (
    Repository,
    trace_event_dict,
    trace_run_dict,
    trace_span_dict,
)
from app.db.session import get_db
from app.replay.formats import trace_to_jsonl, trace_to_otel

router = APIRouter(prefix="/api/v1")


class TraceEventPayload(BaseModel):
    event_id: str | None = None
    span_id: str | None = None
    name: str = "event"
    severity: str = "info"
    timestamp_ns: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceSpanPayload(BaseModel):
    span_id: str | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None
    name: str = "span"
    status: str = "ok"
    start_ns: int | None = None
    end_ns: int | None = None
    duration_ms: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[TraceEventPayload] = Field(default_factory=list)


class TraceCreatePayload(BaseModel):
    trace_id: str | None = None
    project_id: str = "default"
    task_id: str | None = None
    task_fingerprint: str | None = None
    agent_name: str | None = None
    model: str | None = None
    status: str = "running"
    failure_tag: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_cost_micros: int = 0
    pinned: bool = False
    start_ns: int | None = None
    end_ns: int | None = None
    duration_ms: int = 0
    attributes: dict[str, Any] = Field(default_factory=dict)
    spans: list[TraceSpanPayload] = Field(default_factory=list)


class EventBatchPayload(BaseModel):
    trace_id: str
    events: list[TraceEventPayload]


class ComparePayload(BaseModel):
    left_trace_id: str
    right_trace_id: str


class PinPayload(BaseModel):
    pinned: bool = True


class TraceImportPayload(BaseModel):
    bundle: dict[str, Any]


@router.post("/traces")
def create_trace(payload: TraceCreatePayload, db: Session = Depends(get_db)) -> dict:
    repo = Repository(db)
    trace_data = payload.model_dump(exclude={"spans"})
    span_starts = [span.start_ns for span in payload.spans if span.start_ns is not None]
    span_ends = [span.end_ns for span in payload.spans if span.end_ns is not None]
    if trace_data.get("start_ns") is None and span_starts:
        trace_data["start_ns"] = min(span_starts)
    if trace_data.get("end_ns") is None and span_ends:
        trace_data["end_ns"] = max(span_ends)
    if not trace_data.get("duration_ms") and span_starts and span_ends:
        trace_data["duration_ms"] = max(0, int((max(span_ends) - min(span_starts)) / 1_000_000))
    run = repo.create_trace_run(trace_data)
    for span_payload in payload.spans:
        span_data = span_payload.model_dump(exclude={"events"})
        span = repo.add_trace_span(run.id, span_data)
        if span_payload.events:
            events = [
                {**event.model_dump(), "span_id": event.span_id or (span.id if span else None)}
                for event in span_payload.events
            ]
            repo.add_trace_events(run.id, events)
    exported = repo.trace_export(run.id)
    if exported is None:
        raise HTTPException(500, "Trace was not created.")
    return exported


@router.post("/spans")
def create_span(payload: TraceSpanPayload, db: Session = Depends(get_db)) -> dict:
    if not payload.trace_id:
        raise HTTPException(400, "trace_id is required.")
    repo = Repository(db)
    span = repo.add_trace_span(payload.trace_id, payload.model_dump(exclude={"events"}))
    if span is None:
        raise HTTPException(404, "Trace not found.")
    if payload.events:
        repo.add_trace_events(
            payload.trace_id,
            [
                {**event.model_dump(), "span_id": event.span_id or span.id}
                for event in payload.events
            ],
        )
    return trace_span_dict(span)


@router.post("/events/batch")
def create_events(payload: EventBatchPayload, db: Session = Depends(get_db)) -> dict:
    events = Repository(db).add_trace_events(
        payload.trace_id, [event.model_dump() for event in payload.events]
    )
    if events is None:
        raise HTTPException(404, "Trace not found.")
    return {"events": [trace_event_dict(item) for item in events]}


@router.get("/runs")
def runs(
    limit: int = 50,
    project_id: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        trace_run_dict(item)
        for item in Repository(db).list_trace_runs(limit=limit, project_id=project_id, query=q)
    ]


@router.get("/runs/{trace_id}")
def run_detail(trace_id: str, db: Session = Depends(get_db)) -> dict:
    exported = Repository(db).trace_export(trace_id)
    if exported is None:
        raise HTTPException(404, "Trace not found.")
    return exported


@router.get("/runs/{trace_id}/export")
def run_export(
    trace_id: str,
    format: str = Query(default="json", pattern="^(json|jsonl|otel)$"),
    db: Session = Depends(get_db),
):
    exported = Repository(db).trace_export(trace_id)
    if exported is None:
        raise HTTPException(404, "Trace not found.")
    if format == "jsonl":
        return PlainTextResponse(trace_to_jsonl(exported), media_type="application/x-ndjson")
    if format == "otel":
        return JSONResponse(trace_to_otel(exported))
    return JSONResponse(exported)


@router.post("/runs/import")
def import_run(payload: TraceImportPayload, db: Session = Depends(get_db)) -> dict:
    repo = Repository(db)
    try:
        run = repo.import_trace_bundle(payload.bundle)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    exported = repo.trace_export(run.id)
    assert exported is not None
    return exported


@router.post("/runs/{trace_id}/pin")
def pin_run(trace_id: str, payload: PinPayload, db: Session = Depends(get_db)) -> dict:
    run = Repository(db).pin_trace(trace_id, payload.pinned)
    if run is None:
        raise HTTPException(404, "Trace not found.")
    return trace_run_dict(run)


@router.post("/compare")
def compare(payload: ComparePayload, db: Session = Depends(get_db)) -> dict:
    result = Repository(db).compare_traces(payload.left_trace_id, payload.right_trace_id)
    if result is None:
        raise HTTPException(404, "One or both traces were not found.")
    return result
