# Operations and Local Data

Agent Loop Guard has no remote control plane or product telemetry. Operational state lives on the machine where the daemon runs.

## Health and status

```bash
alg doctor
alg status
alg status --json
alg open
alg open --replay
```

`doctor` checks the Python runtime, configuration, storage path, and optional capabilities. `status` probes the running daemon. The health API is `GET /api/health`.

## Storage

The default database is `data/agent_loop_guard.db` relative to the process working directory. Setup-generated data is kept under `.agent-loop-guard`. Use an absolute SQLite path when starting the daemon from different directories:

```yaml
storage:
  url: sqlite:///C:/projects/example/.agent-loop-guard/agent_loop_guard.db
```

Database initialization applies the included Alembic revisions. Back up data before upgrading across versions.

## Backup and restore

```bash
alg backup --output backups/alg-backup.zip
alg restore backups/alg-backup.zip --force
```

Restore refuses to overwrite existing local state unless `--force` is present. Stop the daemon before restoring so SQLite files are not being written concurrently.

## Retention

```bash
alg cleanup
alg cleanup --days 14
```

Without `--days`, the configured `storage.retention_days` value is used. Pin important Replay runs before cleanup. Treat exports and backups as sensitive even though redaction is applied.

## Binding and access

Keep the default loopback host:

```yaml
server:
  host: 127.0.0.1
```

The gateway key protects model proxy and MCP traffic, but the local admin and Replay interfaces are designed for loopback use and are not an internet-facing multi-user service. Do not bind to `0.0.0.0` without an authenticated reverse proxy, firewall rules, TLS, and a careful security review.

## Logs and privacy

- Full request content logging is disabled by default.
- Common API key, authorization, password, token, and cookie fields are redacted recursively.
- Tool arguments are represented by fingerprints and selected metadata where possible.
- Chain-of-thought is neither requested nor stored.
- No user telemetry is sent by Agent Loop Guard.

Redaction lowers risk but cannot recognize every project-specific secret. Never use logs as a secret store, and inspect exported traces before sharing them.
