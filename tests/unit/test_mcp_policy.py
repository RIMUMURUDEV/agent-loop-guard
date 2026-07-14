from __future__ import annotations

from pathlib import Path

from app.mcp.policy import MCPPolicyEngine, argument_fingerprint, validate_policy


def test_default_mcp_policy_allows_reads_confirms_writes_and_denies_delete(tmp_path: Path) -> None:
    engine = MCPPolicyEngine(project_root=tmp_path)

    read = engine.evaluate("filesystem", "read_file", {"path": "README.md"})
    write = engine.evaluate(
        "filesystem", "write_file", {"path": "notes.txt", "content": "hello"}
    )
    delete = engine.evaluate("filesystem", "delete_file", {"path": "notes.txt"})

    assert read.action == "allow"
    assert write.action == "confirm"
    assert delete.action == "deny"


def test_path_escape_overrides_allow_rule(tmp_path: Path) -> None:
    engine = MCPPolicyEngine(project_root=tmp_path)
    decision = engine.evaluate("filesystem", "read_file", {"path": "../secret.txt"})
    assert decision.action == "deny"
    assert "escapes project root" in decision.reason


def test_transform_and_argument_fingerprint_are_deterministic(tmp_path: Path) -> None:
    engine = MCPPolicyEngine(project_root=tmp_path)
    engine.data = {
        "version": 1,
        "default_action": "deny",
        "servers": {
            "database": {
                "tools": {
                    "query": {
                        "action": "transform",
                        "max_limit": 25,
                        "remove_fields": ["debug"],
                    }
                }
            }
        },
    }
    decision = engine.evaluate("database", "query", {"limit": 100, "debug": True})
    assert decision.arguments == {"limit": 25}
    assert decision.transformed_fields == ["debug", "limit"]
    assert argument_fingerprint({"b": 2, "a": 1}) == argument_fingerprint({"a": 1, "b": 2})


def test_policy_validation_reports_unsupported_actions() -> None:
    errors = validate_policy(
        {
            "version": 1,
            "servers": {"filesystem": {"tools": {"read_file": {"action": "maybe"}}}},
        }
    )
    assert errors
