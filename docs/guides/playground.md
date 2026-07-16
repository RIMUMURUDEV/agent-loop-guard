# Agent Playground

Agent Playground is the interactive, mock-first replacement for Demo Lab. It
shows requests, tool calls, policy decisions, loop detections, token totals, and
the resulting Replay trace without requiring an API key.

```bash
alg guard run
alg playground list
alg playground run exact-loop
alg playground open
```

Scenarios are deterministic fixtures. A run passes through the real Guard
pipeline and is stored in the same SQLite database as ordinary agent traffic.
The Playground polls the run API while a scenario is active and links directly
to Replay for deeper inspection.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/playground/scenarios` | List scenarios |
| `POST` | `/api/v1/playground/runs` | Start a run |
| `GET` | `/api/v1/playground/runs/{id}` | Inspect a run |

An optional OpenAI-compatible upstream can still be configured for normal Guard
traffic. Playground fixtures remain deterministic so screenshots, tests, and
workshops do not depend on a paid service.

