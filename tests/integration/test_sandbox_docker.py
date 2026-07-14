from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.sandbox.workspace import SandboxWorkspace, docker_available


@pytest.mark.skipif(os.getenv("ALG_DOCKER_TEST") != "1", reason="requires explicit Docker test")
def test_offline_container_changes_only_workspace(tmp_path: Path) -> None:
    available, detail = docker_available()
    if not available:
        pytest.skip(detail)
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("original\n", encoding="utf-8")
    manager = SandboxWorkspace(tmp_path / "sandboxes")
    manifest = manager.create(source, "alpine:3.20")

    result = manager.execute(
        manifest["id"],
        [
            "sh",
            "-c",
            "printf 'sandbox\\n' > value.txt; "
            "test ! -e /root/.ssh/id_rsa; "
            "! wget -q -T 2 -O /tmp/network https://example.com",
        ],
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert (source / "value.txt").read_text(encoding="utf-8") == "original\n"
    assert manager.diff(manifest["id"])[0]["status"] == "modified"
