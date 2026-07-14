# Event and Trace Schemas

All modules share a redacted `event.v1` envelope. Module-specific exports add their own versioned records.

## Unified event

```json
{
  "schema_version": "event.v1",
  "event_id": "evt_0123456789abcdef01234567",
  "source": "mcp",
  "type": "policy.decision",
  "project_id": "default",
  "trace_id": "trace_...",
  "span_id": "span_...",
  "severity": "info",
  "timestamp_ns": 1784000000000000000,
  "attributes": {
    "action": "confirm",
    "tool_name": "write_file"
  }
}
```

Required semantic fields are `source` and `type`. IDs and timestamp are generated when absent. `trace_id` and `span_id` are optional correlation fields. Attributes are recursively redacted when serialized.

Recommended event types:

- `tool.call`
- `policy.decision`
- `command.exec`
- `file.change`
- `benchmark.result`
- provider and Guard lifecycle events

Event names describe an observation, not hidden model reasoning. Chain-of-thought is outside the schema.

## Replay trace

Replay exports a run plus spans, events, and artifacts. A span has an ID, trace ID, optional parent ID, name, start/end nanoseconds, status, and redacted attributes. Events can attach to a trace or span. Artifacts store metadata or safe references rather than an assumption that arbitrary content is harmless.

Supported export forms:

| Format | Use |
| --- | --- |
| `json` | One complete human-readable run object |
| `jsonl` | Stream-friendly versioned records |
| `otel` | OpenTelemetry-shaped trace exchange |

Deterministic failure tags include loop, timeout, rate limit, policy block, and test failure. Tags are diagnostic labels, not proof of root cause.

## Benchmark observation

`benchmark-observation` records contain:

```text
run_id, candidate, task_id, difficulty, repetition, seed,
score, duration_ms, input_tokens, output_tokens, cost_micros,
output_hash, error, metadata
```

The output hash allows equality checks without persisting generated output.

## Sandbox manifest

`sandbox.v1` includes the sandbox ID, absolute source path, container image, Docker version, creation timestamp, and original file hashes. Exports additionally include `diff.json` and the copied workspace.

## Compatibility rules

- Readers should ignore unknown fields.
- Writers must preserve IDs used for correlation.
- A breaking semantic change requires a new `schema_version`.
- Timestamps use Unix epoch nanoseconds unless a format explicitly says otherwise.
- Secrets must be redacted before an event crosses a module boundary.
