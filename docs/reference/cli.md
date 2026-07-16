# CLI Reference

The executable is `alg`. Run `alg COMMAND --help` for the parser-generated reference for an installed version.

## Runtime and setup

| Command | Important options | Purpose |
| --- | --- | --- |
| `alg setup` | `--path`, `--host`, `--port`, `--gateway-key`, `--force` | Create local config and agent profiles |
| `alg doctor` | `--config` | Diagnose installation and configuration |
| `alg status` | `--base-url`, `--json` | Probe a running daemon |
| `alg open` | `--base-url`, `--replay` | Open Dashboard or Replay |
| `alg init` | `--path`, `--force` | Write a sample YAML config |
| `alg sample-config` | none | Print sample YAML to stdout |
| `alg run` | `--config`, `--host`, `--port`, `--log-level` | Start the gateway; legacy alias for `guard run` |
| `alg guard run` | `--config`, `--host`, `--port`, `--log-level` | Start Guard, UI, Replay, and configured HTTP MCP proxies |
| `alg playground list` | none | List deterministic local scenarios |
| `alg playground run SCENARIO` | `--mode shadow|enforce`, `--base-url` | Run a scenario against a daemon |
| `alg playground open` | `--base-url` | Open the interactive Playground |
| `alg demo [SCENARIO]` | `--mode shadow|enforce`, `--base-url` | Legacy scenario alias |

The default demo scenario is `exact-loop`.

## IssuePilot

```text
alg issue import SOURCE [--root DIRECTORY] [--token TOKEN]
alg issue plan ISSUE_ID [--root DIRECTORY]
alg issue apply ISSUE_ID [--root DIRECTORY] [--repository DIRECTORY]
alg issue export ISSUE_ID [--root DIRECTORY] [--output FILE]
```

`SOURCE` is a GitHub issue URL or local JSON fixture. Import and planning are
read-only. `apply` is required before IssuePilot creates or switches a Git
branch. The default local root is `.agent-loop-guard/issues`.

## ReproLab

```text
alg repro create REPORT [--source DIRECTORY] [--setup-command COMMAND]
                         [--test-command COMMAND] [--image IMAGE]
alg repro run REPRO_ID [--root DIRECTORY] [--timeout SEC]
alg repro status REPRO_ID [--root DIRECTORY]
alg repro diff REPRO_ID [--root DIRECTORY] [--json]
alg repro export REPRO_ID [--root DIRECTORY] [--output FILE]
```

`REPORT` is a Markdown/text file or inline report. Creation, status, diff, and
export work without Docker. `run` delegates every command to the Docker Sandbox.

## Data operations

| Command | Important options | Purpose |
| --- | --- | --- |
| `alg backup` | `--config`, `--output` | Create a local backup archive |
| `alg restore SOURCE` | `--config`, `--force` | Restore an archive |
| `alg cleanup` | `--config`, `--days` | Delete records older than retention |

## MCP Firewall

```text
alg mcp run [--config FILE] [--policy FILE] [--server-id ID] -- COMMAND...
alg mcp serve [--config FILE] [--host HOST] [--port PORT]
alg mcp validate-policy POLICY.yml
alg mcp test-server
```

`mcp run` proxies a child stdio server. Everything after `--` is the upstream command. `mcp serve` starts the same web process as Guard and exposes servers configured under `/mcp/{server_id}`. `test-server` is a deterministic stdio fixture for development.

## Replay

```text
alg replay export TRACE_ID [--config FILE] [--format json|jsonl|otel] [--output FILE]
alg replay import SOURCE [--config FILE]
```

Without `--output`, export writes to stdout. Import accepts JSON and JSONL representations produced by Replay.

## Benchmark

```text
alg bench dataset validate [DATASET]
alg bench run [DATASET] [OPTIONS]
alg bench compare BASELINE CANDIDATE [OPTIONS]
alg bench regression-check BASELINE CANDIDATE [OPTIONS]
```

Run options:

- `--adapter mock|http|cli`, `--variant baseline|regressed`, `--candidate NAME`
- `--output FILE`, `--repetitions N`, `--seed N`, `--timeout SECONDS`
- `--token-budget N`, `--cost-budget-micros N`
- HTTP: `--endpoint`, `--model`, `--api-key`
- CLI: `--command COMMAND`
- MLflow: `--mlflow`, `--experiment NAME`

Comparison options are `--threshold`, `--bootstrap-samples`, `--min-pairs`, and `--seed`. Regression check exits `0`, `1`, or `2` for no regression, regression, or inconclusive respectively.

## Sandbox

```text
alg sandbox create [SOURCE] [--image IMAGE] [--root DIRECTORY]
alg sandbox exec ID [--root DIRECTORY] [--timeout SEC] [--network none|bridge]
                     [--cpus N] [--memory LIMIT] [--pids N] -- COMMAND...
alg sandbox diff ID [--root DIRECTORY] [--json]
alg sandbox apply ID [--root DIRECTORY] [--path PATH ... | --all]
alg sandbox discard ID [--root DIRECTORY]
alg sandbox export ID [--root DIRECTORY] [--output FILE]
```

The default sandbox root is `.agent-loop-guard/sandboxes`, image is `python:3.12-slim`, network is `none`, and export name is `sandbox-export.zip`.

## Configuration selection

Commands accepting `--config` set `ALG_CONFIG` for that invocation. Otherwise configuration is loaded from the path in `ALG_CONFIG`, followed by environment overrides and built-in defaults.
