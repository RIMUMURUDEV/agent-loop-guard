from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.benchmark.models import BenchmarkTask

VALID_DIFFICULTIES = {"easy", "medium", "hard"}
VALID_SCORERS = {"exact", "contains", "json_equal"}


def bundled_dataset_path() -> Path:
    return Path(__file__).with_name("data") / "starter-v1.json"


def load_dataset(path: str | Path | None = None) -> tuple[dict[str, Any], list[BenchmarkTask]]:
    source = Path(path) if path else bundled_dataset_path()
    payload = json.loads(source.read_text(encoding="utf-8"))
    errors = validate_dataset(payload)
    if errors:
        raise ValueError("; ".join(errors))
    tasks = [BenchmarkTask(**item) for item in payload["tasks"]]
    return payload, tasks


def validate_dataset(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return ["dataset must be a JSON object"]
    errors: list[str] = []
    if not isinstance(payload.get("version"), str) or not payload["version"].strip():
        errors.append("version must be a non-empty string")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return errors + ["tasks must be a non-empty array"]
    seen: set[str] = set()
    for index, task in enumerate(tasks):
        prefix = f"tasks[{index}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"{prefix}.id must be a non-empty string")
        elif task_id in seen:
            errors.append(f"duplicate task id: {task_id}")
        else:
            seen.add(task_id)
        if task.get("difficulty") not in VALID_DIFFICULTIES:
            errors.append(f"{prefix}.difficulty must be easy, medium, or hard")
        if not isinstance(task.get("prompt"), str) or not task["prompt"]:
            errors.append(f"{prefix}.prompt must be a non-empty string")
        scorer = str(task.get("scorer") or "exact")
        if scorer not in VALID_SCORERS and not scorer.startswith("python:"):
            errors.append(f"{prefix}.scorer is unsupported: {scorer}")
        if "expected" not in task:
            errors.append(f"{prefix}.expected is required")
    return errors

