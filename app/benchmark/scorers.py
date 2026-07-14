from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import Any


def score_output(scorer: str, output: str, expected: Any) -> float:
    if scorer == "exact":
        return float(output.strip() == str(expected).strip())
    if scorer == "contains":
        return float(str(expected).strip().lower() in output.strip().lower())
    if scorer == "json_equal":
        try:
            return float(json.loads(output) == expected)
        except (json.JSONDecodeError, TypeError):
            return 0.0
    if scorer.startswith("python:"):
        function = _load_custom_scorer(scorer.removeprefix("python:"))
        value = float(function(output, expected))
        return min(1.0, max(0.0, value))
    raise ValueError(f"Unsupported scorer: {scorer}")


def _load_custom_scorer(reference: str) -> Callable[[str, Any], float]:
    module_name, separator, function_name = reference.partition(":")
    if not separator:
        raise ValueError("Custom scorer must use python:module:function")
    function = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(function):
        raise ValueError(f"Custom scorer is not callable: {reference}")
    return function

