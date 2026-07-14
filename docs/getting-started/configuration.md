# Configuration

Agent Loop Guard uses built-in defaults, an optional YAML file, and environment-variable overrides.

Precedence is:

```text
environment variable > YAML configuration > built-in default
```

Set `ALG_CONFIG` or pass `--config` to commands that accept it.

```bash
alg guard run --config agent-loop-guard.yml
```

## Complete example

```yaml
server:
  host: 127.0.0.1
  port: 8787
  admin_ui: true
  body_limit_bytes: 1048576
  inactive_timeout_seconds: 1800

storage:
  url: sqlite:///./data/agent_loop_guard.db
  retention_days: 30
  full_content_logging: false

gateway_key: replace-this-value

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
      name: Local filesystem server
      transport: mock
      target: mock://filesystem
```

## Server settings

| YAML path | Environment | Default | Description |
| --- | --- | --- | --- |
| `server.host` | `ALG_HOST` | `127.0.0.1` | Bind address |
| `server.port` | `ALG_PORT` | `8787` | HTTP port |
| `server.admin_ui` | `ALG_ADMIN_UI` | `true` | Enable dashboard and static assets |
| `server.body_limit_bytes` | `ALG_BODY_LIMIT_BYTES` | `1048576` | Maximum declared request body size |
| `server.inactive_timeout_seconds` | `ALG_INACTIVE_TIMEOUT_SECONDS` | `1800` | Session inactivity threshold |
| `server.allow_mode_header` | `ALG_ALLOW_MODE_HEADER` | `true` | Allow supported requests to select Shadow/Enforce mode |

Keep the default loopback host unless remote access is deliberately protected by another authentication and network layer. The local dashboard and administration endpoints are designed for local use.

## Storage settings

| YAML path | Environment | Default | Description |
| --- | --- | --- | --- |
| `storage.url` | `ALG_STORAGE_URL` | `sqlite:///./data/agent_loop_guard.db` | SQLAlchemy database URL |
| `storage.retention_days` | `ALG_RETENTION_DAYS` | `30` | Default cleanup window |
| `storage.full_content_logging` | `ALG_FULL_CONTENT_LOGGING` | `false` | Store redacted content previews instead of metadata-only previews |

File-backed SQLite is the supported local storage target. Alembic migrations run at startup and SQLite foreign keys are enabled for every connection.

!!! danger "Full-content logging"
    Redaction is best-effort. Enabling full-content logging can persist prompts, model output, paths, or source fragments that do not match a known secret pattern.

## Project and provider settings

| YAML path | Environment | Default |
| --- | --- | --- |
| `projects.default.mode` | `ALG_MODE` | `shadow` |
| `projects.default.provider` | `ALG_PROVIDER` | `mock` |
| `providers.openai.base_url` | `ALG_OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| OpenAI key | `OPENAI_API_KEY` | unset |
| `providers.anthropic.base_url` | `ALG_ANTHROPIC_BASE_URL` | `https://api.anthropic.com` |
| Anthropic key | `ANTHROPIC_API_KEY` | unset |

Provider API keys should be supplied through environment variables. Do not place live upstream keys in committed YAML.

## Gateway authentication

`gateway_key` is accepted through either:

```http
Authorization: Bearer <gateway-key>
```

or:

```http
x-api-key: <gateway-key>
```

The default development key is intentionally public and must not be used when exposing the service beyond a private local environment. `alg setup` generates a random key for a new workspace.

## MCP settings

| YAML path | Environment | Default | Description |
| --- | --- | --- | --- |
| `mcp.policy` | `ALG_MCP_POLICY` | `mcp-policy.yml` | YAML permission policy |
| `mcp.approval_timeout_seconds` | `ALG_MCP_APPROVAL_TIMEOUT_SECONDS` | `30` | Pending approval lifetime |
| `mcp.allowed_origins` | none | loopback origins | Browser Origin allowlist |
| `mcp.servers` | none | mock filesystem | Server IDs, transports, and targets |

See the [MCP guide](../guides/mcp-firewall.md) and [policy reference](../reference/mcp-policy.md).
