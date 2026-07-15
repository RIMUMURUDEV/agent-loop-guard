# Release Process

Only the repository owner or an authorized maintainer publishes releases.

## Prepare

1. Choose a version consistent with pre-1.0 semantic versioning.
2. Replace the development version in `pyproject.toml` and the VS Code manifest where applicable.
3. Move relevant entries in `CHANGELOG.md` under the release date.
4. Update the project status and any compatibility notes.
5. Run the complete checks on a clean checkout.

```bash
ruff check .
pytest -q
mkdocs build --strict
python -m build
python -m twine check dist/*

cd extensions/vscode
npm run check
npm run package
```

Inspect wheel/sdist contents, install the wheel in a fresh virtual environment, and run `alg doctor` plus the five-minute quickstart.

## Publish

1. Merge the reviewed release commit to `main`.
2. Create an annotated `vX.Y.Z` tag and push it.
3. Publish a GitHub Release and let GitHub Actions attach the wheel, sdist, and VSIX.
4. After configuring a PyPI trusted publisher, run the `publish-pypi` workflow manually.
5. Publish the VSIX with the owner-controlled Marketplace publisher token.
6. Verify GitHub Pages, PyPI installation, VSIX installation, and release checksums.

Never place PyPI, Marketplace, provider, or signing tokens in the repository. Prefer short-lived or OIDC trusted publishing credentials.

## Rollback

Published package versions are immutable. If a defect escapes, mark the GitHub Release clearly, yank the affected PyPI version when appropriate, fix forward with a patch version, and document migration or data-restoration steps. Do not rewrite a published tag.

## Development releases

Prereleases such as `0.6.0a1` are not stable promises. They may be published for testing, but should not replace a normal release without clean-install verification.
