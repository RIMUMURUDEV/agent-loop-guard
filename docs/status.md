# Project Status

Current package version: **`0.6.0a2`**. The repository is an educational open-source project and remains pre-1.0.

| Area | Current state | Main limitation |
| --- | --- | --- |
| Platform setup | Implemented | PyPI publication depends on publisher setup |
| Loop Guard | Locally usable | Only sees routed traffic; single-node state |
| MCP Firewall | Technical preview | Task-based execution deferred; local approvals |
| Replay | Technical preview | UI and export contracts may still evolve |
| Benchmark Lab | Technical preview | Starter dataset is synthetic and small |
| Sandbox | Technical preview | Requires Docker; not a certified boundary |
| VS Code extension | Experimental | Marketplace publication not completed |

## Implemented

- OpenAI- and Anthropic-compatible guarded proxy routes
- exact request, tool, error, and sequence loop detection
- Shadow/Enforce modes, limits, pause/resume, session export
- stdio and Streamable HTTP MCP proxying with policy, approvals, validation, and audit
- Replay SDK, automatic model traces, JSON/JSONL/OTel exchange, comparison, cost and failure tags
- 30-task versioned benchmark dataset, three adapters, deterministic/custom scorers, paired bootstrap gate
- copied-workspace Docker runner with diff, selective apply, discard, and export
- VS Code Activity Bar integration and workspace setup
- Alembic-managed SQLite schema, backup, restore, cleanup, diagnostics
- no product telemetry and metadata-only logging by default

## Not complete

- PyPI and VS Code Marketplace public releases
- MCP task-based execution
- fully integrated v1.0 dashboard and cross-module workflow
- broad real-world benchmark datasets and adapter ecosystem
- hardened multi-user or network deployment
- macOS/Windows parity for real Sandbox security tests
- formal security audit or certification

## Release policy

Each milestone should remain installable, documented, and tested. Features may change before `1.0`, but versioned event and export formats should change only through an explicit schema version.

## Project priorities

Correctness, learning value, tests, privacy, and honest limitations come before monetization. The project has no paid tier, hosted service, SLA, or closed features. Optional donations do not affect architecture or issue priority.
