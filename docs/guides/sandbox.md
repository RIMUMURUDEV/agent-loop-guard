# Sandbox Technical Preview

Sandbox runs commands against a private copy of a project in a Docker container. The original source is changed only by an explicit `apply` command.

!!! warning
    This module is a Linux-first technical preview and a defense-in-depth development tool. It is not a certified security boundary and does not claim protection from unknown container or kernel vulnerabilities.

## Requirements

- Docker CLI and a running Docker daemon
- Linux, or Windows through WSL2 and Docker Desktop
- Permission to pull the selected image

Check Docker first:

```bash
docker version
```

## Workflow

```bash
alg sandbox create .
# prints an id such as sbx_0123456789abcdef01234567

alg sandbox exec SANDBOX_ID -- pytest -q
alg sandbox diff SANDBOX_ID
alg sandbox apply SANDBOX_ID --path app/example.py
alg sandbox discard SANDBOX_ID
```

Use `--all` instead of repeated `--path` options only after reviewing the complete diff. Export evidence and the copied workspace with:

```bash
alg sandbox export SANDBOX_ID --output sandbox-export.zip
```

## Isolation controls

The runner:

- copies the source into both an immutable comparison snapshot and a working directory;
- refuses source trees containing symlinks;
- excludes `.git`, `.agent-loop-guard`, `.venv`, `node_modules`, and `__pycache__`;
- runs as a non-root UID/GID, drops all capabilities, enables `no-new-privileges`, and uses a read-only container root;
- mounts only the copied workspace at `/workspace`;
- uses a small `noexec,nosuid` `/tmp` tmpfs;
- defaults to no network and applies CPU, memory, PID, and wall-time limits;
- rejects a small set of clearly dangerous container-management and host-control commands.

Customize execution limits:

```bash
alg sandbox exec SANDBOX_ID \
  --timeout 120 --network none --cpus 1 --memory 768m --pids 96 \
  -- python -m pytest -q
```

Network `bridge` is an explicit opt-in and should be used only when dependency installation is required.

## Apply safety

Before applying each path, Sandbox compares the current source hash with the original snapshot. If the host file changed after sandbox creation, apply stops instead of overwriting it. Paths must remain inside the source root, and symlinks are never applied.

Review the diff again after every container command. Binary changes are reported with hashes but do not have a text patch.

## Known limits

- Docker daemon security remains outside Agent Loop Guard.
- The command denylist is not a complete shell policy.
- Resource flags depend on Docker and the host kernel.
- A container image and dependencies may execute arbitrary initialization code.
- Secrets copied into the source tree can be visible inside the sandbox. Keep them outside the project or exclude them before creation.
- The current implementation has no long-running interactive container session; each `exec` starts a fresh container over the same copied workspace.

See the [threat model](../security.md) before processing untrusted repositories.
