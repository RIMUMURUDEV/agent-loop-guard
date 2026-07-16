from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.issuepilot.core import apply_issue, import_issue, plan_issue
from app.reprolab.core import ReproLab


def test_issuepilot_import_plan_and_explicit_apply(tmp_path: Path) -> None:
    source = tmp_path / "issue.json"
    source.write_text(
        json.dumps(
            {
                "number": 17,
                "title": "Add API validation and security tests",
                "body": "The CLI and API need deterministic tests and documentation.",
                "labels": ["security", "api"],
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "issues"
    issue = import_issue(str(source), root)
    plan = plan_issue(issue["id"], root)

    assert plan["branch"].startswith("codex/issue-17-")
    assert set(plan["areas"]) >= {"API contract", "security boundary", "CLI behavior"}

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init"], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=repository, check=True)
    (repository / "README.md").write_text("test", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repository, check=True, capture_output=True)

    assert (
        subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        != plan["branch"]
    )
    applied = apply_issue(issue["id"], root, repository)
    assert applied["branch"] == plan["branch"]


def test_issuepilot_rejects_unsafe_identifier(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid IssuePilot id"):
        plan_issue("../escape", tmp_path)


def test_reprolab_create_status_and_export_without_docker(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "example.py").write_text("print('ok')\n", encoding="utf-8")
    lab = ReproLab(tmp_path / "repros")

    manifest = lab.create(
        "The example command fails on a clean environment.",
        source,
        test_command="python example.py",
    )
    status = lab.status(manifest["id"])
    assert status["manifest"]["status"] == "created"
    assert status["run"] is None
    assert lab.diff(manifest["id"]) == []

    destination = lab.export(manifest["id"], tmp_path / "repro.zip")
    with zipfile.ZipFile(destination) as archive:
        assert set(archive.namelist()) >= {"manifest.json", "report.md", "diff.json"}


def test_reprolab_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid ReproLab id"):
        ReproLab(tmp_path).status("../escape")

