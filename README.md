# Agent Loop Guard

Agent Loop Guard is a local runtime guard for coding agents. It sits between an agent and an LLM provider, proxies OpenAI-compatible or Anthropic Messages traffic, records minimal telemetry, and flags or blocks obvious loops.

The default setup uses a local mock provider, so the demo works without an external API key.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alg init
alg run
```

Open `http://127.0.0.1:8787`, then run Demo Lab or:

```bash
alg demo exact-loop
```

Default local gateway key:

```text
alg_demo_key
```

## Proxy Endpoints

OpenAI-compatible:

```text
POST /v1/responses
POST /v1/chat/completions
GET  /v1/models
```

Anthropic-compatible:

```text
POST /v1/messages
POST /v1/messages/count_tokens
```

Connectivity probe:

```text
HEAD /
```

Use `Authorization: Bearer alg_demo_key` or `x-api-key: alg_demo_key`.

## Guard Behavior

The MVP implements:

- exact repeated request detection
- repeated tool call detection
- repeated upstream error detection
- repeated request sequence detection
- request and token limits
- project-level Shadow and Enforce modes
- manual session and agent pause/resume
- metadata-only logging by default
- JSON session export and aggregate CSV export

Shadow Mode flags suspicious requests without blocking. Enforce Mode blocks requests when a blocking rule triggers.

## Agent Setup

Codex CLI:

```toml
model = "demo-model"
model_provider = "agent_loop_guard"

[model_providers.agent_loop_guard]
name = "Agent Loop Guard"
base_url = "http://127.0.0.1:8787/v1"
env_key = "ALG_GATEWAY_KEY"
```

Claude Code:

```bash
set ANTHROPIC_BASE_URL=http://127.0.0.1:8787
set ANTHROPIC_AUTH_TOKEN=alg_demo_key
```

OpenCode:

```json
{
  "provider": {
    "alg": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Agent Loop Guard",
      "options": {
        "baseURL": "http://127.0.0.1:8787/v1",
        "apiKey": "{env:ALG_GATEWAY_KEY}"
      },
      "models": {
        "demo-model": {"name": "Guarded model"}
      }
    }
  },
  "model": "alg/demo-model"
}
```

Cline:

```text
API Provider: OpenAI Compatible
Base URL: http://127.0.0.1:8787/v1
API Key: alg_demo_key
Model ID: demo-model
```

## Configuration

Create a config file:

```bash
alg init --path agent-loop-guard.yml
```

Run with it:

```bash
alg run --config agent-loop-guard.yml
```

Environment overrides include:

- `ALG_HOST`
- `ALG_PORT`
- `ALG_STORAGE_URL`
- `ALG_MODE`
- `ALG_PROVIDER`
- `ALG_GATEWAY_KEY`
- `ALG_OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `ALG_ANTHROPIC_BASE_URL`
- `ANTHROPIC_API_KEY`

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

Docker:

```bash
docker compose up --build
```

## Limits

This is a local pet-project MVP. It only sees traffic routed through its base URL. It does not provide enterprise IAM, distributed leases, legal audit guarantees, or semantic loop detection. Full Content Logging is off by default and should not be enabled for sensitive data unless the data owner understands the risk.

