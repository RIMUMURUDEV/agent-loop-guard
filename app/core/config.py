from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | int | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


@dataclass(slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    admin_ui: bool = True
    storage_url: str = "sqlite:///./data/agent_loop_guard.db"
    retention_days: int = 30
    full_content_logging: bool = False
    body_limit_bytes: int = 1_048_576
    inactive_timeout_seconds: int = 1800
    default_project_id: str = "default"
    default_mode: str = "shadow"
    default_provider: str = "mock"
    allow_mode_header: bool = True
    gateway_key: str = "alg_demo_key"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: str | None = None
    mcp_policy_path: str = "mcp-policy.yml"
    mcp_approval_timeout_seconds: int = 30
    mcp_allowed_origins: list[str] = field(
        default_factory=lambda: ["http://127.0.0.1", "http://localhost"]
    )
    mcp_servers: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "filesystem": {
                "name": "Demo filesystem server",
                "transport": "mock",
                "target": "mock://filesystem",
            }
        }
    )

    @classmethod
    def from_env(cls) -> AppConfig:
        defaults = cls()
        data: dict[str, Any] = {}
        config_path = os.getenv("ALG_CONFIG")
        if config_path and Path(config_path).exists():
            with open(config_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}

        return cls(
            host=os.getenv("ALG_HOST", str(_get(data, "server.host", defaults.host))),
            port=_int(os.getenv("ALG_PORT"), int(_get(data, "server.port", defaults.port))),
            admin_ui=_bool(os.getenv("ALG_ADMIN_UI"), bool(_get(data, "server.admin_ui", True))),
            storage_url=os.getenv(
                "ALG_STORAGE_URL", str(_get(data, "storage.url", defaults.storage_url))
            ),
            retention_days=_int(
                os.getenv("ALG_RETENTION_DAYS"),
                int(_get(data, "storage.retention_days", defaults.retention_days)),
            ),
            full_content_logging=_bool(
                os.getenv("ALG_FULL_CONTENT_LOGGING"),
                bool(_get(data, "storage.full_content_logging", False)),
            ),
            body_limit_bytes=_int(
                os.getenv("ALG_BODY_LIMIT_BYTES"),
                int(_get(data, "server.body_limit_bytes", defaults.body_limit_bytes)),
            ),
            inactive_timeout_seconds=_int(
                os.getenv("ALG_INACTIVE_TIMEOUT_SECONDS"),
                int(
                    _get(
                        data,
                        "server.inactive_timeout_seconds",
                        defaults.inactive_timeout_seconds,
                    )
                ),
            ),
            default_mode=os.getenv("ALG_MODE", str(_get(data, "projects.default.mode", "shadow"))),
            default_provider=os.getenv(
                "ALG_PROVIDER", str(_get(data, "projects.default.provider", "mock"))
            ),
            allow_mode_header=_bool(
                os.getenv("ALG_ALLOW_MODE_HEADER"),
                bool(_get(data, "server.allow_mode_header", True)),
            ),
            gateway_key=os.getenv(
                "ALG_GATEWAY_KEY", str(_get(data, "gateway_key", defaults.gateway_key))
            ),
            openai_base_url=os.getenv(
                "ALG_OPENAI_BASE_URL",
                str(_get(data, "providers.openai.base_url", "https://api.openai.com/v1")),
            ),
            openai_api_key=os.getenv(
                "OPENAI_API_KEY", _get(data, "providers.openai.api_key", None)
            ),
            anthropic_base_url=os.getenv(
                "ALG_ANTHROPIC_BASE_URL",
                str(_get(data, "providers.anthropic.base_url", "https://api.anthropic.com")),
            ),
            anthropic_api_key=os.getenv(
                "ANTHROPIC_API_KEY", _get(data, "providers.anthropic.api_key", None)
            ),
            mcp_policy_path=os.getenv(
                "ALG_MCP_POLICY", str(_get(data, "mcp.policy", defaults.mcp_policy_path))
            ),
            mcp_approval_timeout_seconds=_int(
                os.getenv("ALG_MCP_APPROVAL_TIMEOUT_SECONDS"),
                int(_get(data, "mcp.approval_timeout_seconds", 30)),
            ),
            mcp_allowed_origins=list(
                _get(data, "mcp.allowed_origins", defaults.mcp_allowed_origins)
            ),
            mcp_servers=dict(_get(data, "mcp.servers", defaults.mcp_servers)),
        )

    def ensure_storage_parent(self) -> None:
        if not self.storage_url.startswith("sqlite:///"):
            return
        raw_path = self.storage_url.removeprefix("sqlite:///")
        if raw_path == ":memory:":
            return
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)


SAMPLE_CONFIG = """server:
  host: 127.0.0.1
  port: 8787
  admin_ui: true
  body_limit_bytes: 1048576
  inactive_timeout_seconds: 1800
storage:
  url: sqlite:///./data/agent_loop_guard.db
  retention_days: 30
  full_content_logging: false
gateway_key: alg_demo_key
projects:
  default:
    mode: shadow
    provider: mock
providers:
  mock:
    type: mock
  openai:
    type: openai
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
  anthropic:
    type: anthropic
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
mcp:
  policy: mcp-policy.yml
  approval_timeout_seconds: 30
  allowed_origins:
    - http://127.0.0.1
    - http://localhost
  servers:
    filesystem:
      name: Demo filesystem server
      transport: mock
      target: mock://filesystem
"""
