from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.benchmark.models import Observation


def save_observations(rows: list[Observation], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = [row.to_dict() for row in rows]
    if destination.suffix.lower() == ".parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError(
                "Parquet output requires: pip install 'agent-loop-guard-runtime[bench]'"
            ) from exc
        pq.write_table(pa.Table.from_pylist(payload), destination)
    else:
        destination.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in payload),
            encoding="utf-8",
        )
    return destination


def load_observations(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError(
                "Parquet input requires: pip install 'agent-loop-guard-runtime[bench]'"
            ) from exc
        return pq.read_table(source).to_pylist()
    return [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize_with_duckdb(path: str | Path) -> list[dict[str, Any]]:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "DuckDB analysis requires: pip install 'agent-loop-guard-runtime[bench]'"
        ) from exc
    source = str(Path(path).resolve()).replace("'", "''")
    reader = "read_parquet" if str(path).lower().endswith(".parquet") else "read_json_auto"
    connection = duckdb.connect(":memory:")
    rows = connection.execute(
        f"SELECT difficulty, avg(score) AS score, count(*) AS observations "
        f"FROM {reader}('{source}') GROUP BY difficulty ORDER BY difficulty"
    ).fetchall()
    return [
        {"difficulty": difficulty, "score": score, "observations": observations}
        for difficulty, score, observations in rows
    ]


def log_to_mlflow(rows: list[Observation], experiment: str = "agent-loop-guard") -> str:
    try:
        import mlflow
    except ImportError as exc:
        raise RuntimeError(
            "MLflow tracking requires: pip install 'agent-loop-guard-runtime[bench]'"
        ) from exc
    scores = [row.score for row in rows]
    mlflow.set_experiment(experiment)
    with mlflow.start_run() as run:
        mlflow.log_param("candidate", rows[0].candidate if rows else "unknown")
        mlflow.log_param("observations", len(rows))
        mlflow.log_metric("score", sum(scores) / len(scores) if scores else 0.0)
        mlflow.log_metric("tokens", sum(row.input_tokens + row.output_tokens for row in rows))
        return run.info.run_id
