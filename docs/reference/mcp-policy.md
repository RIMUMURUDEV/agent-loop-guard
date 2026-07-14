# MCP Policy Format

MCP policies are YAML files evaluated locally for every `tools/call`. The current schema version is `1`.

```yaml
version: 1
mode: enforce
default_action: confirm
hide_denied_tools: true

servers:
  filesystem:
    default_action: confirm
    tools:
      read_file:
        action: allow
        paths: ["./**"]
      write_file:
        action: confirm
        paths: ["./src/**", "./tests/**"]
      delete_file:
        action: deny
    groups:
      read_only:
        tools: ["list_*", "search_*"]
        action: allow
```

Validate before use:

```bash
alg mcp validate-policy mcp-policy.yml
```

## Rule precedence

1. Exact tool rule at `servers.SERVER.tools.TOOL`.
2. First matching group in YAML insertion order; group patterns use shell-style wildcards.
3. Server `default_action`.
4. Top-level `default_action`.

Top-level `mode: shadow` converts deny and confirmation outcomes into `shadow_deny`, allowing the request while recording what enforcement would have done.

## Actions

| Action | Behavior |
| --- | --- |
| `allow` | Forward immediately |
| `deny` | Return a policy error and do not call upstream |
| `confirm` | Wait for a decision in the local approval queue |
| `transform` | Remove configured fields and/or cap numeric `limit` |
| `rate_limit` | Allow within a local in-memory sliding window, otherwise deny |
| `shadow_deny` | Record a would-deny decision and forward |

When `hide_denied_tools` is true, tools with an exact or group-level `deny` action are removed from `tools/list`. Argument-dependent denial, such as an escaping path, cannot be predicted during discovery and is enforced at call time.

## Constraints

| Field | Applies to | Meaning |
| --- | --- | --- |
| `paths` | path-like arguments | Allowed project-relative glob patterns; escaping the project root is denied |
| `deny_patterns` | `command` or `argv` | Denied shell text patterns |
| `hosts` | `url` or `uri` | Allowed hostname glob patterns |
| `sql_operations` | `query` or `sql` | Allowed first SQL keyword, such as `SELECT` |
| `max_payload_bytes` | all arguments | Maximum serialized JSON size |
| `remove_fields` | `transform` | Top-level argument keys to remove |
| `max_limit` | `transform` | Upper bound for integer `limit` |
| `limit` | `rate_limit` | Calls allowed per window |
| `window_seconds` | `rate_limit` | Sliding-window duration |

Path checking recognizes `path`, `file`, `filepath`, `file_path`, `directory`, `cwd`, and `root`, case-insensitively. Paths resolve against the proxy process project root.

## Presets

Starter policies live in `app/mcp/presets` for filesystem, shell, git, HTTP, and database servers. Copy a preset into the project and tighten it for the real upstream tool names and argument schemas.

!!! danger
    A policy is only as complete as its tool names and argument mapping. Unknown tools fall back to the configured default. Keep `default_action: confirm` or `deny` while introducing a new server.

## Reload and audit

File-backed policies reload when their modification time changes. Each decision records policy version hash, rule ID, action, reason, argument fingerprint, risk tags, and transformed field names. Raw secrets and full arguments are not intended audit fields.
