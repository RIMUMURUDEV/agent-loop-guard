from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import TextIO

from app.core.config import AppConfig
from app.db.repository import Repository
from app.db.session import build_engine, build_session_factory, init_db
from app.mcp.gateway import MCPGateway, jsonrpc_error, mock_response
from app.mcp.policy import MCPPolicyEngine


def _write_message(stream: TextIO, message: dict, lock: threading.Lock | None = None) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
    if lock:
        with lock:
            stream.write(payload)
            stream.flush()
    else:
        stream.write(payload)
        stream.flush()


def run_stdio_proxy(
    command: list[str],
    *,
    policy_path: str | None = None,
    server_id: str = "stdio",
    config: AppConfig | None = None,
) -> int:
    if not command:
        raise ValueError("An upstream command is required after --.")
    config = config or AppConfig.from_env()
    engine = build_engine(config)
    init_db(engine, config)
    session_factory = build_session_factory(engine)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    assert process.stdin and process.stdout and process.stderr
    output_lock = threading.Lock()
    gateway_lock = threading.Lock()
    pending: dict[str, str] = {}

    db = session_factory()
    repo = Repository(db)
    repo.ensure_mcp_server(server_id, server_id, "stdio", " ".join(command))
    policy = MCPPolicyEngine(policy_path or config.mcp_policy_path)
    session = repo.start_mcp_session(server_id, client_name="stdio-client", mode=str(policy.data.get("mode", "enforce")))
    gateway = MCPGateway(
        repo,
        policy,
        server_id,
        session_id=session.id,
        approval_timeout_seconds=config.mcp_approval_timeout_seconds,
    )

    def upstream_reader() -> None:
        for raw in process.stdout:
            try:
                response = json.loads(raw)
            except json.JSONDecodeError:
                print("[mcp upstream] ignored non-JSON stdout", file=sys.stderr)
                continue
            request_id = str(response.get("id")) if response.get("id") is not None else None
            with gateway_lock:
                if request_id and pending.pop(request_id, None) == "tools/list":
                    response = gateway.filter_tools(response)
            _write_message(sys.stdout, response, output_lock)

    def stderr_reader() -> None:
        for raw in process.stderr:
            sys.stderr.write(raw)
            sys.stderr.flush()

    threads = [
        threading.Thread(target=upstream_reader, daemon=True),
        threading.Thread(target=stderr_reader, daemon=True),
    ]
    for thread in threads:
        thread.start()

    try:
        for raw in sys.stdin:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                _write_message(sys.stdout, jsonrpc_error(None, -32700, "Parse error"), output_lock)
                continue
            with gateway_lock:
                interception = gateway.intercept(message)
            if not interception.forward:
                if interception.response:
                    _write_message(sys.stdout, interception.response, output_lock)
                continue
            request_id = interception.message.get("id")
            if request_id is not None:
                pending[str(request_id)] = str(interception.message.get("method") or "")
            _write_message(process.stdin, interception.message)
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=2)
        repo.end_mcp_session(session.id)
        db.close()
    return int(process.returncode or 0)


def run_mock_stdio_server() -> int:
    for raw in sys.stdin:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            _write_message(sys.stdout, jsonrpc_error(None, -32700, "Parse error"))
            continue
        response = mock_response(message)
        if response is not None:
            _write_message(sys.stdout, response)
    return 0


def validate_policy_file(path: str | Path) -> list[str]:
    from app.mcp.policy import load_policy, validate_policy

    data, _ = load_policy(path)
    return validate_policy(data)
