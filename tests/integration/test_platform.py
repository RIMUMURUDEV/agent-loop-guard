from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import AppConfig
from app.db.models import Event, GuardSession, RequestRecord, ToolCall, TraceRun
from app.main import create_app
from app.platform.maintenance import cleanup_old_data
from app.platform.setup import setup_workspace


def test_setup_generates_redacted_agent_profiles(tmp_path: Path) -> None:
    result = setup_workspace(tmp_path, gateway_key="alg_test_setup_secret")

    assert Path(str(result["config"])).exists()
    profile_names = {Path(path).name for path in result["profiles"]}
    assert profile_names == {"codex.toml", "claude.env", "cline.txt", "opencode.json"}
    assert "agent_loop_guard" in (tmp_path / ".agent-loop-guard/profiles/codex.toml").read_text(
        encoding="utf-8"
    )

    claude = tmp_path / ".agent-loop-guard/profiles/claude.env"
    claude.unlink()
    setup_workspace(tmp_path)
    assert "alg_test_setup_secret" in claude.read_text(encoding="utf-8")


def test_retention_cleanup_deletes_children_before_parents(tmp_path: Path) -> None:
    config = AppConfig(
        storage_url=f"sqlite:///{tmp_path / 'cleanup.db'}",
        gateway_key="alg_cleanup_key",
        default_provider="mock",
    )
    app = create_app(config)
    with TestClient(app) as client:
        response = client.post(
            "/v1/responses",
            headers={"authorization": "Bearer alg_cleanup_key", "x-alg-session-id": "cleanup"},
            json={"model": "demo-model", "input": "cleanup test"},
        )
        assert response.status_code == 200

    old = datetime.now(UTC) - timedelta(days=90)
    with app.state.SessionLocal() as db:
        session = db.scalar(select(GuardSession))
        trace = db.scalar(select(TraceRun))
        assert session is not None and trace is not None
        session.updated_at = old
        trace.updated_at = old
        db.commit()

        result = cleanup_old_data(db, 30)
        assert result == {"traces": 1, "sessions": 1}
        for model in (GuardSession, RequestRecord, ToolCall, Event, TraceRun):
            assert db.scalar(select(func.count()).select_from(model)) == 0
