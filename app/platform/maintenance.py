from __future__ import annotations

import json
import shutil
import socket
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.config import AppConfig
from app.db.models import (
    Event,
    GuardSession,
    RequestRecord,
    ToolCall,
    TraceArtifact,
    TraceEvent,
    TraceRun,
    TraceSpan,
)


def sqlite_path(config: AppConfig) -> Path | None:
    if not config.storage_url.startswith("sqlite:///"):
        return None
    raw = config.storage_url.removeprefix("sqlite:///")
    if raw == ":memory:":
        return None
    path = Path(raw)
    return path if path.is_absolute() else Path.cwd() / path


def build_doctor_report(config: AppConfig) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("python", sys.version_info >= (3, 11), sys.version.split()[0])
    storage = sqlite_path(config)
    if storage is None:
        add("storage", True, config.storage_url)
    else:
        try:
            storage.parent.mkdir(parents=True, exist_ok=True)
            add("storage", True, str(storage))
        except OSError as exc:
            add("storage", False, str(exc))

    try:
        with socket.socket() as probe:
            probe.settimeout(0.3)
            available = probe.connect_ex((config.host, config.port)) != 0
        if available:
            add("port", True, f"{config.host}:{config.port} available")
        else:
            status = fetch_status(f"http://{config.host}:{config.port}")
            add(
                "port",
                status["running"],
                f"{config.host}:{config.port} "
                + ("Agent Loop Guard is running" if status["running"] else "used by another process"),
            )
    except OSError as exc:
        add("port", False, str(exc))

    add("docker", shutil.which("docker") is not None, shutil.which("docker") or "not installed")
    add("wsl", shutil.which("wsl") is not None, shutil.which("wsl") or "not installed")
    return {"ok": all(item["ok"] for item in checks if item["name"] != "docker"), "checks": checks}


def fetch_status(base_url: str) -> dict[str, Any]:
    try:
        response = httpx.get(base_url.rstrip("/") + "/api/health", timeout=2)
        response.raise_for_status()
        return {"running": True, "url": base_url, **response.json()}
    except (httpx.HTTPError, ValueError) as exc:
        return {"running": False, "url": base_url, "error": str(exc)}


def create_backup(config: AppConfig, destination: Path, config_path: Path | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "backup.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "storage_url": config.storage_url,
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        storage = sqlite_path(config)
        if storage and storage.exists():
            archive.write(storage, "data/agent_loop_guard.db")
        if config_path and config_path.exists():
            archive.write(config_path, "agent-loop-guard.yml")
    return destination


def restore_backup(config: AppConfig, source: Path, *, force: bool = False) -> Path:
    storage = sqlite_path(config)
    if storage is None:
        raise ValueError("Restore currently supports file-backed SQLite storage only.")
    if storage.exists() and not force:
        raise FileExistsError(f"{storage} exists; pass --force to replace it.")
    with zipfile.ZipFile(source) as archive:
        if "data/agent_loop_guard.db" not in archive.namelist():
            raise ValueError("Backup does not contain a SQLite database.")
        storage.parent.mkdir(parents=True, exist_ok=True)
        with archive.open("data/agent_loop_guard.db") as src, storage.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return storage


def cleanup_old_data(db: Session, retention_days: int) -> dict[str, int]:
    cutoff = datetime.now(UTC) - timedelta(days=max(1, retention_days))
    old_trace_ids = select(TraceRun.id).where(TraceRun.updated_at < cutoff)
    db.execute(delete(TraceArtifact).where(TraceArtifact.trace_id.in_(old_trace_ids)))
    db.execute(delete(TraceEvent).where(TraceEvent.trace_id.in_(old_trace_ids)))
    db.execute(delete(TraceSpan).where(TraceSpan.trace_id.in_(old_trace_ids)))
    trace_result = db.execute(delete(TraceRun).where(TraceRun.updated_at < cutoff))

    old_session_ids = select(GuardSession.id).where(GuardSession.updated_at < cutoff)
    old_request_ids = select(RequestRecord.id).where(RequestRecord.session_id.in_(old_session_ids))
    db.execute(update(TraceRun).where(TraceRun.source_session_id.in_(old_session_ids)).values(source_session_id=None))
    db.execute(delete(ToolCall).where(ToolCall.request_id.in_(old_request_ids)))
    db.execute(delete(Event).where(Event.session_id.in_(old_session_ids)))
    db.execute(delete(RequestRecord).where(RequestRecord.session_id.in_(old_session_ids)))
    session_result = db.execute(delete(GuardSession).where(GuardSession.updated_at < cutoff))
    db.commit()
    return {
        "traces": int(trace_result.rowcount or 0),
        "sessions": int(session_result.rowcount or 0),
    }
