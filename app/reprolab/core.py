from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.sandbox.workspace import SandboxWorkspace

REPRO_ID_PREFIX = "rpr_"


class ReproLab:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(".agent-loop-guard/repros")).resolve()

    def create(
        self,
        report: str,
        source: Path,
        *,
        setup_command: str | None = None,
        test_command: str = "python -m pytest -q",
        image: str = "python:3.12-slim",
    ) -> dict[str, Any]:
        source = source.resolve()
        if not source.is_dir():
            raise ValueError(f"Source directory does not exist: {source}")
        report_text = _report_text(report)
        repro_id = REPRO_ID_PREFIX + hashlib.sha256(
            f"{source}:{report_text}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:20]
        directory = self._directory(repro_id)
        directory.mkdir(parents=True)
        manifest = {
            "schema_version": "reprolab.v1",
            "id": repro_id,
            "status": "created",
            "source": str(source),
            "image": image,
            "setup_command": setup_command,
            "test_command": test_command,
            "report_sha256": hashlib.sha256(report_text.encode()).hexdigest(),
            "created_at": datetime.now(UTC).isoformat(),
            "environment": _environment(),
        }
        (directory / "report.md").write_text(report_text, encoding="utf-8")
        self._write_manifest(directory, manifest)
        return manifest

    def run(self, repro_id: str, *, timeout: float = 300) -> dict[str, Any]:
        directory, manifest = self._load(repro_id)
        manager = SandboxWorkspace(directory / "sandboxes")
        sandbox = manager.create(Path(manifest["source"]), str(manifest["image"]))
        commands = [
            value
            for value in (manifest.get("setup_command"), manifest.get("test_command"))
            if value
        ]
        results = []
        for value in commands:
            command = shlex.split(str(value), posix=os.name != "nt")
            completed = manager.execute(sandbox["id"], command, timeout=timeout)
            results.append(
                {
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-20000:],
                    "stderr": completed.stderr[-20000:],
                }
            )
            if completed.returncode:
                break
        manifest["status"] = "passed" if results and all(not row["returncode"] for row in results) else "failed"
        manifest["sandbox_id"] = sandbox["id"]
        manifest["completed_at"] = datetime.now(UTC).isoformat()
        _write_json(directory / "run.json", {"results": results})
        self._write_manifest(directory, manifest)
        return self.status(repro_id)

    def status(self, repro_id: str) -> dict[str, Any]:
        directory, manifest = self._load(repro_id)
        run_path = directory / "run.json"
        return {
            "manifest": manifest,
            "run": json.loads(run_path.read_text(encoding="utf-8")) if run_path.exists() else None,
        }

    def diff(self, repro_id: str) -> list[dict[str, Any]]:
        directory, manifest = self._load(repro_id)
        sandbox_id = manifest.get("sandbox_id")
        if not sandbox_id:
            return []
        return SandboxWorkspace(directory / "sandboxes").diff(str(sandbox_id))

    def export(self, repro_id: str, destination: Path) -> Path:
        directory, _ = self._load(repro_id)
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        diff = self.diff(repro_id)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("manifest.json", "report.md", "run.json"):
                path = directory / name
                if path.exists():
                    archive.write(path, name)
            archive.writestr("diff.json", json.dumps(diff, indent=2))
        return destination

    def _directory(self, repro_id: str) -> Path:
        if not repro_id.startswith(REPRO_ID_PREFIX) or not repro_id[4:].isalnum():
            raise ValueError("Invalid ReproLab id.")
        directory = (self.root / repro_id).resolve()
        if directory.parent != self.root:
            raise ValueError("ReproLab path escapes the local root.")
        return directory

    def _load(self, repro_id: str) -> tuple[Path, dict[str, Any]]:
        directory = self._directory(repro_id)
        path = directory / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"ReproLab package not found: {repro_id}")
        return directory, json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_manifest(directory: Path, payload: dict[str, Any]) -> None:
        _write_json(directory / "manifest.json", payload)


def _report_text(value: str) -> str:
    try:
        path = Path(value)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return value.strip() or "No bug report details were provided."


def _environment() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "architecture": platform.machine(),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
