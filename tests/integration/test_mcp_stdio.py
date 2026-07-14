from __future__ import annotations

import json
import subprocess
import sys


def test_stdio_proxy_preserves_jsonrpc_and_filters_denied_tools(tmp_path) -> None:
    policy = tmp_path / "policy.yml"
    policy.write_text(
        """version: 1
default_action: confirm
hide_denied_tools: true
servers:
  test:
    tools:
      read_file: {action: allow, paths: [\"./**\"]}
      write_file: {action: confirm, paths: [\"./**\"]}
      delete_file: {action: deny}
""",
        encoding="utf-8",
    )
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    command = [
        sys.executable,
        "-m",
        "app.cli",
        "mcp",
        "run",
        "--policy",
        str(policy),
        "--server-id",
        "test",
        "--",
        sys.executable,
        "-m",
        "app.cli",
        "mcp",
        "test-server",
    ]
    completed = subprocess.run(
        command,
        input="".join(json.dumps(item) + "\n" for item in requests),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=15,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stderr
    responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert [response["id"] for response in responses] == [1, 2]
    names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert names == {"read_file", "write_file"}
