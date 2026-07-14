from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.common import guarded_proxy
from app.db.session import get_db

router = APIRouter()


@router.post("/v1/responses")
async def responses(request: Request, db: Session = Depends(get_db)) -> Response:
    return await guarded_proxy(request, db, "openai", "/v1/responses")


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, db: Session = Depends(get_db)) -> Response:
    return await guarded_proxy(request, db, "openai", "/v1/chat/completions")


@router.get("/v1/models")
async def models(request: Request, db: Session = Depends(get_db)) -> Response:
    return await guarded_proxy(request, db, "openai", "/v1/models")

