# ReproLab

ReproLab turns a bug report into a portable local reproduction package. It
stores the report, source reference, environment manifest, commands, bounded
logs, Sandbox ID, and file diff.

```bash
alg repro create bug-report.md --source . --test-command "python -m pytest -q"
alg repro status REPRO_ID
alg repro export REPRO_ID --output reproduction.zip
```

Creation, status, diff, and export work without Docker. Running setup or test
commands requires Docker because ReproLab delegates execution to the copied
workspace Sandbox:

```bash
alg repro run REPRO_ID --timeout 300
alg repro diff REPRO_ID
```

The original source directory is never mounted into the container and is never
modified by ReproLab.
