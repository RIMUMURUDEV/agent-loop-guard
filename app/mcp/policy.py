from __future__ import annotations

import fnmatch
import hashlib
import json
import shlex
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

ALLOWED_ACTIONS = {"allow", "deny", "confirm", "transform", "rate_limit", "shadow_deny"}
PATH_KEYS = {"path", "file", "filepath", "file_path", "directory", "cwd", "root"}


class MCPPolicyError(ValueError):
    pass


@dataclass(slots=True)
class MCPDecision:
    action: str
    reason: str
    rule_id: str
    policy_version: str
    arguments: dict[str, Any]
    argument_hash: str
    mode: str = "enforce"
    risk_tags: list[str] = field(default_factory=list)
    transformed_fields: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.action in {"allow", "transform", "shadow_deny"}


def argument_fingerprint(arguments: dict[str, Any]) -> str:
    normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_policy(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if int(data.get("version", 0)) < 1:
        errors.append("version must be a positive integer")
    default_action = str(data.get("default_action", "confirm"))
    if default_action not in ALLOWED_ACTIONS:
        errors.append(f"unsupported default_action: {default_action}")
    servers = data.get("servers", {})
    if not isinstance(servers, dict):
        errors.append("servers must be an object")
        return errors
    for server_id, server in servers.items():
        if not isinstance(server, dict):
            errors.append(f"servers.{server_id} must be an object")
            continue
        for tool_name, rule in (server.get("tools") or {}).items():
            if not isinstance(rule, dict):
                errors.append(f"servers.{server_id}.tools.{tool_name} must be an object")
                continue
            action = str(rule.get("action", default_action))
            if action not in ALLOWED_ACTIONS:
                errors.append(f"servers.{server_id}.tools.{tool_name}: unsupported action {action}")
    return errors


def load_policy(path: str | Path | None = None) -> tuple[dict[str, Any], Path | None]:
    if path is None:
        return default_policy(), None
    policy_path = Path(path)
    if not policy_path.exists():
        return default_policy(), policy_path
    with policy_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    errors = validate_policy(data)
    if errors:
        raise MCPPolicyError("; ".join(errors))
    return data, policy_path


def default_policy() -> dict[str, Any]:
    return {
        "version": 1,
        "default_action": "confirm",
        "mode": "enforce",
        "hide_denied_tools": True,
        "servers": {
            "filesystem": {
                "tools": {
                    "read_file": {"action": "allow", "paths": ["./**"]},
                    "write_file": {"action": "confirm", "paths": ["./**"]},
                    "delete_file": {"action": "deny"},
                }
            }
        },
    }


class MCPPolicyEngine:
    def __init__(self, path: str | Path | None = None, *, project_root: str | Path | None = None):
        self.path = Path(path) if path else None
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.data, _ = load_policy(self.path)
        self._mtime = self.path.stat().st_mtime_ns if self.path and self.path.exists() else 0
        self._rate_windows: dict[str, deque[float]] = defaultdict(deque)

    @property
    def version(self) -> str:
        digest = hashlib.sha256(
            json.dumps(self.data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]
        return f"v{self.data.get('version', 1)}:{digest}"

    def reload_if_changed(self) -> bool:
        if not self.path or not self.path.exists():
            return False
        mtime = self.path.stat().st_mtime_ns
        if mtime == self._mtime:
            return False
        self.data, _ = load_policy(self.path)
        self._mtime = mtime
        return True

    def rule_for(self, server_id: str, tool_name: str) -> tuple[dict[str, Any], str]:
        server = (self.data.get("servers") or {}).get(server_id, {})
        tools = server.get("tools") or {}
        if tool_name in tools:
            return dict(tools[tool_name]), f"{server_id}.tools.{tool_name}"
        for group_name, group in (server.get("groups") or {}).items():
            patterns = group.get("tools") or []
            if any(fnmatch.fnmatchcase(tool_name, str(pattern)) for pattern in patterns):
                return dict(group), f"{server_id}.groups.{group_name}"
        action = server.get("default_action", self.data.get("default_action", "confirm"))
        return {"action": action}, f"{server_id}.default"

    def visible_tool(self, server_id: str, tool_name: str) -> bool:
        rule, _ = self.rule_for(server_id, tool_name)
        action = str(rule.get("action", "confirm"))
        return not (bool(self.data.get("hide_denied_tools", True)) and action == "deny")

    def evaluate(self, server_id: str, tool_name: str, arguments: dict[str, Any]) -> MCPDecision:
        self.reload_if_changed()
        rule, rule_id = self.rule_for(server_id, tool_name)
        args = json.loads(json.dumps(arguments))
        action = str(rule.get("action", self.data.get("default_action", "confirm")))
        mode = str(self.data.get("mode", "enforce"))
        risks: list[str] = []
        transformed: list[str] = []

        reason = f"Matched {rule_id}."
        path_error = self._check_paths(rule, args)
        if path_error:
            action, reason = "deny", path_error
            risks.append("filesystem")

        command_error = self._check_command(rule, args)
        if command_error:
            action, reason = "deny", command_error
            risks.append("shell")

        host_error = self._check_host(rule, args)
        if host_error:
            action, reason = "deny", host_error
            risks.append("network")

        sql_error = self._check_sql(rule, args)
        if sql_error:
            action, reason = "deny", sql_error
            risks.append("database")

        payload_limit = int(rule.get("max_payload_bytes", 0) or 0)
        if payload_limit and len(json.dumps(args).encode("utf-8")) > payload_limit:
            action, reason = "deny", "Payload exceeds the configured byte limit."
            risks.append("large_payload")

        if action == "transform":
            for key in rule.get("remove_fields", []):
                if key in args:
                    args.pop(key)
                    transformed.append(str(key))
            if "max_limit" in rule and isinstance(args.get("limit"), int):
                bounded = min(args["limit"], int(rule["max_limit"]))
                if bounded != args["limit"]:
                    args["limit"] = bounded
                    transformed.append("limit")

        if action == "rate_limit":
            action, reason = self._rate_limit(server_id, tool_name, rule)

        if mode == "shadow" and action in {"deny", "confirm"}:
            action = "shadow_deny"
            reason = f"Shadow mode: {reason}"

        return MCPDecision(
            action=action,
            reason=reason,
            rule_id=rule_id,
            policy_version=self.version,
            arguments=args,
            argument_hash=argument_fingerprint(args),
            mode=mode,
            risk_tags=sorted(set(risks)),
            transformed_fields=transformed,
        )

    def _check_paths(self, rule: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        patterns = [str(item) for item in rule.get("paths", [])]
        if not patterns:
            return None
        for key, value in arguments.items():
            if key.lower() not in PATH_KEYS or not isinstance(value, str):
                continue
            candidate = Path(value)
            resolved = (self.project_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            try:
                relative = resolved.relative_to(self.project_root).as_posix()
            except ValueError:
                return f"Path escapes project root: {value}"
            normalized = f"./{relative}"
            if not any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns):
                return f"Path is outside allowed patterns: {value}"
        return None

    @staticmethod
    def _check_command(rule: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        patterns = [str(item) for item in rule.get("deny_patterns", [])]
        if not patterns:
            return None
        raw = arguments.get("argv", arguments.get("command"))
        if isinstance(raw, list):
            command = shlex.join(str(item) for item in raw)
        elif isinstance(raw, str):
            command = raw
        else:
            return None
        if any(fnmatch.fnmatch(command, pattern) or pattern in command for pattern in patterns):
            return "Command matched a denied pattern."
        return None

    @staticmethod
    def _check_host(rule: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        hosts = [str(item).lower() for item in rule.get("hosts", [])]
        if not hosts:
            return None
        url = arguments.get("url") or arguments.get("uri")
        if not isinstance(url, str):
            return None
        host = (urlparse(url).hostname or "").lower()
        if not any(fnmatch.fnmatchcase(host, pattern) for pattern in hosts):
            return f"URL host is not allowed: {host or 'missing'}"
        return None

    @staticmethod
    def _check_sql(rule: dict[str, Any], arguments: dict[str, Any]) -> str | None:
        operations = [str(item).upper() for item in rule.get("sql_operations", [])]
        query = arguments.get("query") or arguments.get("sql")
        if not operations or not isinstance(query, str):
            return None
        operation = query.lstrip().split(None, 1)[0].upper() if query.strip() else ""
        if operation not in operations:
            return f"SQL operation is not allowed: {operation or 'empty'}"
        return None

    def _rate_limit(
        self, server_id: str, tool_name: str, rule: dict[str, Any]
    ) -> tuple[str, str]:
        now = time.monotonic()
        window_seconds = max(1, int(rule.get("window_seconds", 60)))
        limit = max(1, int(rule.get("limit", 10)))
        key = f"{server_id}:{tool_name}"
        window = self._rate_windows[key]
        while window and window[0] <= now - window_seconds:
            window.popleft()
        if len(window) >= limit:
            return "deny", "Rate limit exceeded."
        window.append(now)
        return "allow", "Allowed within rate limit."
