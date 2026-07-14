from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

from app.benchmark.adapters import BenchmarkAdapter
from app.benchmark.models import BenchmarkTask, Observation
from app.benchmark.scorers import score_output


@dataclass(slots=True)
class RunLimits:
    repetitions: int = 1
    seed: int = 0
    timeout_seconds: float = 30.0
    token_budget: int = 0
    cost_budget_micros: int = 0


def run_benchmark(
    tasks: list[BenchmarkTask],
    adapter: BenchmarkAdapter,
    candidate: str,
    limits: RunLimits,
) -> list[Observation]:
    run_id = f"bench_{uuid.uuid4().hex[:24]}"
    observations: list[Observation] = []
    used_tokens = 0
    used_cost = 0
    for repetition in range(limits.repetitions):
        for task in tasks:
            if limits.token_budget and used_tokens >= limits.token_budget:
                return observations
            if limits.cost_budget_micros and used_cost >= limits.cost_budget_micros:
                return observations
            seed = limits.seed + repetition
            started = time.perf_counter_ns()
            result = adapter.execute(task, seed, limits.timeout_seconds)
            duration_ms = max(0, int((time.perf_counter_ns() - started) / 1_000_000))
            score = 0.0 if result.error else score_output(task.scorer, result.output, task.expected)
            used_tokens += result.input_tokens + result.output_tokens
            used_cost += result.cost_micros
            observations.append(
                Observation(
                    run_id=run_id,
                    candidate=candidate,
                    task_id=task.id,
                    difficulty=task.difficulty,
                    repetition=repetition,
                    seed=seed,
                    score=score,
                    duration_ms=duration_ms,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_micros=result.cost_micros,
                    output_hash=hashlib.sha256(result.output.encode("utf-8")).hexdigest(),
                    error=result.error,
                    metadata={"dataset.tags": task.tags},
                )
            )
    return observations
