from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError, validate

from app.db.models import MCPSession
from app.db.repository import Repository
from app.mcp.policy import MCPDecision, MCPPolicyEngine


@dataclass(slots=True)
class CallInterception:
    forward: bool
    message: dict[str, Any]
    response: dict[str, Any] | None
    decision: MCPDecision | None


def jsonrpc_error(request_id: Any, code: int, message: str, data: dict | None = None) -> dict:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def tool_error(request_id: Any, message: str, data: dict | None = None) -> dict:
    payload: dict[str, Any] = {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
    if data:
        payload["structuredContent"] = data
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


class MCPGateway:
    def __init__(
        self,
        repo: Repository,
        policy: MCPPolicyEngine,
        server_id: str,
        session_id: str | None = None,
        approval_timeout_seconds: int = 30,
    ):
        self.repo = repo
        self.policy = policy
        self.server_id = server_id
        self.session_id = session_id
        self.approval_timeout_seconds = approval_timeout_seconds

    def ensure_session(
        self, *, client_name: str | None = None, protocol_version: str | None = None
    ) -> str:
        if self.session_id and self.repo.db.get(MCPSession, self.session_id):
            return self.session_id
        session_id = f"mcp_{secrets.token_urlsafe(18)}"
        self.repo.start_mcp_session(
            self.server_id,
            client_name=client_name,
            protocol_version=protocol_version,
            mode=str(self.policy.data.get("mode", "enforce")),
            session_id=session_id,
        )
        self.session_id = session_id
        return session_id

    def filter_tools(self, response: dict[str, Any]) -> dict[str, Any]:
        result = response.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            return response
        tools = [
            tool
            for tool in result["tools"]
            if isinstance(tool, dict)
            and self.policy.visible_tool(self.server_id, str(tool.get("name") or ""))
        ]
        result["tools"] = tools
        if self.session_id:
            self.repo.record_mcp_tools(self.session_id, self.server_id, tools)
        return response

    def intercept(self, message: dict[str, Any]) -> CallInterception:
        if message.get("method") != "tools/call":
            return CallInterception(True, message, None, None)
        request_id = message.get("id")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        tool_name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        schema = self.repo.mcp_tool_schema(self.server_id, tool_name)
        if schema:
            try:
                validate(instance=arguments, schema=schema)
            except ValidationError as exc:
                return CallInterception(
                    False,
                    message,
                    tool_error(request_id, "Tool arguments failed JSON Schema validation.", {"path": list(exc.path)}),
                    None,
                )

        decision = self.policy.evaluate(self.server_id, tool_name, arguments)
        approved = None
        if decision.action == "confirm":
            approved = self.repo.consume_mcp_approval(
                self.server_id, tool_name, decision.argument_hash, self.session_id
            )
            if approved:
                decision.action = "allow"
                decision.reason = f"Approved by user ({approved.scope})."

        event = self.repo.record_mcp_decision(
            server_id=self.server_id,
            session_id=self.session_id,
            request_id=request_id,
            tool_name=tool_name,
            argument_hash=decision.argument_hash,
            policy_version=decision.policy_version,
            action=decision.action,
            reason=decision.reason,
            rule_id=decision.rule_id,
            mode=decision.mode,
            attributes={
                "risk_tags": decision.risk_tags,
                "transformed_fields": decision.transformed_fields,
            },
        )

        if decision.action == "confirm":
            approval = self.repo.create_mcp_approval(
                event.id, decision.argument_hash, self.approval_timeout_seconds
            )
            return CallInterception(
                False,
                message,
                tool_error(
                    request_id,
                    "User approval is required. Approve the request and retry the same call.",
                    {"approval_id": approval.id, "action": "confirm"},
                ),
                decision,
            )
        if not decision.allowed:
            return CallInterception(
                False,
                message,
                tool_error(request_id, decision.reason, {"action": decision.action, "rule_id": decision.rule_id}),
                decision,
            )

        transformed = json.loads(json.dumps(message))
        transformed.setdefault("params", {})["arguments"] = decision.arguments
        return CallInterception(True, transformed, None, decision)


MOCK_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the demo workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": "Write a file in the demo workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file in the demo workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]


def mock_response(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return None
    if method == "initialize":
        requested = (message.get("params") or {}).get("protocolVersion")
        version = requested if requested == "2025-11-25" else "2025-11-25"
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "Agent Loop Guard mock filesystem", "version": "0.2.0"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": MOCK_TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Mock {name} completed for {arguments.get('path', 'no path')}.",
                    }
                ],
                "structuredContent": {"tool": name, "status": "ok"},
                "isError": False,
            },
        }
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")
