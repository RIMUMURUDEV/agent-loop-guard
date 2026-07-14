from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Any


def paired_bootstrap(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    samples: int = 2000,
    seed: int = 0,
    min_pairs: int = 10,
    regression_threshold: float = 0.0,
) -> dict[str, Any]:
    left = _scores_by_key(baseline)
    right = _scores_by_key(candidate)
    keys = sorted(set(left) & set(right))
    differences = [right[key] - left[key] for key in keys]
    result: dict[str, Any] = {
        "schema_version": "benchmark.compare.v1",
        "pairs": len(differences),
        "baseline_mean": mean(left[key] for key in keys) if keys else None,
        "candidate_mean": mean(right[key] for key in keys) if keys else None,
        "delta": mean(differences) if differences else None,
        "confidence": 0.95,
        "threshold": regression_threshold,
    }
    if len(differences) < min_pairs:
        return {**result, "ci_low": None, "ci_high": None, "verdict": "inconclusive"}
    rng = random.Random(seed)
    bootstrapped = sorted(
        mean(differences[rng.randrange(len(differences))] for _ in differences)
        for _ in range(samples)
    )
    low = bootstrapped[int(samples * 0.025)]
    high = bootstrapped[min(samples - 1, int(samples * 0.975))]
    verdict = "regression" if high < -regression_threshold else "no_regression"
    return {**result, "ci_low": low, "ci_high": high, "verdict": verdict}


def _scores_by_key(rows: list[dict[str, Any]]) -> dict[tuple[str, int], float]:
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["task_id"]), int(row.get("repetition", 0)))].append(float(row["score"]))
    return {key: mean(values) for key, values in grouped.items()}
