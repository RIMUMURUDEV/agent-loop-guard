# HTTP API Reference

When the daemon is running, interactive OpenAPI documentation is available at [`/docs`](http://127.0.0.1:8787/docs) and the machine-readable schema at `/openapi.json`.

## Authentication boundary

Model proxy and MCP transport requests require the configured gateway key:

```http
Authorization: Bearer alg_demo_key
```

`x-api-key: alg_demo_key` is also accepted for compatible clients. Admin, UI, and Replay endpoints are intended for loopback access and do not constitute a hardened multi-user authentication layer. Keep the daemon on `127.0.0.1`.

## Model proxy

| Method | Path | Compatibility |
| --- | --- | --- |
| `POST` | `/v1/responses` | OpenAI Responses |
| `POST` | `/v1/chat/completions` | OpenAI Chat Completions |
| `GET` | `/v1/models` | OpenAI model discovery |
| `POST` | `/v1/messages` | Anthropic Messages |
| `POST` | `/v1/messages/count_tokens` | Anthropic token counting |
| `HEAD` | `/` | Connectivity probe |

Useful correlation headers include `x-alg-project-id`, `x-alg-session-id`, and `x-alg-agent-id`. If enabled, `x-alg-mode` can select `shadow` or `enforce` for a request.

Guard preserves the upstream response format. A blocked request returns an HTTP error with a safe reason and correlation metadata.

## Local administration

All paths in this table are prefixed by `/api`.

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Health and version data |
| `GET /sessions`, `GET /sessions/{id}` | List or inspect Guard sessions |
| `PATCH /sessions/{id}` | Update mutable session metadata |
| `GET /sessions/{id}/events` | Session decision history |
| `POST /sessions/{id}/pause`, `/resume` | Control one session |
| `GET /policies/{project_id}`, `PUT /policies/{project_id}` | Read or update Guard policy |
| `GET /agents`, `POST /agents` | List or register agents |
| `POST /agents/{id}/pause`, `/resume` | Control an agent |
| `POST /demo/run` | Run a local demo scenario |
| `GET /export/sessions/{id}.json` | Export one session |
| `GET /export/aggregates.csv` | Export aggregate metrics |

The HTML UI uses related form endpoints. API clients should prefer the JSON endpoints above.

## Replay API

These endpoints are prefixed by `/api/v1`.

| Method and path | Purpose |
| --- | --- |
| `POST /traces` | Ingest a trace and optional nested spans/events |
| `POST /spans` | Ingest one span |
| `POST /events/batch` | Ingest an event batch |
| `GET /runs` | List runs with filters and pagination |
| `GET /runs/{trace_id}` | Read one complete run |
| `GET /runs/{trace_id}/export?format=...` | Export `json`, `jsonl`, or `otel` |
| `POST /runs/import` | Import a supported trace representation |
| `POST /runs/{trace_id}/pin` | Set pin state |
| `POST /compare` | Compare two trace IDs |

Minimal ingest:

```bash
curl -X POST http://127.0.0.1:8787/api/v1/traces \
  -H "Content-Type: application/json" \
  -d '{"trace_id":"demo_trace","task_id":"demo","spans":[{"name":"tool.call","start_ns":1,"end_ns":2000000}]}'
```

Use realistic nanosecond timestamps for correct timeline ordering and duration calculation.

## MCP API

| Method and path | Purpose |
| --- | --- |
| `POST /mcp/{server_id}` | Streamable HTTP JSON-RPC transport |
| `GET /api/v1/mcp/servers` | List configured upstream servers |
| `GET /api/v1/mcp/events` | Read redacted MCP audit events |
| `GET /api/v1/mcp/approvals` | List approval requests |
| `POST /api/v1/mcp/approvals/{id}` | Submit allow or deny decision |
| `POST /api/v1/mcp/policies/validate` | Validate policy YAML/data |
| `GET /api/v1/mcp/export` | Export MCP audit records |

The transport follows MCP lifecycle and session headers. Clients should preserve the server-provided `Mcp-Session-Id`. Browser callers must use an Origin allowed by configuration.

## Stability

The local API is pre-1.0. `event.v1`, Replay export formats, and benchmark observation fields are the intended compatibility surfaces; admin endpoints may still evolve between minor development releases.
