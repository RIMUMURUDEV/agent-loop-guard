from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_pricing(path: str | Path | None = None) -> dict[str, dict[str, int]]:
    selected = Path(path or os.getenv("ALG_MODEL_PRICING", "model-pricing.yml"))
    if not selected.exists():
        return {"demo-model": {"input_micros_per_million": 0, "output_micros_per_million": 0}}
    with selected.open(encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle) or {}
    return {
        str(model): {
            "input_micros_per_million": int(row.get("input_micros_per_million", 0)),
            "output_micros_per_million": int(row.get("output_micros_per_million", 0)),
        }
        for model, row in (data.get("models") or {}).items()
        if isinstance(row, dict)
    }


def estimate_cost_micros(
    model: str | None, input_tokens: int, output_tokens: int, pricing: dict | None = None
) -> tuple[int, bool]:
    catalog = pricing or load_pricing()
    row = catalog.get(model or "")
    if not row:
        return 0, True
    total = (
        input_tokens * int(row.get("input_micros_per_million", 0))
        + output_tokens * int(row.get("output_micros_per_million", 0))
    ) // 1_000_000
    return total, True
