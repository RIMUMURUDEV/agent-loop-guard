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
- trace runs, spans, events, replay UI, JSON export, and run comparison

Shadow Mode flags suspicious requests without blocking. Enforce Mode blocks requests when a blocking rule triggers.

## Session Replay

Every proxied model request now creates a replay trace automatically. Open:

```text
http://127.0.0.1:8787/replay
```

The Replay view shows trace runs, model request spans, policy decision events, token totals, duration, source session links, JSON export, and a simple two-run comparison.

Replay ingest API:

```text
POST /api/v1/traces
POST /api/v1/spans
POST /api/v1/events/batch
GET  /api/v1/runs
GET  /api/v1/runs/{trace_id}
GET  /api/v1/runs/{trace_id}/export
POST /api/v1/compare
```

Minimal trace ingest example:

```bash
curl -X POST http://127.0.0.1:8787/api/v1/traces ^
  -H "Content-Type: application/json" ^
  -d "{\"trace_id\":\"demo_trace\",\"task_id\":\"demo\",\"spans\":[{\"name\":\"tool.call\",\"start_ns\":1,\"end_ns\":2000000}]}"
```

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

## VS Code Extension

An experimental VS Code wrapper lives in `extensions/vscode`. It starts the local guard daemon, shows health in the status bar, opens the dashboard and replay views in VS Code WebViews, and copies agent connection settings.

Install the Python runtime first:

```bash
pip install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git
```

Run the extension from source:

```bash
cd extensions/vscode
npm run check
```

Then open this repository in VS Code, press `F5`, and run `Agent Loop Guard: Start Guard` in the Extension Development Host.

Package and install a local `.vsix`:

```bash
cd extensions/vscode
npm run package
code --install-extension agent-loop-guard-vscode-0.1.0.vsix
```

If `alg` is installed globally, keep `agentLoopGuard.startMode` as `cli`. To run from this checkout instead, set:

```json
{
  "agentLoopGuard.startMode": "source",
  "agentLoopGuard.pythonPath": ".venv\\Scripts\\python.exe",
  "agentLoopGuard.sourcePath": "C:\\path\\to\\agent-loop-guard"
}
```

After the guard is running, point agents at:

```text
OpenAI base URL: http://127.0.0.1:8787/v1
Anthropic base URL: http://127.0.0.1:8787
API key: alg_demo_key
```

See `extensions/vscode/README.md` for all commands and settings.

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
