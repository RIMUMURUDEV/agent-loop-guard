# Agent Loop Guard

[![CI](https://github.com/RIMUMURUDEV/agent-loop-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/RIMUMURUDEV/agent-loop-guard/actions/workflows/ci.yml)
[![Documentation](https://github.com/RIMUMURUDEV/agent-loop-guard/actions/workflows/docs.yml/badge.svg)](https://rimumurudev.github.io/agent-loop-guard/)
[![Python 3.11-3.13](https://img.shields.io/badge/python-3.11--3.13-3776AB.svg)](https://www.python.org/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-2F6F44.svg)](LICENSE)

Agent Loop Guard is an Apache-2.0 local safety and observability toolkit for coding agents. It combines a loop guard, MCP permission firewall, session replay, deterministic benchmark lab, and a Docker-backed sandbox technical preview.

The default setup uses a local mock provider, so the demo works without an external API key.

![Agent Loop Guard dashboard](https://raw.githubusercontent.com/RIMUMURUDEV/agent-loop-guard/main/docs/assets/dashboard.png)

## Install

Install the current alpha directly from GitHub. The installed command is `alg`:

```bash
pipx install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git
# or
uv tool install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git
```

Run once without a permanent installation:

```bash
uvx --from git+https://github.com/RIMUMURUDEV/agent-loop-guard.git alg doctor
```

PyPI publication under the distribution name `agent-loop-guard-runtime` is planned after trusted publishing is configured. The project does not claim that an unpublished package is available.

For development from this checkout:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alg setup
alg doctor
alg guard run
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

`alg setup` creates a local YAML configuration and connection profiles for Codex, Claude Code, Cline, and OpenCode under `.agent-loop-guard/profiles`. Open `http://127.0.0.1:8787`, then run Demo Lab or `alg demo exact-loop`.

## Modules

```text
alg setup | doctor | status | open
alg guard run
alg mcp run | serve | validate-policy | test-server
alg replay import | export
alg bench dataset validate | run | compare | regression-check
alg sandbox create | exec | diff | apply | discard | export
```

- **Guard** detects exact request, tool, error, and sequence loops with Shadow and Enforce modes.
- **MCP Firewall** proxies stdio and Streamable HTTP, validates schemas, filters discovery, and applies YAML policies.
- **Replay** stores redacted traces, spans, events, costs, deterministic failure tags, and JSONL/OpenTelemetry exports.
- **Benchmark Lab** runs the bundled 30-task dataset through mock, HTTP, or CLI adapters and computes paired bootstrap confidence intervals.
- **Sandbox Preview** runs a copied workspace in a resource-limited Docker container and applies no changes before explicit approval.

Read the [public documentation](https://rimumurudev.github.io/agent-loop-guard/), [Architecture](docs/architecture.md), [Threat Model](docs/security.md), [Benchmark Guide](docs/guides/benchmark.md), and [Sandbox Guide](docs/guides/sandbox.md). A [Russian overview](docs/ru/index.md) is also available.

## Guard Behavior

The guard implements:

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

## MCP Firewall

Validate and run a stdio policy proxy:

```bash
alg mcp validate-policy app/mcp/presets/filesystem.yml
alg mcp run --policy app/mcp/presets/filesystem.yml -- your-mcp-server
```

For Streamable HTTP, configure a server under `mcp.servers`, run `alg mcp serve`, and connect to `/mcp/{server_id}`. Approval requests appear at `/mcp`. Raw arguments and secrets are redacted; audit records store hashes and policy metadata.

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
GET  /api/v1/runs/{trace_id}/export?format=json|jsonl|otel
POST /api/v1/runs/import
POST /api/v1/runs/{trace_id}/pin
POST /api/v1/compare
```

CLI transfer:

```bash
alg replay export TRACE_ID --format jsonl --output trace.jsonl
alg replay import trace.jsonl
```

## Benchmark Lab

```bash
alg bench dataset validate
alg bench run --adapter mock --candidate baseline --output baseline.jsonl
alg bench run --adapter mock --variant regressed --candidate candidate --output candidate.jsonl
alg bench regression-check baseline.jsonl candidate.jsonl
```

Parquet, DuckDB, and MLflow are optional:

```bash
pip install -e ".[bench]"
```

The regression command exits `0` for no regression, `1` for a statistically supported regression, and `2` when the result is inconclusive.

## Sandbox Preview

Docker must be installed and running first. The original project is not mounted into the container; the sandbox uses a private copy.

```bash
alg sandbox create .
alg sandbox exec SANDBOX_ID -- pytest -q
alg sandbox diff SANDBOX_ID
alg sandbox apply SANDBOX_ID --path app/example.py
alg sandbox discard SANDBOX_ID
```

Network is disabled by default. This is a defense-in-depth development tool, not a certified security boundary; read [the threat model](docs/security.md) before using it with untrusted code.

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

Install the Python runtime first, then use `Agent Loop Guard: Setup Current Workspace`:

```bash
pipx install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git
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
code --install-extension agent-loop-guard-vscode-0.2.0.vsix
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
pip install -e ".[dev,docs]"
pytest -q
ruff check .
mkdocs build --strict
```

Run the documentation site locally:

```bash
mkdocs serve
```

The full contributor workflow is in [CONTRIBUTING.md](CONTRIBUTING.md). Security assumptions and private reporting guidance are in [SECURITY.md](SECURITY.md).

Docker:

```bash
docker compose up --build
```

## Project Status

This repository is developed as an educational open-source project. Guard, MCP, Replay, and Benchmark are locally testable. Sandbox is a technical preview and its real Docker smoke-test runs only on Linux CI; it could not be executed on the current Windows machine because Docker is not installed. PyPI and VS Code Marketplace publication require the repository owner to configure the corresponding publisher accounts.

There is no telemetry, paid cloud, subscription, SLA, or closed feature set. Optional donations may be added later, but they do not influence architecture or priorities.

## Limits

The toolkit only sees traffic routed through it. It does not provide enterprise IAM, distributed leases, legal audit guarantees, a kernel-level isolation guarantee, or hidden chain-of-thought capture. Full Content Logging is off by default and should not be enabled for sensitive data unless the data owner understands the risk.
