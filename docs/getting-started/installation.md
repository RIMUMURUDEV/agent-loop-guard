# Installation

## Requirements

- Python 3.11, 3.12, or 3.13.
- Windows, Linux, or macOS for Guard, MCP, Replay, and Benchmark.
- Docker on Linux or through WSL2/Docker Desktop for Sandbox.
- Node.js only when developing or packaging the VS Code extension.

## Install from PyPI

The current public line is an alpha prerelease. Pin it explicitly while the interfaces are still stabilizing. The PyPI distribution is named `agent-loop-guard-runtime`; the installed command remains `alg`.

=== "pipx"

    ```bash
    pipx install agent-loop-guard-runtime==0.6.0a1
    ```

=== "uv"

    ```bash
    uv tool install agent-loop-guard-runtime==0.6.0a1
    ```

=== "virtual environment"

    ```bash
    git clone https://github.com/RIMUMURUDEV/agent-loop-guard.git
    cd agent-loop-guard
    python -m venv .venv
    ```

    === "Windows PowerShell"

        ```powershell
        .venv\Scripts\Activate.ps1
        pip install -e ".[dev]"
        ```

To install the newest repository revision instead, pass the GitHub URL to `pipx` or `uv tool install`.

    === "Linux/macOS"

        ```bash
        source .venv/bin/activate
        pip install -e ".[dev]"
        ```

## Optional dependency groups

The default installation includes Guard, MCP, Replay, the web UI, and JSONL benchmarks.

| Extra | Install command | Adds |
| --- | --- | --- |
| `bench` | `pip install "agent-loop-guard-runtime[bench]"` | PyArrow, DuckDB, MLflow |
| `sandbox` | `pip install "agent-loop-guard-runtime[sandbox]"` | Marker extra; Docker remains external |
| `docs` | `pip install "agent-loop-guard-runtime[docs]"` | MkDocs Material |
| `dev` | `pip install "agent-loop-guard-runtime[dev]"` | pytest, coverage, Ruff, HTTP mocks |

`mcp` is currently a compatibility marker and adds no package beyond the default dependencies.

## Verify the installation

```bash
alg --help
alg doctor
```

`doctor` checks Python, storage, the configured port, Docker, and WSL. Missing Docker is a warning because only the Sandbox module depends on it.

## Upgrade

=== "pipx"

    ```bash
    pipx upgrade agent-loop-guard-runtime
    ```

=== "uv"

    ```bash
    uv tool upgrade agent-loop-guard-runtime
    ```

=== "editable checkout"

    ```bash
    git pull
    pip install -e ".[dev]"
    ```

Database migrations run automatically at application startup.

## Uninstall

Remove the Python package with the tool manager that installed it. Local project state remains in `agent-loop-guard.yml`, `.agent-loop-guard/`, and the configured SQLite path until removed manually.
