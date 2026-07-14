from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class BenchmarkTask:
    id: str
    difficulty: str
    prompt: str
    expected: Any
    scorer: str = "exact"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdapterResult:
    output: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int = 0
    error: str | None = None


@dataclass(slots=True)
class Observation:
    run_id: str
    candidate: str
    task_id: str
    difficulty: str
    repetition: int
    seed: int
    score: float
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cost_micros: int
    output_hash: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

