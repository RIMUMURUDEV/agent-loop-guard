# Agent Loop Guard for VS Code

This extension is a lightweight VS Code wrapper around the Agent Loop Guard local gateway. It can start the daemon, show runtime status, open the dashboard in a VS Code WebView, and copy agent connection settings.

## Requirements

Install the Python runtime first, or run `Agent Loop Guard: Install Runtime` and choose pipx, uv, or pip:

```bash
pipx install git+https://github.com/RIMUMURUDEV/agent-loop-guard.git
```

Or use a local checkout:

```bash
git clone https://github.com/RIMUMURUDEV/agent-loop-guard.git
cd agent-loop-guard
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Run From Source

Open this repository in VS Code, then open `extensions/vscode` and press `F5`. In the Extension Development Host, run:

```text
Agent Loop Guard: Start Guard
```

If `alg` is installed globally, keep `agentLoopGuard.startMode` set to `cli`.

If you want to run from the checkout instead, set:

```json
{
  "agentLoopGuard.startMode": "source",
  "agentLoopGuard.pythonPath": ".venv\\Scripts\\python.exe",
  "agentLoopGuard.sourcePath": "C:\\path\\to\\agent-loop-guard"
}
```

## Package A VSIX

```bash
cd extensions/vscode
npm run check
npm run package
code --install-extension agent-loop-guard-vscode-0.2.0.vsix
```

`npm run package` uses `npx @vscode/vsce`, so no committed build output is required.

## Commands

- `Agent Loop Guard: Start Guard`
- `Agent Loop Guard: Stop Guard`
- `Agent Loop Guard: Restart Guard`
- `Agent Loop Guard: Open Dashboard`
- `Agent Loop Guard: Open Replay`
- `Agent Loop Guard: Show Status`
- `Agent Loop Guard: Copy OpenAI Base URL`
- `Agent Loop Guard: Copy Anthropic Base URL`
- `Agent Loop Guard: Copy Agent Environment`

## Agent Connection

OpenAI-compatible agents:

```text
Base URL: http://127.0.0.1:8787/v1
API Key: alg_demo_key
```

Anthropic-compatible agents:

```text
Base URL: http://127.0.0.1:8787
API Key: alg_demo_key
```

The extension can copy both base URLs and a small environment snippet from the command palette.

The Agent Loop Guard Activity Bar contains embedded Guard and Replay views. Run `Agent Loop Guard: Setup Current Workspace` to generate the YAML config and Codex, Claude Code, Cline, and OpenCode connection profiles.

## Settings

Important settings:

- `agentLoopGuard.autoStart`
- `agentLoopGuard.startMode`
- `agentLoopGuard.cliCommand`
- `agentLoopGuard.pythonPath`
- `agentLoopGuard.sourcePath`
- `agentLoopGuard.configPath`
- `agentLoopGuard.host`
- `agentLoopGuard.port`
- `agentLoopGuard.gatewayKey`
- `agentLoopGuard.environment`

The runtime remains a separate Python process. The extension detects `alg`, offers installation when it is missing, and never downloads or executes an installer without a command selected by the user.

The extension only stops guard processes it started itself. If the daemon is already running from another terminal, the Stop command leaves it alone.
