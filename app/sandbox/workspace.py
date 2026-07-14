from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.sandbox.policy import validate_command

IGNORED_NAMES = {".git", ".agent-loop-guard", ".venv", "node_modules", "__pycache__"}
SESSION_PATTERN = re.compile(r"^sbx_[a-f0-9]{24}$")


def docker_available() -> tuple[bool, str]:
    executable = shutil.which("docker")
    if not executable:
        return False, "Docker CLI is not installed. Install Docker in WSL2 or Docker Desktop first."
    try:
        result = subprocess.run(
            [executable, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode:
        return False, result.stderr.strip() or "Docker daemon is not available."
    return True, result.stdout.strip()


def build_docker_command(
    workspace: Path,
    image: str,
    command: list[str],
    *,
    network: str = "none",
    cpus: float = 1.0,
    memory: str = "1g",
    pids: int = 128,
) -> list[str]:
    validate_command(command)
    user = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "1000:1000"
    return [
        "docker",
        "run",
        "--rm",
        "--init",
        "--user",
        user,
        "--network",
        network,
        "--cpus",
        str(cpus),
        "--memory",
        memory,
        "--pids-limit",
        str(pids),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=128m",
        "--mount",
        f"type=bind,source={workspace.resolve()},target=/workspace",
        "--workdir",
        "/workspace",
        image,
        *command,
    ]


class SandboxWorkspace:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(".agent-loop-guard/sandboxes")).resolve()

    def create(self, source: Path, image: str = "python:3.12-slim") -> dict[str, Any]:
        available, detail = docker_available()
        if not available:
            raise RuntimeError(detail)
        source = source.resolve()
        _ensure_safe_source(source)
        session_id = f"sbx_{uuid.uuid4().hex[:24]}"
        session_root = self.root / session_id
        snapshot = session_root / "snapshot"
        workspace = session_root / "workspace"
        session_root.mkdir(parents=True)
        _copy_tree(source, snapshot)
        _copy_tree(source, workspace)
        manifest = {
            "schema_version": "sandbox.v1",
            "id": session_id,
            "source": str(source),
            "image": image,
            "docker_version": detail,
            "created_at": datetime.now(UTC).isoformat(),
            "original_hashes": _file_hashes(snapshot),
        }
        _write_manifest(session_root, manifest)
        return manifest

    def execute(
        self,
        session_id: str,
        command: list[str],
        *,
        timeout: float = 300,
        network: str = "none",
        cpus: float = 1.0,
        memory: str = "1g",
        pids: int = 128,
    ) -> subprocess.CompletedProcess[str]:
        session_root, manifest = self._load(session_id)
        docker_command = build_docker_command(
            session_root / "workspace",
            str(manifest["image"]),
            command,
            network=network,
            cpus=cpus,
            memory=memory,
            pids=pids,
        )
        try:
            return subprocess.run(
                docker_command,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Sandbox command timed out after {timeout:g}s") from exc

    def diff(self, session_id: str) -> list[dict[str, Any]]:
        session_root, _ = self._load(session_id)
        snapshot = session_root / "snapshot"
        workspace = session_root / "workspace"
        before = _file_hashes(snapshot)
        after = _file_hashes(workspace)
        rows = []
        for path in sorted(set(before) | set(after)):
            status = "added" if path not in before else "deleted" if path not in after else "modified"
            if before.get(path) == after.get(path):
                continue
            rows.append(
                {
                    "path": path,
                    "status": status,
                    "before_sha256": before.get(path),
                    "after_sha256": after.get(path),
                    "patch": _text_diff(snapshot / path, workspace / path, path),
                }
            )
        return rows

    def apply(self, session_id: str, paths: list[str] | None = None) -> list[str]:
        session_root, manifest = self._load(session_id)
        source = Path(str(manifest["source"])).resolve()
        snapshot = session_root / "snapshot"
        workspace = session_root / "workspace"
        changes = {item["path"]: item for item in self.diff(session_id)}
        selected = sorted(changes) if paths is None else paths
        unknown = sorted(set(selected) - set(changes))
        if unknown:
            raise ValueError(f"Paths are not changed: {', '.join(unknown)}")
        applied = []
        for relative in selected:
            source_path = _contained(source, relative)
            snapshot_path = _contained(snapshot, relative)
            workspace_path = _contained(workspace, relative)
            expected = _hash_file(snapshot_path) if snapshot_path.is_file() else None
            current = _hash_file(source_path) if source_path.is_file() else None
            if current != expected:
                raise RuntimeError(f"Source changed since sandbox creation: {relative}")
            if workspace_path.is_symlink():
                raise RuntimeError(f"Refusing to apply symlink: {relative}")
            if changes[relative]["status"] == "deleted":
                source_path.unlink(missing_ok=True)
            else:
                source_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(workspace_path, source_path)
            applied.append(relative)
        return applied

    def discard(self, session_id: str) -> None:
        session_root, _ = self._load(session_id)
        shutil.rmtree(session_root)

    def export(self, session_id: str, destination: Path) -> Path:
        session_root, _ = self._load(session_id)
        destination = destination.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(session_root / "manifest.json", "manifest.json")
            archive.writestr("diff.json", json.dumps(self.diff(session_id), indent=2))
            for path in (session_root / "workspace").rglob("*"):
                if path.is_file() and not path.is_symlink():
                    archive.write(path, Path("workspace") / path.relative_to(session_root / "workspace"))
        return destination

    def _load(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        if not SESSION_PATTERN.fullmatch(session_id):
            raise ValueError("Invalid sandbox id")
        session_root = (self.root / session_id).resolve()
        if session_root.parent != self.root or not session_root.is_dir():
            raise FileNotFoundError(f"Sandbox not found: {session_id}")
        manifest = json.loads((session_root / "manifest.json").read_text(encoding="utf-8"))
        return session_root, manifest


def _ensure_safe_source(source: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")
    for path in source.rglob("*"):
        if any(part in IGNORED_NAMES for part in path.relative_to(source).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Source contains a symlink; sandbox creation refused: {path}")


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return set(names) & IGNORED_NAMES


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=_ignore)


def _write_manifest(session_root: Path, manifest: dict[str, Any]) -> None:
    (session_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _hash_file(path)
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contained(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"Unsafe relative path: {relative}")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace: {relative}") from exc
    return candidate


def _text_diff(before: Path, after: Path, label: str) -> str | None:
    try:
        before_text = before.read_text(encoding="utf-8").splitlines(keepends=True) if before.exists() else []
        after_text = after.read_text(encoding="utf-8").splitlines(keepends=True) if after.exists() else []
    except (OSError, UnicodeDecodeError):
        return None
    return "".join(
        difflib.unified_diff(before_text, after_text, fromfile=f"a/{label}", tofile=f"b/{label}")
    )
