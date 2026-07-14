from __future__ import annotations

import json
import random
import shlex
import subprocess
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.benchmark.models import AdapterResult, BenchmarkTask


def _tokens(value: str) -> int:
    return max(1, (len(value) + 3) // 4)


class BenchmarkAdapter(ABC):
    @abstractmethod
    def execute(self, task: BenchmarkTask, seed: int, timeout: float) -> AdapterResult:
        raise NotImplementedError


class MockAdapter(BenchmarkAdapter):
    def __init__(self, variant: str = "baseline") -> None:
        self.variant = variant

    def execute(self, task: BenchmarkTask, seed: int, timeout: float) -> AdapterResult:
        del timeout
        output = json.dumps(task.expected, sort_keys=True) if task.scorer == "json_equal" else str(task.expected)
        if self.variant == "regressed" and task.difficulty in {"medium", "hard"}:
            output = f"incorrect-{random.Random(f'{seed}:{task.id}').randrange(1000)}"
        return AdapterResult(output, _tokens(task.prompt), _tokens(output))


class HTTPAdapter(BenchmarkAdapter):
    def __init__(self, endpoint: str, model: str, api_key: str | None = None) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key

    def execute(self, task: BenchmarkTask, seed: int, timeout: float) -> AdapterResult:
        headers = {"authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = httpx.post(
                self.endpoint,
                headers=headers,
                json={"model": self.model, "input": task.prompt, "seed": seed},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            output = _response_text(payload)
            usage = payload.get("usage") or {}
            return AdapterResult(
                output=output,
                input_tokens=int(usage.get("input_tokens") or _tokens(task.prompt)),
                output_tokens=int(usage.get("output_tokens") or _tokens(output)),
            )
        except (httpx.HTTPError, ValueError) as exc:
            return AdapterResult("", error=str(exc))


class CLIAdapter(BenchmarkAdapter):
    def __init__(self, command: str | list[str]) -> None:
        self.command = shlex.split(command) if isinstance(command, str) else command

    def execute(self, task: BenchmarkTask, seed: int, timeout: float) -> AdapterResult:
        try:
            process = subprocess.run(
                self.command,
                input=json.dumps({"prompt": task.prompt, "seed": seed}),
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return AdapterResult("", error=str(exc))
        if process.returncode:
            return AdapterResult("", error=process.stderr.strip() or f"exit {process.returncode}")
        output = process.stdout.strip()
        return AdapterResult(output, _tokens(task.prompt), _tokens(output))


def _response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            if isinstance(content.get("text"), str):
                return content["text"]
    choices = payload.get("choices") or []
    if choices:
        return str((choices[0].get("message") or {}).get("content") or choices[0].get("text") or "")
    return ""
