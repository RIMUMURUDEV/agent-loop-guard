# Five-minute quickstart

This workflow uses the built-in mock provider. It sends no request to a paid model API.

## 1. Create local configuration

From the project you want to protect:

```bash
alg setup
```

This creates:

```text
agent-loop-guard.yml
.agent-loop-guard/
└── profiles/
    ├── claude.env
    ├── cline.txt
    ├── codex.toml
    └── opencode.json
```

The command generates a gateway key when it creates a new configuration. Re-running setup preserves the existing key unless `--force` is used.

## 2. Check the environment

```bash
alg doctor
```

Docker may show `WARN`. That does not prevent Guard, MCP, Replay, or Benchmark from running.

## 3. Start the local gateway

```bash
alg guard run
```

Keep this terminal open. The default addresses are:

| Surface | URL |
| --- | --- |
| Dashboard | `http://127.0.0.1:8787` |
| OpenAI-compatible API | `http://127.0.0.1:8787/v1` |
| Anthropic-compatible API | `http://127.0.0.1:8787` |
| API documentation | `http://127.0.0.1:8787/docs` |

## 4. Run a guarded demo

In another terminal:

```bash
alg demo exact-loop
```

The command creates a session with repeated requests. In the default Shadow mode the requests are recorded and flagged without being blocked.

Open the dashboard:

```bash
alg open
```

Inspect:

- **Sessions** for request counters and loop decisions;
- **Replay** for spans, events, timing, and token usage;
- **MCP Firewall** for configured servers and pending approvals.

## 5. Try Enforce mode

```bash
alg demo exact-loop --mode enforce
```

In Enforce mode a matching blocking policy returns a local error instead of forwarding the request.

## Next steps

- [Connect a real coding agent](agent-setup.md).
- [Understand Guard rules](../guides/guard.md).
- [Configure MCP permissions](../guides/mcp-firewall.md).
- [Import traces through the Replay SDK](../guides/replay.md).
