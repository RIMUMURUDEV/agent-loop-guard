from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.demo import run_demo
from app.db.repository import (
    Repository,
    agent_dict,
    event_dict,
    policy_dict,
    request_dict,
    session_dict,
)
from app.db.session import get_db

router = APIRouter(prefix="/api")


class PolicyUpdate(BaseModel):
    id: str | None = None
    rule_type: str
    threshold: int = Field(ge=1)
    window_size: int = Field(ge=0, default=0)
    action: str = "block"
    enabled: bool = True


class AgentCreate(BaseModel):
    project_id: str = "default"
    name: str
    protocol: str = "openai"


class SessionUpdate(BaseModel):
    name: str | None = None
    note: str | None = None


class DemoRequest(BaseModel):
    scenario: str = "exact-loop"
    mode: str = "shadow"


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    repo = Repository(db)
    return {"ok": True, "database": "ok", "stats": repo.aggregate_stats()}


@router.get("/sessions")
def sessions(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    return [session_dict(item) for item in Repository(db).list_sessions(limit)]


@router.get("/sessions/{session_id}")
def session_detail(session_id: str, db: Session = Depends(get_db)) -> dict:
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return {
        "session": session_dict(session),
        "requests": [request_dict(item) for item in repo.requests_for_session(session_id)],
        "events": [event_dict(item) for item in repo.events_for_session(session_id)],
    }


@router.patch("/sessions/{session_id}")
def update_session(session_id: str, payload: SessionUpdate, db: Session = Depends(get_db)) -> dict:
    session = Repository(db).update_session(session_id, name=payload.name, note=payload.note)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return session_dict(session)


@router.get("/sessions/{session_id}/events")
def session_events(session_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return [event_dict(item) for item in Repository(db).events_for_session(session_id)]


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = Repository(db).pause_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return session_dict(session)


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = Repository(db).resume_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return session_dict(session)


@router.get("/policies/{project_id}")
def policies(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    return [policy_dict(item) for item in Repository(db).policies(project_id)]


@router.put("/policies/{project_id}")
def put_policies(project_id: str, payload: list[PolicyUpdate], db: Session = Depends(get_db)) -> list[dict]:
    rows = [item.model_dump() for item in payload]
    return [policy_dict(item) for item in Repository(db).upsert_policies(project_id, rows)]


@router.get("/agents")
def agents(db: Session = Depends(get_db)) -> list[dict]:
    return [agent_dict(item) for item in Repository(db).list_agents()]


@router.post("/agents")
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)) -> dict:
    agent, raw_key = Repository(db).create_agent(payload.project_id, payload.name, payload.protocol)
    data = agent_dict(agent)
    data["gateway_key"] = raw_key
    return data


@router.post("/agents/{agent_id}/pause")
def pause_agent(agent_id: str, db: Session = Depends(get_db)) -> dict:
    agent = Repository(db).pause_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found.")
    return agent_dict(agent)


@router.post("/agents/{agent_id}/resume")
def resume_agent(agent_id: str, db: Session = Depends(get_db)) -> dict:
    agent = Repository(db).resume_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found.")
    return agent_dict(agent)


@router.post("/demo/run")
def demo_run(payload: DemoRequest, db: Session = Depends(get_db)) -> dict:
    repo = Repository(db)
    agents = repo.list_agents()
    if not agents:
        raise HTTPException(500, "No demo agent is available.")
    session = run_demo(repo, agents[-1], payload.scenario, payload.mode)
    return {
        "session": session_dict(session),
        "events": [event_dict(item) for item in repo.events_for_session(session.id)],
    }


@router.get("/export/sessions/{session_id}.json")
def export_session(session_id: str, db: Session = Depends(get_db)) -> JSONResponse:
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    payload = {
        "schema_version": "1.0",
        "session": session_dict(session),
        "requests": [request_dict(item) for item in repo.requests_for_session(session_id)],
        "events": [event_dict(item) for item in repo.events_for_session(session_id)],
    }
    return JSONResponse(payload)


@router.get("/export/aggregates.csv")
def export_aggregates(db: Session = Depends(get_db)) -> Response:
    stats = Repository(db).aggregate_stats()
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(stats))
    writer.writeheader()
    writer.writerow(stats)
    return Response(stream.getvalue(), media_type="text/csv")

