# VS Code Extension

The extension is a local wrapper around the Python runtime. It can find or install `alg`, start and stop the daemon, show Guard and Replay in the Activity Bar, set up the current workspace, and copy agent connection values.

## Install

Install the public extension from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=RIMUMURUDEV.agent-loop-guard-vscode) or run:

```bash
code --install-extension RIMUMURUDEV.agent-loop-guard-vscode
```

To build and install a local development package instead:

```bash
cd extensions/vscode
npm run check
npm run package
code --install-extension agent-loop-guard-vscode-0.2.0.vsix
```

The Python runtime is still required. Install it with `pipx`, or run the extension command **Agent Loop Guard: Install Runtime**.

## First use

1. Open the target project in VS Code.
2. Run **Agent Loop Guard: Setup Current Workspace**.
3. Review `.agent-loop-guard/profiles` and merge the relevant agent profile.
4. Run **Agent Loop Guard: Start Guard**.
5. Open the shield icon in the Activity Bar.

The Guard and Replay views embed the local UI. The status bar reports daemon health.

## Commands

| Command | Effect |
| --- | --- |
| Start Guard | Launch the local runtime |
| Stop Guard | Stop the process launched by this extension |
| Restart Guard | Restart that managed process |
| Open Dashboard / Open Replay | Open the corresponding local view |
| Show Status | Probe runtime health |
| Copy OpenAI Base URL / Anthropic Base URL | Copy a provider endpoint |
| Copy Agent Environment | Copy environment variables for agent setup |
| Install Runtime | Install the Python package |
| Setup Current Workspace | Run `alg setup` in the workspace |

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `agentLoopGuard.autoStart` | `false` | Start when VS Code starts |
| `agentLoopGuard.openDashboardOnStart` | `true` | Open dashboard after a successful start |
| `agentLoopGuard.stopOnDeactivate` | `true` | Stop the extension-managed process on deactivation |
| `agentLoopGuard.startMode` | `cli` | Use installed `alg` or a source checkout |
| `agentLoopGuard.cliCommand` | `alg` | Runtime command in CLI mode |
| `agentLoopGuard.pythonPath` | `python` | Python executable in source mode |
| `agentLoopGuard.sourcePath` | empty | Runtime checkout; first workspace folder when empty |
| `agentLoopGuard.configPath` | empty | Optional YAML configuration path |
| `agentLoopGuard.host` / `port` | `127.0.0.1` / `8787` | Local daemon address |
| `agentLoopGuard.gatewayKey` | `alg_demo_key` | Key passed to the daemon and setup snippets |
| `agentLoopGuard.environment` | `{}` | Additional environment variables |

Source mode example:

```json
{
  "agentLoopGuard.startMode": "source",
  "agentLoopGuard.pythonPath": ".venv\\Scripts\\python.exe",
  "agentLoopGuard.sourcePath": "C:\\src\\agent-loop-guard"
}
```

!!! note
    The extension stops only a process it started. It does not kill an independently running `alg` daemon.
