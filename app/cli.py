from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn
import yaml

from app.core.config import SAMPLE_CONFIG, AppConfig
from app.db.repository import Repository
from app.db.session import build_engine, build_session_factory, init_db
from app.platform.maintenance import (
    build_doctor_report,
    cleanup_old_data,
    create_backup,
    fetch_status,
    restore_backup,
)
from app.platform.setup import setup_workspace
from app.replay.formats import jsonl_to_trace, trace_to_jsonl, trace_to_otel


def _config(path: str | None = None) -> AppConfig:
    if path:
        os.environ["ALG_CONFIG"] = path
    return AppConfig.from_env()


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"{path} already exists. Use --force to overwrite.")
        return 1
    path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    print(f"Wrote {path}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from app.main import create_app

    if args.config:
        os.environ["ALG_CONFIG"] = args.config
    config = AppConfig.from_env()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    uvicorn.run(create_app(config), host=config.host, port=config.port, log_level=args.log_level)
    return 0


def _cmd_setup(args: argparse.Namespace) -> int:
    result = setup_workspace(
        Path(args.path).resolve(),
        host=args.host,
        port=args.port,
        gateway_key=args.gateway_key,
        force=args.force,
    )
    print(f"Config: {result['config']}")
    print(f"Agent profiles: {Path(str(result['profiles'][0])).parent}")
    print(f"Dashboard: {result['base_url']}")
    if result.get("gateway_key"):
        print("A new gateway key was written to the config file.")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = build_doctor_report(_config(args.config))
    for check in report["checks"]:
        marker = "OK" if check["ok"] else "WARN" if check["name"] == "docker" else "FAIL"
        print(f"[{marker}] {check['name']}: {check['detail']}")
    return 0 if report["ok"] else 1


def _cmd_status(args: argparse.Namespace) -> int:
    status = fetch_status(args.base_url)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    elif status["running"]:
        stats = status.get("stats", {})
        print(
            "Agent Loop Guard is running: "
            f"sessions={stats.get('sessions', 0)} requests={stats.get('requests', 0)} "
            f"traces={stats.get('traces', 0)} blocks={stats.get('blocks', 0)}"
        )
    else:
        print(f"Agent Loop Guard is offline at {args.base_url}: {status['error']}")
    return 0 if status["running"] else 1


def _cmd_open(args: argparse.Namespace) -> int:
    url = args.base_url.rstrip("/") + ("/replay" if args.replay else "")
    if not webbrowser.open(url):
        print(url)
    return 0


def _cmd_backup(args: argparse.Namespace) -> int:
    config = _config(args.config)
    default_name = f"agent-loop-guard-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
    destination = Path(args.output or default_name).resolve()
    path = create_backup(config, destination, Path(args.config) if args.config else None)
    print(f"Backup written to {path}")
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        restored = restore_backup(_config(args.config), Path(args.source), force=args.force)
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"Database restored to {restored}")
    return 0


def _cmd_cleanup(args: argparse.Namespace) -> int:
    config = _config(args.config)
    engine = build_engine(config)
    init_db(engine, config)
    with build_session_factory(engine)() as db:
        result = cleanup_old_data(db, args.days or config.retention_days)
    print(f"Removed {result['sessions']} sessions and {result['traces']} traces.")
    return 0


def _cmd_mcp_run(args: argparse.Namespace) -> int:
    from app.mcp.stdio import run_stdio_proxy

    command = list(args.upstream)
    if command and command[0] == "--":
        command = command[1:]
    try:
        return run_stdio_proxy(
            command,
            policy_path=args.policy,
            server_id=args.server_id,
            config=_config(args.config),
        )
    except (OSError, ValueError) as exc:
        print(f"MCP proxy failed: {exc}", file=sys.stderr)
        return 1


def _cmd_mcp_validate(args: argparse.Namespace) -> int:
    from app.mcp.policy import MCPPolicyError
    from app.mcp.stdio import validate_policy_file

    try:
        errors = validate_policy_file(args.path)
    except (MCPPolicyError, OSError, yaml.YAMLError) as exc:
        print(f"Invalid policy: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"Policy is valid: {args.path}")
    return 0


def _cmd_mcp_test_server(_: argparse.Namespace) -> int:
    from app.mcp.stdio import run_mock_stdio_server

    return run_mock_stdio_server()


def _repository(config: AppConfig):
    engine = build_engine(config)
    init_db(engine, config)
    return build_session_factory(engine)


def _cmd_replay_export(args: argparse.Namespace) -> int:
    with _repository(_config(args.config))() as db:
        bundle = Repository(db).trace_export(args.trace_id)
    if bundle is None:
        print(f"Trace not found: {args.trace_id}", file=sys.stderr)
        return 1
    if args.format == "jsonl":
        content = trace_to_jsonl(bundle)
    else:
        payload = trace_to_otel(bundle) if args.format == "otel" else bundle
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"Trace exported to {Path(args.output).resolve()}")
    else:
        print(content, end="")
    return 0


def _cmd_replay_import(args: argparse.Namespace) -> int:
    source = Path(args.source)
    try:
        text = source.read_text(encoding="utf-8")
        bundle = jsonl_to_trace(text) if source.suffix.lower() == ".jsonl" else json.loads(text)
        with _repository(_config(args.config))() as db:
            run = Repository(db).import_trace_bundle(bundle)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Replay import failed: {exc}", file=sys.stderr)
        return 1
    print(f"Imported trace: {run.id}")
    return 0


def _cmd_bench_dataset_validate(args: argparse.Namespace) -> int:
    from app.benchmark.dataset import load_dataset

    try:
        payload, tasks = load_dataset(args.path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid dataset: {exc}", file=sys.stderr)
        return 1
    counts = {difficulty: 0 for difficulty in ("easy", "medium", "hard")}
    for task in tasks:
        counts[task.difficulty] += 1
    print(
        f"Dataset {payload['version']} is valid: {len(tasks)} tasks "
        f"(easy={counts['easy']}, medium={counts['medium']}, hard={counts['hard']})"
    )
    return 0


def _benchmark_adapter(args: argparse.Namespace):
    from app.benchmark.adapters import CLIAdapter, HTTPAdapter, MockAdapter

    if args.adapter == "mock":
        return MockAdapter(args.variant)
    if args.adapter == "http":
        if not args.endpoint:
            raise ValueError("--endpoint is required for the HTTP adapter")
        return HTTPAdapter(args.endpoint, args.model, args.api_key)
    if not args.command:
        raise ValueError("--command is required for the CLI adapter")
    return CLIAdapter(args.command)


def _cmd_bench_run(args: argparse.Namespace) -> int:
    from app.benchmark.dataset import load_dataset
    from app.benchmark.runner import RunLimits, run_benchmark
    from app.benchmark.storage import log_to_mlflow, save_observations

    try:
        _, tasks = load_dataset(args.dataset)
        observations = run_benchmark(
            tasks,
            _benchmark_adapter(args),
            args.candidate,
            RunLimits(
                repetitions=args.repetitions,
                seed=args.seed,
                timeout_seconds=args.timeout,
                token_budget=args.token_budget,
                cost_budget_micros=args.cost_budget_micros,
            ),
        )
        destination = save_observations(observations, args.output)
        mlflow_run = log_to_mlflow(observations, args.experiment) if args.mlflow else None
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1
    average = sum(item.score for item in observations) / len(observations) if observations else 0
    print(f"Saved {len(observations)} observations to {destination.resolve()}; score={average:.3f}")
    if mlflow_run:
        print(f"MLflow run: {mlflow_run}")
    return 0


def _benchmark_comparison(args: argparse.Namespace) -> dict:
    from app.benchmark.statistics import paired_bootstrap
    from app.benchmark.storage import load_observations

    return paired_bootstrap(
        load_observations(args.baseline),
        load_observations(args.candidate),
        samples=args.bootstrap_samples,
        seed=args.seed,
        min_pairs=args.min_pairs,
        regression_threshold=args.threshold,
    )


def _cmd_bench_compare(args: argparse.Namespace) -> int:
    try:
        result = _benchmark_comparison(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Benchmark comparison failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cmd_bench_regression_check(args: argparse.Namespace) -> int:
    try:
        result = _benchmark_comparison(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Regression check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return {"no_regression": 0, "regression": 1, "inconclusive": 2}[result["verdict"]]


def _sandbox(args: argparse.Namespace):
    from app.sandbox.workspace import SandboxWorkspace

    return SandboxWorkspace(Path(args.root) if args.root else None)


def _cmd_sandbox_create(args: argparse.Namespace) -> int:
    try:
        manifest = _sandbox(args).create(Path(args.source), args.image)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Sandbox creation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Created sandbox {manifest['id']} using {manifest['image']}")
    return 0


def _cmd_sandbox_exec(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    try:
        result = _sandbox(args).execute(
            args.session_id,
            command,
            timeout=args.timeout,
            network=args.network,
            cpus=args.cpus,
            memory=args.memory,
            pids=args.pids,
        )
    except (OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"Sandbox execution failed: {exc}", file=sys.stderr)
        return 1
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return int(result.returncode)


def _cmd_sandbox_diff(args: argparse.Namespace) -> int:
    try:
        changes = _sandbox(args).diff(args.session_id)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"Sandbox diff failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(changes, indent=2))
    else:
        for change in changes:
            print(f"{change['status']:8} {change['path']}")
            if change["patch"]:
                print(change["patch"], end="")
    return 0


def _cmd_sandbox_apply(args: argparse.Namespace) -> int:
    if not args.all and not args.path:
        print("Select --path at least once or pass --all.", file=sys.stderr)
        return 1
    try:
        applied = _sandbox(args).apply(args.session_id, None if args.all else args.path)
    except (OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"Sandbox apply failed: {exc}", file=sys.stderr)
        return 1
    print(f"Applied {len(applied)} path(s).")
    return 0


def _cmd_sandbox_discard(args: argparse.Namespace) -> int:
    try:
        _sandbox(args).discard(args.session_id)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"Sandbox discard failed: {exc}", file=sys.stderr)
        return 1
    print(f"Discarded sandbox {args.session_id}")
    return 0


def _cmd_sandbox_export(args: argparse.Namespace) -> int:
    try:
        destination = _sandbox(args).export(args.session_id, Path(args.output))
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"Sandbox export failed: {exc}", file=sys.stderr)
        return 1
    print(f"Sandbox exported to {destination}")
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    url = args.base_url.rstrip("/") + "/api/demo/run"
    payload = {"scenario": args.scenario, "mode": args.mode}
    with httpx.Client(timeout=10) as client:
        response = client.post(url, json=payload)
    response.raise_for_status()
    session = response.json()["session"]
    print(f"Demo session: {session['id']}")
    print(f"flags={session['flagged_count']} blocks={session['blocked_count']} requests={session['request_count']}")
    return 0


def _cmd_sample_config(_: argparse.Namespace) -> int:
    print(SAMPLE_CONFIG)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alg", description="Agent Loop Guard")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a sample YAML config")
    init.add_argument("--path", default="agent-loop-guard.yml")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=_cmd_init)

    run = sub.add_parser("run", help="start the local gateway")
    run.add_argument("--config")
    run.add_argument("--host")
    run.add_argument("--port", type=int)
    run.add_argument("--log-level", default="info")
    run.set_defaults(func=_cmd_run)

    guard = sub.add_parser("guard", help="guard gateway commands")
    guard_sub = guard.add_subparsers(dest="guard_command", required=True)
    guard_run = guard_sub.add_parser("run", help="start the local gateway")
    guard_run.add_argument("--config")
    guard_run.add_argument("--host")
    guard_run.add_argument("--port", type=int)
    guard_run.add_argument("--log-level", default="info")
    guard_run.set_defaults(func=_cmd_run)

    setup = sub.add_parser("setup", help="create config and agent connection profiles")
    setup.add_argument("--path", default=".")
    setup.add_argument("--host", default="127.0.0.1")
    setup.add_argument("--port", type=int, default=8787)
    setup.add_argument("--gateway-key")
    setup.add_argument("--force", action="store_true")
    setup.set_defaults(func=_cmd_setup)

    doctor = sub.add_parser("doctor", help="check the local installation")
    doctor.add_argument("--config")
    doctor.set_defaults(func=_cmd_doctor)

    status = sub.add_parser("status", help="show local daemon status")
    status.add_argument("--base-url", default="http://127.0.0.1:8787")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=_cmd_status)

    open_command = sub.add_parser("open", help="open the local dashboard")
    open_command.add_argument("--base-url", default="http://127.0.0.1:8787")
    open_command.add_argument("--replay", action="store_true")
    open_command.set_defaults(func=_cmd_open)

    backup = sub.add_parser("backup", help="create a local data backup")
    backup.add_argument("--config")
    backup.add_argument("--output")
    backup.set_defaults(func=_cmd_backup)

    restore = sub.add_parser("restore", help="restore a local data backup")
    restore.add_argument("source")
    restore.add_argument("--config")
    restore.add_argument("--force", action="store_true")
    restore.set_defaults(func=_cmd_restore)

    cleanup = sub.add_parser("cleanup", help="delete data older than the retention window")
    cleanup.add_argument("--config")
    cleanup.add_argument("--days", type=int)
    cleanup.set_defaults(func=_cmd_cleanup)

    mcp = sub.add_parser("mcp", help="MCP Permission Firewall commands")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)

    mcp_run = mcp_sub.add_parser("run", help="proxy an MCP stdio server")
    mcp_run.add_argument("--config")
    mcp_run.add_argument("--policy")
    mcp_run.add_argument("--server-id", default="stdio")
    mcp_run.add_argument("upstream", nargs=argparse.REMAINDER)
    mcp_run.set_defaults(func=_cmd_mcp_run)

    mcp_serve = mcp_sub.add_parser("serve", help="serve configured Streamable HTTP MCP proxies")
    mcp_serve.add_argument("--config")
    mcp_serve.add_argument("--host")
    mcp_serve.add_argument("--port", type=int)
    mcp_serve.add_argument("--log-level", default="info")
    mcp_serve.set_defaults(func=_cmd_run)

    mcp_validate = mcp_sub.add_parser("validate-policy", help="validate an MCP policy YAML")
    mcp_validate.add_argument("path")
    mcp_validate.set_defaults(func=_cmd_mcp_validate)

    mcp_test = mcp_sub.add_parser("test-server", help="run a deterministic MCP stdio server")
    mcp_test.set_defaults(func=_cmd_mcp_test_server)

    replay = sub.add_parser("replay", help="Replay import and export commands")
    replay_sub = replay.add_subparsers(dest="replay_command", required=True)
    replay_export = replay_sub.add_parser("export", help="export a trace")
    replay_export.add_argument("trace_id")
    replay_export.add_argument("--config")
    replay_export.add_argument("--format", choices=["json", "jsonl", "otel"], default="json")
    replay_export.add_argument("--output")
    replay_export.set_defaults(func=_cmd_replay_export)

    replay_import = replay_sub.add_parser("import", help="import a JSON or JSONL trace")
    replay_import.add_argument("source")
    replay_import.add_argument("--config")
    replay_import.set_defaults(func=_cmd_replay_import)

    bench = sub.add_parser("bench", help="Benchmark and regression lab")
    bench_sub = bench.add_subparsers(dest="bench_command", required=True)
    bench_dataset = bench_sub.add_parser("dataset", help="dataset operations")
    bench_dataset_sub = bench_dataset.add_subparsers(dest="dataset_command", required=True)
    bench_validate = bench_dataset_sub.add_parser("validate", help="validate a versioned dataset")
    bench_validate.add_argument("path", nargs="?")
    bench_validate.set_defaults(func=_cmd_bench_dataset_validate)

    bench_run = bench_sub.add_parser("run", help="run a benchmark dataset")
    bench_run.add_argument("dataset", nargs="?")
    bench_run.add_argument("--adapter", choices=["mock", "http", "cli"], default="mock")
    bench_run.add_argument("--variant", choices=["baseline", "regressed"], default="baseline")
    bench_run.add_argument("--candidate", default="candidate")
    bench_run.add_argument("--output", default="benchmark-observations.jsonl")
    bench_run.add_argument("--repetitions", type=int, default=1)
    bench_run.add_argument("--seed", type=int, default=0)
    bench_run.add_argument("--timeout", type=float, default=30.0)
    bench_run.add_argument("--token-budget", type=int, default=0)
    bench_run.add_argument("--cost-budget-micros", type=int, default=0)
    bench_run.add_argument("--endpoint")
    bench_run.add_argument("--model", default="demo-model")
    bench_run.add_argument("--api-key")
    bench_run.add_argument("--command")
    bench_run.add_argument("--mlflow", action="store_true")
    bench_run.add_argument("--experiment", default="agent-loop-guard")
    bench_run.set_defaults(func=_cmd_bench_run)

    for name, handler in (
        ("compare", _cmd_bench_compare),
        ("regression-check", _cmd_bench_regression_check),
    ):
        command = bench_sub.add_parser(name, help=f"{name.replace('-', ' ')} two benchmark runs")
        command.add_argument("baseline")
        command.add_argument("candidate")
        command.add_argument("--threshold", type=float, default=0.0)
        command.add_argument("--bootstrap-samples", type=int, default=2000)
        command.add_argument("--min-pairs", type=int, default=10)
        command.add_argument("--seed", type=int, default=0)
        command.set_defaults(func=handler)

    sandbox = sub.add_parser("sandbox", help="Docker sandbox technical preview")
    sandbox_sub = sandbox.add_subparsers(dest="sandbox_command", required=True)

    sandbox_create = sandbox_sub.add_parser("create", help="create an isolated workspace copy")
    sandbox_create.add_argument("source", nargs="?", default=".")
    sandbox_create.add_argument("--image", default="python:3.12-slim")
    sandbox_create.add_argument("--root")
    sandbox_create.set_defaults(func=_cmd_sandbox_create)

    sandbox_exec = sandbox_sub.add_parser("exec", help="execute a command in the container")
    sandbox_exec.add_argument("session_id")
    sandbox_exec.add_argument("--root")
    sandbox_exec.add_argument("--timeout", type=float, default=300)
    sandbox_exec.add_argument("--network", choices=["none", "bridge"], default="none")
    sandbox_exec.add_argument("--cpus", type=float, default=1.0)
    sandbox_exec.add_argument("--memory", default="1g")
    sandbox_exec.add_argument("--pids", type=int, default=128)
    sandbox_exec.add_argument("command", nargs=argparse.REMAINDER)
    sandbox_exec.set_defaults(func=_cmd_sandbox_exec)

    sandbox_diff = sandbox_sub.add_parser("diff", help="preview workspace changes")
    sandbox_diff.add_argument("session_id")
    sandbox_diff.add_argument("--root")
    sandbox_diff.add_argument("--json", action="store_true")
    sandbox_diff.set_defaults(func=_cmd_sandbox_diff)

    sandbox_apply = sandbox_sub.add_parser("apply", help="apply selected changes to the source")
    sandbox_apply.add_argument("session_id")
    sandbox_apply.add_argument("--root")
    sandbox_apply.add_argument("--path", action="append")
    sandbox_apply.add_argument("--all", action="store_true")
    sandbox_apply.set_defaults(func=_cmd_sandbox_apply)

    sandbox_discard = sandbox_sub.add_parser("discard", help="delete a sandbox workspace")
    sandbox_discard.add_argument("session_id")
    sandbox_discard.add_argument("--root")
    sandbox_discard.set_defaults(func=_cmd_sandbox_discard)

    sandbox_export = sandbox_sub.add_parser("export", help="export workspace and diff as a zip")
    sandbox_export.add_argument("session_id")
    sandbox_export.add_argument("--root")
    sandbox_export.add_argument("--output", default="sandbox-export.zip")
    sandbox_export.set_defaults(func=_cmd_sandbox_export)

    demo = sub.add_parser("demo", help="run a demo scenario against a running gateway")
    demo.add_argument("scenario", nargs="?", default="exact-loop")
    demo.add_argument("--mode", choices=["shadow", "enforce"], default="shadow")
    demo.add_argument("--base-url", default="http://127.0.0.1:8787")
    demo.set_defaults(func=_cmd_demo)

    sample = sub.add_parser("sample-config", help="print the sample YAML config")
    sample.set_defaults(func=_cmd_sample_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
