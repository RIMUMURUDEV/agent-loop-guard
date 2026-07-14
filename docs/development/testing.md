# Testing

## Local checks

```bash
pip install -e ".[dev,docs]"
ruff check .
pytest -q
mkdocs build --strict
```

Run coverage with the same policy used by CI:

```bash
coverage run -m pytest
coverage report -m
```

The target is at least 75% for shared logic and 90% for critical security modules. Coverage is a floor, not a substitute for adversarial cases.

## Test layout

| Location | Scope |
| --- | --- |
| `tests/unit` | policies, redaction, fingerprints, statistics, workspace safety |
| `tests/integration` | provider proxy, MCP lifecycle/transports, Replay, platform services |
| `tests/integration/test_sandbox_docker.py` | real Docker smoke and isolation behavior |

Security tests should include traversal, symlink escape, approval replay, Origin spoofing, secret leakage, schema mismatch, and dangerous defaults. Benchmark fixtures should have a known statistical effect and an explicit inconclusive case.

## Docker tests

Real Sandbox execution is opt-in locally:

```bash
ALG_DOCKER_TEST=1 pytest -q tests/integration/test_sandbox_docker.py
```

Run it on Linux with a disposable test project. Unit tests verify Docker arguments without requiring a daemon.

## VS Code extension

```bash
cd extensions/vscode
npm run check
npm run package
```

The package step should create a VSIX without development-only files. Before publication, manually test runtime discovery, setup, process lifecycle, both Activity Bar views, and settings on a clean VS Code profile.

## CI matrix

GitHub Actions runs supported Python versions on Windows, Linux, and macOS. Security and coverage jobs run focused checks, and Sandbox Docker tests are Linux-only. Documentation uses MkDocs strict mode so missing nav pages and broken internal references fail the build.

## Manual smoke test

```bash
alg setup --path smoke-test
cd smoke-test
alg doctor
alg guard run
```

In another terminal:

```bash
alg status
alg demo exact-loop --mode shadow
alg demo exact-loop --mode enforce
alg bench dataset validate
```

Confirm the Guard session and Replay trace are visible in the local UI and contain no raw gateway or provider key.
