# Contributing to Agent Loop Guard

Thanks for considering a contribution. Start with the full [contributing guide](docs/development/contributing.md), then run:

```bash
pip install -e ".[dev,docs]"
ruff check .
pytest -q
mkdocs build --strict
```

Please keep changes focused, add tests for behavior changes, preserve privacy defaults, and document security limitations honestly. Contributions are licensed under Apache-2.0.
