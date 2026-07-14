from __future__ import annotations

from pathlib import Path

import pytest

from app.sandbox.workspace import SandboxWorkspace, build_docker_command


def test_docker_command_is_offline_and_resource_limited(tmp_path: Path) -> None:
    command = build_docker_command(tmp_path, "python:3.12-slim", ["python", "-V"])

    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert "--user" in command
    assert "--pids-limit" in command
    assert "no-new-privileges" in command


def test_command_policy_blocks_container_escape_tools(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="denied"):
        build_docker_command(tmp_path, "python:3.12-slim", ["docker", "run", "busybox"])


def test_workspace_diff_selective_apply_and_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.sandbox.workspace.docker_available", lambda: (True, "test"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "keep.txt").write_text("old\n", encoding="utf-8")
    (source / "delete.txt").write_text("remove\n", encoding="utf-8")
    manager = SandboxWorkspace(tmp_path / "sandboxes")

    manifest = manager.create(source)
    workspace = tmp_path / "sandboxes" / manifest["id"] / "workspace"
    (workspace / "keep.txt").write_text("new\n", encoding="utf-8")
    (workspace / "delete.txt").unlink()
    (workspace / "added.txt").write_text("added\n", encoding="utf-8")

    changes = {item["path"]: item["status"] for item in manager.diff(manifest["id"])}
    assert changes == {"added.txt": "added", "delete.txt": "deleted", "keep.txt": "modified"}
    assert manager.apply(manifest["id"], ["keep.txt", "added.txt"]) == [
        "keep.txt",
        "added.txt",
    ]
    assert (source / "keep.txt").read_text(encoding="utf-8") == "new\n"
    assert (source / "delete.txt").exists()

    manager.discard(manifest["id"])
    assert not (tmp_path / "sandboxes" / manifest["id"]).exists()


def test_apply_refuses_source_changed_after_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.sandbox.workspace.docker_available", lambda: (True, "test"))
    source = tmp_path / "source"
    source.mkdir()
    target = source / "file.txt"
    target.write_text("original", encoding="utf-8")
    manager = SandboxWorkspace(tmp_path / "sandboxes")
    manifest = manager.create(source)
    workspace_file = tmp_path / "sandboxes" / manifest["id"] / "workspace" / "file.txt"
    workspace_file.write_text("sandbox", encoding="utf-8")
    target.write_text("user edit", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Source changed"):
        manager.apply(manifest["id"], ["file.txt"])


def test_create_rejects_symlinks_when_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.sandbox.workspace.docker_available", lambda: (True, "test"))
    source = tmp_path / "source"
    source.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("secret", encoding="utf-8")
    try:
        (source / "escape.txt").symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is unavailable for this Windows account")

    with pytest.raises(ValueError, match="symlink"):
        SandboxWorkspace(tmp_path / "sandboxes").create(source)
