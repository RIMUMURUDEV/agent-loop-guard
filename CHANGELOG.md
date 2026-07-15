# Changelog

## 0.6.0a3 - 2026-07-15

- Updated package metadata and installation guidance after the first PyPI publication.
- Switched the VS Code runtime installer from GitHub source installs to the PyPI distribution.

## 0.6.0a2 - 2026-07-15

- Replaced the shortened repository license with the canonical Apache License 2.0 text.
- Polished the public installation guidance, documentation site, repository metadata, contribution templates, and release artifacts.
- Published the Agent Loop Guard 0.2.0 extension in the VS Code Marketplace.
- Published `agent-loop-guard-runtime` 0.6.0a2 on PyPI through Trusted Publishing.

## 0.6.0a1 - 2026-07-14

- Added setup, doctor, status, open, backup, restore, cleanup, and Alembic migrations.
- Added shared redacted event envelopes and modular `platform`, `mcp`, `replay`, `benchmark`, and `sandbox` packages.
- Added MCP stdio and Streamable HTTP proxies, YAML policies, approvals, hot reload, schema validation, and Replay audit events.
- Expanded Replay with SDK contexts, JSONL/OpenTelemetry import/export, pinning, costs, failure tags, timeline bars, and aligned comparisons.
- Added a versioned 30-task benchmark dataset, mock/HTTP/CLI adapters, deterministic and custom scorers, budgets, Parquet/DuckDB/MLflow hooks, and paired bootstrap regression checks.
- Added a Docker sandbox technical preview with offline defaults, resource limits, diff, selective apply, discard, and export.
- Expanded the VS Code extension with runtime discovery, installation/setup commands, and Guard/Replay Activity Bar views.
- Added Python 3.11-3.13 CI on Windows, Linux, and macOS plus Linux Docker smoke tests.
