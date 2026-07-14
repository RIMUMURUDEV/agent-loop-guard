from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx
import uvicorn

from app.core.config import SAMPLE_CONFIG, AppConfig


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

    demo = sub.add_parser("demo", help="run a demo scenario against a running gateway")
    demo.add_argument("scenario", nargs="?", default="exact-loop")
    demo.add_argument("--mode", choices=["shadow", "enforce"], default="shadow")
    demo.add_argument("--base-url", default="http://127.0.0.1:8787")
    demo.set_defaults(func=_cmd_demo)

    sample = sub.add_parser("sample-config", help="print the sample YAML config")
    sample.set_defaults(func=_cmd_sample_config)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
