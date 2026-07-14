# MCP Permission Firewall

The MCP Permission Firewall is a policy-enforcing proxy between an MCP client and server. It supports local stdio processes and Streamable HTTP endpoints.

The implementation targets MCP protocol version `2025-11-25`. Task-based execution is not implemented.

## What the proxy enforces

- preserves JSON-RPC request IDs;
- validates `tools/call` arguments against the most recently observed `inputSchema`;
- removes denied tools from `tools/list` discovery;
- evaluates `allow`, `deny`, `confirm`, `transform`, `rate_limit`, and `shadow_deny` actions;
- checks path containment, shell patterns, HTTP hosts, SQL operations, and payload size;
- binds approvals to server, session, tool name, and argument hash;
- writes every decision into Replay;
- reloads the policy when the YAML file modification time changes.

## Start with the bundled policy

```bash
alg mcp validate-policy app/mcp/presets/filesystem.yml
```

The filesystem preset behaves as follows:

| Tool | Result |
| --- | --- |
| `read_file` | Allowed inside the project root |
| `write_file` | Requires approval |
| `delete_file` | Denied and hidden from discovery |
| Unknown tool | Requires approval |

Copy a preset into the workspace before editing it:

```powershell
Copy-Item app\mcp\presets\development.yml mcp-policy.yml
```

## stdio proxy

Place the proxy command where the MCP client would normally start the server:

```bash
alg mcp run --policy mcp-policy.yml --server-id filesystem -- python path/to/server.py
```

Everything after `--` is the real upstream command. The proxy keeps stdout reserved for JSON-RPC messages and forwards upstream stderr separately, which is required by stdio MCP clients.

For a deterministic protocol test server:

```bash
alg mcp test-server
```

## Streamable HTTP proxy

Define the upstream in `agent-loop-guard.yml`:

```yaml
mcp:
  policy: mcp-policy.yml
  approval_timeout_seconds: 30
  allowed_origins:
    - http://127.0.0.1
    - http://localhost
  servers:
    source-control:
      name: Source control tools
      transport: http
      target: http://127.0.0.1:9000/mcp
```

Start the HTTP gateway:

```bash
alg mcp serve
```

Point the MCP client to:

```text
http://127.0.0.1:8787/mcp/source-control
```

Requests require the Agent Loop Guard gateway key. `initialize` creates a local MCP session and returns `MCP-Session-Id`. Subsequent POST, GET/SSE, and DELETE requests must send that ID. For remote upstreams, the proxy maps the local session ID to the server's upstream session ID.

## Approval flow

When a rule returns `confirm`, the tool call does not reach the server. The client receives a tool error with an approval ID:

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "content": [{"type": "text", "text": "User approval is required. Approve the request and retry the same call."}],
    "isError": true,
    "structuredContent": {
      "approval_id": "apr_...",
      "action": "confirm"
    }
  }
}
```

Approve or deny it in the local `/mcp` dashboard, or through the API:

```bash
curl -X POST http://127.0.0.1:8787/api/v1/mcp/approvals/APR_ID \
  -H "Content-Type: application/json" \
  -d '{"action":"allow","scope":"once"}'
```

The client must retry the same call. A `once` approval is consumed after one matching retry. A different argument hash does not reuse it. Expired, decided, or consumed approvals cannot be replayed.

## Discovery filtering

With `hide_denied_tools: true`, an exact `deny` rule removes that tool from the proxied `tools/list` response. Other policy actions remain visible so the client can request them.

Discovery filtering is a usability and least-privilege control. It does not replace call-time enforcement; every `tools/call` is evaluated again.

## Schema validation

The proxy snapshots tool schemas from `tools/list`. A later `tools/call` is validated with JSON Schema before policy evaluation. Invalid calls return an MCP tool error and are not forwarded.

Call `tools/list` after connecting so the proxy can observe schemas. If no schema has been observed, policy checks still run but schema validation is skipped for that tool.

## Origin protection

HTTP requests with an `Origin` header must match `mcp.allowed_origins`. Requests without an Origin are accepted for non-browser clients. Keep the gateway on loopback unless another network security layer is present.

## Audit and Replay

The MCP page shows server fingerprints, pending approvals, and recent decisions. Export the complete local audit bundle:

```bash
curl http://127.0.0.1:8787/api/v1/mcp/export -o mcp-audit.json
```

The audit contains policy versions, argument hashes, actions, rule IDs, modes, timestamps, and Replay trace IDs. It does not need raw tool arguments to correlate repeated calls.

See the [MCP policy reference](../reference/mcp-policy.md) for every supported field.
