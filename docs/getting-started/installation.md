# Installation

## Requirements

- Python 3.11, 3.12, or 3.13.
- Windows, Linux, or macOS for Guard, MCP, Replay, and Benchmark.
- Docker on Linux or through WSL2/Docker Desktop for Sandbox.
- Node.js only when developing or packaging the VS Code extension.

## Install the current alpha

Install the public alpha from [PyPI](https://pypi.org/project/agent-loop-guard-runtime/). The distribution name is `agent-loop-guard-runtime`, and the installed command is `alg`.

=== "pipx"

    ```bash
    pipx install agent-loop-guard-runtime
    ```

=== "uv"

    ```bash
    uv tool install agent-loop-guard-runtime
    ```

=== "virtual environment"

    ```bash
    git clone https://github.com/RIMUMURUDEV/agent-loop-guard.git
    cd agent-loop-guard
    python -m venv .venv
    ```

    On Windows PowerShell:

    ```powershell
    .venv\Scripts\Activate.ps1
    pip install -e "."
    ```

    On Linux or macOS:

    ```bash
    source .venv/bin/activate
    pip install -e "."
    ```

The package is published through a PyPI Trusted Publisher bound to this repository's `publish-pypi.yml` workflow. No long-lived PyPI token is stored in GitHub.

## Optional dependency groups

The default installation includes Guard, MCP, Replay, the web UI, and JSONL benchmarks. Install optional groups from a cloned checkout:

| Extra | Install command | Adds |
| --- | --- | --- |
| `bench` | `pip install -e ".[bench]"` | PyArrow, DuckDB, MLflow |
| `sandbox` | `pip install -e ".[sandbox]"` | Marker extra; Docker remains external |
| `docs` | `pip install -e ".[docs]"` | MkDocs Material |
| `dev` | `pip install -e ".[dev]"` | pytest, coverage, Ruff, HTTP mocks |

`mcp` is currently a compatibility marker and adds no package beyond the default dependencies.

## Verify the installation

```bash
alg --help
alg doctor
```

`doctor` checks Python, storage, the configured port, Docker, and WSL. Missing Docker is a warning because only the Sandbox module depends on it.

## Upgrade

Upgrade the public package with the same tool used for installation:

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
