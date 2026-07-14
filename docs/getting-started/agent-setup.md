# Connect an agent

`alg setup` generates ready-to-use connection profiles in `.agent-loop-guard/profiles`. Review and merge the relevant profile into your agent configuration. The command does not overwrite an agent's global configuration automatically.

Before connecting an agent, start the gateway:

```bash
alg guard run
```

## Common connection values

| Setting | Default |
| --- | --- |
| OpenAI base URL | `http://127.0.0.1:8787/v1` |
| Anthropic base URL | `http://127.0.0.1:8787` |
| API key | Value of `gateway_key` in `agent-loop-guard.yml` |
| Demo model | `demo-model` |

Never commit a generated gateway key. `agent-loop-guard.yml` and `.agent-loop-guard/` are ignored by the repository's default `.gitignore`.

## Codex CLI

Copy the generated `.agent-loop-guard/profiles/codex.toml` provider definition into your Codex configuration:

```toml
model = "demo-model"
model_provider = "agent_loop_guard"

[model_providers.agent_loop_guard]
name = "Agent Loop Guard"
base_url = "http://127.0.0.1:8787/v1"
env_key = "ALG_GATEWAY_KEY"
```

Set the key in the shell that starts Codex:

=== "PowerShell"

    ```powershell
    $env:ALG_GATEWAY_KEY = "your-generated-key"
    ```

=== "Linux/macOS"

    ```bash
    export ALG_GATEWAY_KEY="your-generated-key"
    ```

## Claude Code

The generated `claude.env` contains:

=== "PowerShell"

    ```powershell
    $env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
    $env:ANTHROPIC_AUTH_TOKEN = "your-generated-key"
    ```

=== "Linux/macOS"

    ```bash
    export ANTHROPIC_BASE_URL="http://127.0.0.1:8787"
    export ANTHROPIC_AUTH_TOKEN="your-generated-key"
    ```

## Cline

Open Cline's provider settings and select **OpenAI Compatible**.

| Cline field | Value |
| --- | --- |
| Base URL | `http://127.0.0.1:8787/v1` |
| API key | Generated gateway key |
| Model ID | `demo-model` or your configured upstream model |

The same values are written to `.agent-loop-guard/profiles/cline.txt`.

## OpenCode

Merge `.agent-loop-guard/profiles/opencode.json` into the OpenCode configuration:

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

## Direct HTTP clients

OpenAI-compatible request:

```bash
curl http://127.0.0.1:8787/v1/responses \
  -H "Authorization: Bearer $ALG_GATEWAY_KEY" \
  -H "Content-Type: application/json" \
  -H "x-alg-session-id: docs-example" \
  -d '{"model":"demo-model","input":"Return a short greeting"}'
```

Anthropic-compatible request:

```bash
curl http://127.0.0.1:8787/v1/messages \
  -H "x-api-key: $ALG_GATEWAY_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{"model":"demo-model","max_tokens":64,"messages":[{"role":"user","content":"Hello"}]}'
```

## Session correlation

Send `x-alg-session-id` to group requests into one Guard session. Claude Code may also provide `x-claude-code-session-id`, which is used when the explicit Agent Loop Guard header is absent.

Without an external session ID, the gateway still records requests, but continuity depends on the runtime's session resolution behavior.
