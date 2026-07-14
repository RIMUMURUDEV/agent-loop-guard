from __future__ import annotations

import re

DENIED_COMMAND_PATTERNS = (
    r"\b(?:docker|podman)\b",
    r"\bmount\b",
    r"\b(?:shutdown|reboot|poweroff)\b",
    r"\bnsenter\b",
    r"/proc/(?:1|sysrq-trigger)",
    r":\s*\(\s*\)\s*\{.*:\s*\|\s*:",
)


def validate_command(command: list[str]) -> None:
    if not command:
        raise ValueError("A command is required after --")
    rendered = " ".join(command)
    for pattern in DENIED_COMMAND_PATTERNS:
        if re.search(pattern, rendered, re.IGNORECASE):
            raise ValueError(f"Command denied by sandbox policy: {pattern}")

