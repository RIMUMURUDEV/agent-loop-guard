from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.parse
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ISSUE_ID_PATTERN = re.compile(r"^iss_[a-f0-9]{16}$")
GITHUB_ISSUE_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/?$"
)


def import_issue(source: str, root: Path, *, token: str | None = None) -> dict[str, Any]:
    payload = _load_issue(source, token=token)
    issue_id = "iss_" + hashlib.sha256(
        f"{payload.get('url')}:{payload.get('number')}:{payload.get('title')}".encode()
    ).hexdigest()[:16]
    directory = _issue_directory(root, issue_id)
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "issuepilot.issue.v1",
        "id": issue_id,
        "source": source,
        "url": payload.get("url"),
        "repository": payload.get("repository"),
        "number": payload.get("number"),
        "title": str(payload.get("title") or "Untitled issue"),
        "body": str(payload.get("body") or ""),
        "labels": [str(item) for item in payload.get("labels") or []],
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_json(directory / "issue.json", record)
    return record


def plan_issue(issue_id: str, root: Path) -> dict[str, Any]:
    issue = load_issue(issue_id, root)
    title = issue["title"]
    body = issue["body"]
    labels = issue["labels"]
    combined = f"{title}\n{body}\n{' '.join(labels)}".lower()
    areas = []
    for keyword, area in (
        ("api", "API contract"),
        ("cli", "CLI behavior"),
        ("security", "security boundary"),
        ("database", "data model"),
        ("migration", "migration path"),
        ("ui", "user interface"),
        ("test", "test coverage"),
        ("doc", "documentation"),
    ):
        if keyword in combined and area not in areas:
            areas.append(area)
    if not areas:
        areas = ["core behavior", "test coverage", "documentation"]
    slug = _slug(title)
    branch = f"codex/issue-{issue.get('number') or issue_id[-6:]}-{slug}"[:96].rstrip("-")
    checklist = [
        f"Confirm the expected behavior for {area}." for area in areas
    ] + [
        "Implement the smallest complete change using existing project patterns.",
        "Add regression tests for the reported behavior and failure path.",
        "Update user-facing documentation and release notes where applicable.",
    ]
    acceptance = [
        "The reported scenario has a deterministic automated test.",
        "Existing tests continue to pass.",
        "No secrets or full issue body are written to Replay metadata.",
        "The implementation and limitations are documented.",
    ]
    plan = {
        "schema_version": "issuepilot.plan.v1",
        "issue_id": issue_id,
        "title": title,
        "branch": branch,
        "summary": f"Resolve: {title}",
        "areas": areas,
        "checklist": checklist,
        "acceptance_criteria": acceptance,
        "generated_at": datetime.now(UTC).isoformat(),
        "applied": False,
    }
    directory = _issue_directory(root, issue_id)
    _write_json(directory / "plan.json", plan)
    (directory / "PLAN.md").write_text(_plan_markdown(plan), encoding="utf-8")
    return plan


def apply_issue(issue_id: str, root: Path, repository: Path) -> dict[str, Any]:
    plan = load_plan(issue_id, root)
    repository = repository.resolve()
    if not (repository / ".git").exists():
        raise ValueError(f"Not a Git repository: {repository}")
    branch = str(plan["branch"])
    existing = subprocess.run(
        ["git", "branch", "--list", branch],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if existing.returncode:
        raise RuntimeError(existing.stderr.strip() or "Unable to inspect Git branches.")
    if existing.stdout.strip():
        command = ["git", "switch", branch]
    else:
        command = ["git", "switch", "-c", branch]
    result = subprocess.run(
        command,
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Unable to switch Git branch.")
    plan["applied"] = True
    plan["applied_at"] = datetime.now(UTC).isoformat()
    plan["repository"] = str(repository)
    _write_json(_issue_directory(root, issue_id) / "plan.json", plan)
    return {"issue_id": issue_id, "branch": branch, "repository": str(repository)}


def export_issue(issue_id: str, root: Path, destination: Path) -> Path:
    directory = _issue_directory(root, issue_id)
    if not directory.is_dir():
        raise FileNotFoundError(f"IssuePilot record not found: {issue_id}")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in directory.iterdir():
            if path.is_file():
                archive.write(path, path.name)
    return destination


def load_issue(issue_id: str, root: Path) -> dict[str, Any]:
    return _read_record(root, issue_id, "issue.json")


def load_plan(issue_id: str, root: Path) -> dict[str, Any]:
    return _read_record(root, issue_id, "plan.json")


def _load_issue(source: str, *, token: str | None) -> dict[str, Any]:
    match = GITHUB_ISSUE_PATTERN.fullmatch(source)
    if match:
        headers = {"accept": "application/vnd.github+json", "user-agent": "agent-loop-guard"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        url = (
            f"https://api.github.com/repos/{match['owner']}/{match['repo']}"
            f"/issues/{match['number']}"
        )
        response = httpx.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if "pull_request" in payload:
            raise ValueError("Pull requests are not supported by IssuePilot import.")
        return {
            "url": payload.get("html_url") or source,
            "repository": f"{match['owner']}/{match['repo']}",
            "number": int(match["number"]),
            "title": payload.get("title"),
            "body": payload.get("body"),
            "labels": [item.get("name") for item in payload.get("labels") or []],
        }
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Issue JSON not found: {source}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Issue JSON must contain an object.")
    url = str(payload.get("url") or payload.get("html_url") or path.resolve())
    parsed = urllib.parse.urlparse(url)
    return {
        "url": url,
        "repository": payload.get("repository") or parsed.netloc or "local",
        "number": payload.get("number"),
        "title": payload.get("title"),
        "body": payload.get("body"),
        "labels": [
            item.get("name") if isinstance(item, dict) else item
            for item in payload.get("labels") or []
        ],
    }


def _issue_directory(root: Path, issue_id: str) -> Path:
    if not ISSUE_ID_PATTERN.fullmatch(issue_id):
        raise ValueError("Invalid IssuePilot id.")
    return root.resolve() / issue_id


def _read_record(root: Path, issue_id: str, name: str) -> dict[str, Any]:
    path = _issue_directory(root, issue_id) / name
    if not path.is_file():
        raise FileNotFoundError(f"IssuePilot {name} not found for {issue_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "work"


def _plan_markdown(plan: dict[str, Any]) -> str:
    checklist = "\n".join(f"- [ ] {item}" for item in plan["checklist"])
    acceptance = "\n".join(f"- {item}" for item in plan["acceptance_criteria"])
    return (
        f"# {plan['summary']}\n\n"
        f"Branch: `{plan['branch']}`\n\n"
        f"## Checklist\n\n{checklist}\n\n"
        f"## Acceptance Criteria\n\n{acceptance}\n"
    )

