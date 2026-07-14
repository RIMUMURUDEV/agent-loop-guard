# Benchmark and Regression Lab

Benchmark Lab compares agent or model configurations on versioned tasks. The default path is deterministic and does not require a paid API.

## Starter dataset

The bundled `starter-v1` dataset contains 30 tasks: 10 easy, 10 medium, and 10 hard. Validate it before a run:

```bash
alg bench dataset validate
alg bench dataset validate path/to/dataset.json
```

A dataset is a JSON object with a version and a `tasks` array. Each task has an `id`, `difficulty`, `prompt`, `expected`, `scorer`, optional tags, and optional metadata.

Supported built-in scorers are `exact`, `contains`, and `json_equal`. A scorer named `python:package.module:function` calls a local Python function. Only use custom scorers from code you trust.

## Run a benchmark

```bash
alg bench run --adapter mock --candidate baseline --output baseline.jsonl
alg bench run --adapter mock --variant regressed --candidate candidate --output candidate.jsonl
```

Adapters:

| Adapter | Purpose | Required options |
| --- | --- | --- |
| `mock` | Deterministic development and CI | none; `--variant` selects baseline or regressed behavior |
| `http` | OpenAI-compatible endpoint | `--endpoint`; optionally `--model` and `--api-key` |
| `cli` | External command | `--command` |

Control reproducibility and spending with `--repetitions`, `--seed`, `--timeout`, `--token-budget`, and `--cost-budget-micros`. Budgets stop scheduling new tasks after the accumulated value reaches the limit; they do not cancel a request already running.

Each observation records task and candidate IDs, repetition, seed, score, duration, token counts, cost in micro-units, output SHA-256, error, and metadata. Model output itself is not stored in the observation file.

## Compare runs

```bash
alg bench compare baseline.jsonl candidate.jsonl
alg bench regression-check baseline.jsonl candidate.jsonl
```

The comparison pairs observations by task and repetition and calculates a 95% paired bootstrap confidence interval for `candidate - baseline`.

| Verdict | Meaning | `regression-check` exit code |
| --- | --- | --- |
| `no_regression` | The confidence interval does not establish a regression | `0` |
| `regression` | The upper confidence bound is below the negative threshold | `1` |
| `inconclusive` | Fewer than `--min-pairs` matched observations | `2` |

`compare` prints the same report but is intended for exploration. `regression-check` is the CI gate.

## Optional analytics

Install the benchmark extra for Parquet, DuckDB, and MLflow support:

```bash
pipx inject agent-loop-guard-runtime "duckdb" "pyarrow" "mlflow"
# source checkout
pip install -e ".[bench]"
```

Pass a `.parquet` output path to write Parquet. Add `--mlflow` and optionally `--experiment NAME` to track the run in a configured MLflow instance.

!!! warning
    Real API adapters can spend money and transmit task prompts. Start with the mock adapter, set hard budgets, and enable paid runs manually.

## GitHub Actions example

```yaml
- name: Check benchmark regression
  run: |
    alg bench run --adapter mock --candidate candidate --output candidate.jsonl
    alg bench regression-check benchmarks/baseline.jsonl candidate.jsonl
```

Keep a reviewed baseline artifact in the repository and regenerate it only when the intended behavior changes.
