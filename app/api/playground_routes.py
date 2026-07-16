from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.repository import Repository
from app.db.session import get_db
from app.playground.service import list_scenarios, playground_run, run_scenario

router = APIRouter(prefix="/api/v1/playground", tags=["playground"])


class PlaygroundRequest(BaseModel):
    scenario: str = "exact-loop"
    mode: str = "shadow"


@router.get("/scenarios")
def scenarios() -> list[dict]:
    return list_scenarios()


@router.post("/runs")
def create_run(payload: PlaygroundRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return run_scenario(Repository(db), payload.scenario, payload.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        return playground_run(Repository(db), run_id)
    except KeyError as exc:
        raise HTTPException(404, "Playground run not found.") from exc

