# Troubleshooting

Start with:

```bash
alg doctor
alg status --json
```

## `alg` is not found

Ensure the `pipx` binary directory is on `PATH`:

```bash
pipx ensurepath
```

Restart the terminal afterward. In a source checkout, activate `.venv` or use `.venv\Scripts\python.exe -m app.cli doctor` on Windows.

## Port 8787 is already in use

Probe the existing process with `alg status`. If it is another ALG daemon, reuse it or stop the process that launched it. Otherwise select a port consistently:

```bash
alg guard run --port 8790
alg status --base-url http://127.0.0.1:8790
```

Update agent and VS Code settings to the same address.

## Gateway returns 401

The agent key must match `gateway_key` or `ALG_GATEWAY_KEY`. For OpenAI-compatible clients use a Bearer token; Anthropic-compatible clients may send `x-api-key`. Replace the demo key in any non-demo setup.

## Requests do not appear

Confirm the agent uses the ALG base URL, not the provider URL directly. Add stable `x-alg-project-id`, `x-alg-session-id`, and `x-alg-agent-id` headers when the client supports custom headers.

## MCP server is missing or tools disappear

- Check `mcp.servers` and the `{server_id}` in the URL.
- Validate the policy with `alg mcp validate-policy`.
- A denied tool is intentionally hidden when `hide_denied_tools: true`.
- Inspect `/mcp` and `/api/v1/mcp/events` for redacted decisions.
- Preserve the `Mcp-Session-Id` header across HTTP requests.

For browser clients, ensure the exact Origin is in `mcp.allowed_origins`.

## MCP path is unexpectedly denied

Policy paths resolve against the proxy process working directory. Start ALG from the project root, use the intended `paths` globs, and avoid symlinks or `..`. Absolute paths outside the project root are denied.

## Replay cost is zero

Cost requires model pricing and token usage. Point the runtime at a pricing YAML compatible with the example file, verify the model name matches, and confirm the provider returned input/output token counts. Missing pricing does not invent a cost.

## Database or migration error

Stop all daemon processes, create `alg backup`, check the configured SQLite path, and rerun `alg doctor`. Do not delete the database as a first response. Restore only into the matching project state and use `--force` deliberately.

## Docker unavailable

```bash
docker version
```

Both the CLI and daemon must be available. On Windows, start Docker Desktop with WSL2 integration enabled. Sandbox cannot run without Docker; Guard, MCP, Replay, and Benchmark still work.

## Sandbox apply conflict

The host source changed after sandbox creation. Preserve those host edits, review `alg sandbox diff`, then create a fresh sandbox from the new source. The conflict is intentional overwrite protection.

## Documentation build fails

```bash
pip install -e ".[docs]"
mkdocs build --strict
```

Strict mode treats broken internal links, missing navigation pages, and warnings as failures. File links in documentation are relative to the page, while repository README links are relative to the repository root.

## Still stuck

Open a GitHub issue with OS, Python version, ALG version, sanitized configuration, exact command, exit code, and redacted output. Never include API keys, raw prompts, proprietary source, or unreviewed trace exports.
