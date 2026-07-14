from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.common import guarded_proxy
from app.db.session import get_db

router = APIRouter()


@router.post("/v1/messages")
async def messages(request: Request, db: Session = Depends(get_db)) -> Response:
    return await guarded_proxy(request, db, "anthropic", "/v1/messages")


@router.post("/v1/messages/count_tokens")
async def count_tokens(request: Request, db: Session = Depends(get_db)) -> Response:
    return await guarded_proxy(request, db, "anthropic", "/v1/messages/count_tokens")

