from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.demo import run_demo
from app.db.repository import (
    Repository,
    agent_dict,
    event_dict,
    mcp_approval_dict,
    mcp_event_dict,
    mcp_server_dict,
    policy_dict,
    request_dict,
    session_dict,
    trace_artifact_dict,
    trace_event_dict,
    trace_run_dict,
    trace_span_dict,
)
from app.db.session import get_db

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    approvals = repo.list_mcp_approvals(pending_only=True)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "stats": repo.aggregate_stats(),
            "sessions": [session_dict(item) for item in repo.list_sessions(10)],
            "pending_approvals": len(approvals),
            "docker_available": shutil.which("docker") is not None,
        },
    )


@router.get("/sessions")
def sessions_page(request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    return templates.TemplateResponse(
        request,
        "sessions.html",
        {"sessions": [session_dict(item) for item in repo.list_sessions(100)]},
    )


@router.get("/sessions/{session_id}")
def session_page(session_id: str, request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    return templates.TemplateResponse(
        request,
        "session_detail.html",
        {
            "session": session_dict(session),
            "requests": [request_dict(item) for item in repo.requests_for_session(session_id)],
            "events": [event_dict(item) for item in repo.events_for_session(session_id)],
        },
    )


@router.get("/replay")
def replay_page(
    request: Request,
    q: str | None = None,
    project_id: str | None = None,
    db: Session = Depends(get_db),
):
    repo = Repository(db)
    return templates.TemplateResponse(
        request,
        "replay.html",
        {
            "runs": [
                trace_run_dict(item)
                for item in repo.list_trace_runs(limit=100, project_id=project_id, query=q)
            ],
            "q": q or "",
            "project_id": project_id or "",
        },
    )


@router.get("/mcp")
def mcp_page(request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    return templates.TemplateResponse(
        request,
        "mcp.html",
        {
            "servers": [mcp_server_dict(item) for item in repo.list_mcp_servers()],
            "events": [mcp_event_dict(item) for item in repo.list_mcp_events(100)],
            "approvals": [mcp_approval_dict(item) for item in repo.list_mcp_approvals()],
            "policy_path": request.app.state.config.mcp_policy_path,
        },
    )


@router.post("/mcp/approvals/{approval_id}/decision")
async def mcp_approval_ui(
    approval_id: str, request: Request, db: Session = Depends(get_db)
):
    form = await request.form()
    action = str(form.get("action") or "deny")
    scope = str(form.get("scope") or "once")
    Repository(db).decide_mcp_approval(approval_id, action, scope)
    return RedirectResponse("/mcp", status_code=303)


@router.post("/replay/compare")
async def replay_compare_page(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    left_id = str(form.get("left_trace_id") or "")
    right_id = str(form.get("right_trace_id") or "")
    result = Repository(db).compare_traces(left_id, right_id)
    if result is None:
        raise HTTPException(404, "One or both traces were not found.")
    return templates.TemplateResponse(
        request,
        "replay_compare.html",
        {"result": result, "left_id": left_id, "right_id": right_id},
    )


@router.get("/replay/{trace_id}")
def replay_detail_page(trace_id: str, request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    run = repo.get_trace_run(trace_id)
    if run is None:
        raise HTTPException(404, "Trace not found.")
    spans = [trace_span_dict(item) for item in repo.trace_spans(trace_id)]
    if spans:
        first_start = min(span["start_ns"] for span in spans)
        last_end = max((span["end_ns"] or span["start_ns"]) for span in spans)
        total = max(1, last_end - first_start)
        parents = {span["id"]: span.get("parent_span_id") for span in spans}
        for span in spans:
            depth = 0
            parent = span.get("parent_span_id")
            while parent and depth < 8:
                depth += 1
                parent = parents.get(parent)
            span["depth"] = depth
            span["offset_pct"] = ((span["start_ns"] - first_start) / total) * 100
            span["width_pct"] = max(1.5, (max(1, span["duration_ms"] * 1_000_000) / total) * 100)
    return templates.TemplateResponse(
        request,
        "replay_detail.html",
        {
            "run": trace_run_dict(run),
            "spans": spans,
            "events": [trace_event_dict(item) for item in repo.trace_events(trace_id)],
            "artifacts": [trace_artifact_dict(item) for item in repo.trace_artifacts(trace_id)],
        },
    )


@router.post("/replay/{trace_id}/pin")
async def replay_pin_page(trace_id: str, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    Repository(db).pin_trace(trace_id, str(form.get("pinned") or "true") == "true")
    return RedirectResponse(f"/replay/{trace_id}", status_code=303)


@router.post("/sessions/{session_id}/pause")
def pause_session_ui(session_id: str, db: Session = Depends(get_db)):
    Repository(db).pause_session(session_id)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/resume")
def resume_session_ui(session_id: str, db: Session = Depends(get_db)):
    Repository(db).resume_session(session_id)
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/edit")
async def edit_session_ui(session_id: str, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    Repository(db).update_session(
        session_id,
        name=str(form.get("name") or ""),
        note=str(form.get("note") or ""),
    )
    return RedirectResponse(f"/sessions/{session_id}", status_code=303)


@router.get("/policies")
def policies_page(request: Request, project_id: str = "default", db: Session = Depends(get_db)):
    repo = Repository(db)
    return templates.TemplateResponse(
        request,
        "policies.html",
        {"project_id": project_id, "policies": [policy_dict(item) for item in repo.policies(project_id)]},
    )


@router.post("/policies/{project_id}/update")
async def update_policies_ui(project_id: str, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    rows = []
    for policy in Repository(db).policies(project_id):
        prefix = policy.id
        rows.append(
            {
                "id": policy.id,
                "rule_type": policy.rule_type,
                "threshold": int(form.get(f"{prefix}_threshold") or policy.threshold),
                "window_size": int(form.get(f"{prefix}_window_size") or policy.window_size),
                "action": str(form.get(f"{prefix}_action") or policy.action),
                "enabled": form.get(f"{prefix}_enabled") == "on",
            }
        )
    Repository(db).upsert_policies(project_id, rows)
    return RedirectResponse(f"/policies?project_id={project_id}", status_code=303)


@router.get("/agents")
def agents_page(request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    return templates.TemplateResponse(
        request,
        "agents.html",
        {"agents": [agent_dict(item) for item in repo.list_agents()], "created_key": None},
    )


@router.post("/agents")
async def create_agent_ui(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    repo = Repository(db)
    agent, raw_key = repo.create_agent(
        str(form.get("project_id") or "default"),
        str(form.get("name") or "Local agent"),
        str(form.get("protocol") or "openai"),
    )
    return templates.TemplateResponse(
        request,
        "agents.html",
        {"agents": [agent_dict(item) for item in repo.list_agents()], "created_key": raw_key, "created_agent": agent_dict(agent)},
    )


@router.post("/agents/{agent_id}/pause")
def pause_agent_ui(agent_id: str, db: Session = Depends(get_db)):
    Repository(db).pause_agent(agent_id)
    return RedirectResponse("/agents", status_code=303)


@router.post("/agents/{agent_id}/resume")
def resume_agent_ui(agent_id: str, db: Session = Depends(get_db)):
    Repository(db).resume_agent(agent_id)
    return RedirectResponse("/agents", status_code=303)


@router.get("/demo")
def demo_page(request: Request, db: Session = Depends(get_db)):
    repo = Repository(db)
    return templates.TemplateResponse(
        request,
        "demo.html",
        {"sessions": [session_dict(item) for item in repo.list_sessions(10)], "result": None},
    )


@router.post("/demo/run")
async def demo_run_ui(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    scenario = str(form.get("scenario") or "exact-loop")
    mode = str(form.get("mode") or "shadow")
    repo = Repository(db)
    agents = repo.list_agents()
    if not agents:
        raise HTTPException(500, "No agent is available.")
    session = run_demo(repo, agents[-1], scenario, mode)
    return RedirectResponse(f"/sessions/{session.id}", status_code=303)


@router.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html", {"config": request.app.state.config})
