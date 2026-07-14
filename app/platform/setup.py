from __future__ import annotations

import json
import secrets
from pathlib import Path

import yaml

from app.core.config import SAMPLE_CONFIG


def render_profiles(base_url: str, gateway_key: str) -> dict[str, str]:
    openai_url = base_url.rstrip("/") + "/v1"
    return {
        "codex.toml": (
            'model = "demo-model"\n'
            'model_provider = "agent_loop_guard"\n\n'
            "[model_providers.agent_loop_guard]\n"
            'name = "Agent Loop Guard"\n'
            f'base_url = "{openai_url}"\n'
            'env_key = "ALG_GATEWAY_KEY"\n'
        ),
        "claude.env": (
            f"ANTHROPIC_BASE_URL={base_url.rstrip('/')}\n"
            f"ANTHROPIC_AUTH_TOKEN={gateway_key}\n"
        ),
        "cline.txt": (
            "API Provider: OpenAI Compatible\n"
            f"Base URL: {openai_url}\n"
            f"API Key: {gateway_key}\n"
            "Model ID: demo-model\n"
        ),
        "opencode.json": json.dumps(
            {
                "provider": {
                    "alg": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Agent Loop Guard",
                        "options": {"baseURL": openai_url, "apiKey": "{env:ALG_GATEWAY_KEY}"},
                        "models": {"demo-model": {"name": "Guarded model"}},
                    }
                },
                "model": "alg/demo-model",
            },
            indent=2,
        )
        + "\n",
    }


def setup_workspace(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    gateway_key: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    config_path = root / "agent-loop-guard.yml"
    profiles_dir = root / ".agent-loop-guard" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    if config_path.exists() and not force:
        config_written = False
        existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        effective_gateway_key = str(existing.get("gateway_key") or gateway_key or "alg_demo_key")
    else:
        effective_gateway_key = gateway_key or f"alg_{secrets.token_urlsafe(24)}"
        config_text = SAMPLE_CONFIG.replace(
            "gateway_key: alg_demo_key", f"gateway_key: {effective_gateway_key}"
        )
        config_text = config_text.replace("host: 127.0.0.1", f"host: {host}", 1)
        config_text = config_text.replace("port: 8787", f"port: {port}", 1)
        config_path.write_text(config_text, encoding="utf-8")
        config_written = True

    base_url = f"http://{host}:{port}"
    written_profiles = []
    for name, content in render_profiles(base_url, effective_gateway_key).items():
        path = profiles_dir / name
        if force or not path.exists():
            path.write_text(content, encoding="utf-8")
        written_profiles.append(str(path))

    return {
        "config": str(config_path),
        "config_written": config_written,
        "profiles": written_profiles,
        "base_url": base_url,
        "gateway_key": effective_gateway_key if config_written else None,
    }
