from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.admin_routes import router as admin_router
from app.api.anthropic_routes import router as anthropic_router
from app.api.mcp_routes import router as mcp_router
from app.api.openai_routes import router as openai_router
from app.api.replay_routes import router as replay_router
from app.api.ui_routes import router as ui_router
from app.core.config import AppConfig
from app.db.session import build_engine, build_session_factory, init_db


def create_app(config: AppConfig | None = None) -> FastAPI:
    config = config or AppConfig.from_env()
    engine = build_engine(config)
    init_db(engine, config)

    app = FastAPI(
        title="Agent Loop Guard",
        version="0.6.0a1",
        description="Local runtime guard for coding agents.",
    )
    app.state.config = config
    app.state.engine = engine
    app.state.SessionLocal = build_session_factory(engine)
    app.state.mcp_upstream_sessions = {}

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > config.body_limit_bytes:
            return JSONResponse({"error": "Request body too large."}, status_code=413)
        return await call_next(request)

    @app.head("/")
    async def connectivity_probe() -> Response:
        return Response(status_code=204)

    app.include_router(openai_router)
    app.include_router(anthropic_router)
    app.include_router(admin_router)
    app.include_router(replay_router)
    app.include_router(mcp_router)

    if config.admin_ui:
        static_dir = Path(__file__).resolve().parent / "static"
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        app.include_router(ui_router)

    return app


app = create_app()
