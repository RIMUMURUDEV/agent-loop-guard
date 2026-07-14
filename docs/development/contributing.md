# Contributing

Contributions are welcome, including small documentation and test improvements. This is a part-time educational project, so maintainers cannot promise fast reviews or support.

## Development setup

```bash
git clone https://github.com/RIMUMURUDEV/agent-loop-guard.git
cd agent-loop-guard
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -e ".[dev,docs]"
pytest -q
ruff check .
mkdocs build --strict
```

Use Python 3.11 through 3.13. Docker is optional unless changing Sandbox behavior.

## Choose a change

- Search existing issues and pull requests first.
- Prefer one focused behavior per pull request.
- For security-sensitive behavior, open an issue describing the desired contract without publishing an exploit.
- Discuss major architecture, dependencies, schema changes, or breaking CLI changes before implementing them.

## Engineering expectations

- Follow existing package boundaries and keep optional dependencies behind extras.
- Add or update tests for behavior changes.
- Preserve redaction and metadata-only defaults.
- Do not add telemetry, closed services, or mandatory network calls.
- Use versioned structured formats instead of ad hoc log text.
- Keep Windows, Linux, and macOS behavior in mind; mark Linux-only behavior clearly.
- Update the relevant guide, reference page, status page, and changelog.

## Pull request checklist

```text
[ ] Scope is focused and linked to an issue when appropriate
[ ] Tests cover success and failure paths
[ ] ruff check . passes
[ ] pytest passes on the available platform
[ ] mkdocs build --strict passes
[ ] Security/privacy impact is described
[ ] User-visible behavior and CHANGELOG are updated
```

Use clear commit messages such as `feat(mcp): add host allowlist test` or `docs: explain replay exports`. Maintainers may squash a pull request at merge.

## Documentation style

Write user-facing documentation in English for broad accessibility. The Russian overview can summarize important onboarding changes. Commands must be runnable, limitations should be explicit, and features that are planned must not be described as implemented.

## License

By contributing, you agree that your contribution is licensed under Apache-2.0, the repository license.
