from __future__ import annotations

from app.benchmark.adapters import MockAdapter
from app.benchmark.dataset import load_dataset, validate_dataset
from app.benchmark.runner import RunLimits, run_benchmark
from app.benchmark.statistics import paired_bootstrap


def test_bundled_dataset_has_balanced_thirty_tasks() -> None:
    payload, tasks = load_dataset()

    assert payload["version"] == "starter-v1"
    assert len(tasks) == 30
    assert {difficulty: sum(task.difficulty == difficulty for task in tasks) for difficulty in ("easy", "medium", "hard")} == {
        "easy": 10,
        "medium": 10,
        "hard": 10,
    }


def test_dataset_validation_rejects_duplicates() -> None:
    errors = validate_dataset(
        {
            "version": "bad-v1",
            "tasks": [
                {"id": "same", "difficulty": "easy", "prompt": "a", "expected": "a"},
                {"id": "same", "difficulty": "easy", "prompt": "b", "expected": "b"},
            ],
        }
    )

    assert "duplicate task id: same" in errors


def test_known_mock_regression_and_inconclusive_result() -> None:
    _, tasks = load_dataset()
    limits = RunLimits(repetitions=1, seed=7)
    baseline = [row.to_dict() for row in run_benchmark(tasks, MockAdapter(), "base", limits)]
    candidate = [
        row.to_dict() for row in run_benchmark(tasks, MockAdapter("regressed"), "new", limits)
    ]

    comparison = paired_bootstrap(baseline, candidate, samples=500, seed=1)
    assert comparison["verdict"] == "regression"
    assert comparison["delta"] < 0

    too_small = paired_bootstrap(baseline[:2], candidate[:2], samples=100, min_pairs=10)
    assert too_small["verdict"] == "inconclusive"


def test_token_budget_stops_new_tasks() -> None:
    _, tasks = load_dataset()
    rows = run_benchmark(
        tasks,
        MockAdapter(),
        "budgeted",
        RunLimits(token_budget=1),
    )

    assert len(rows) == 1
