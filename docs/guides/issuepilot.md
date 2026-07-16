# IssuePilot

IssuePilot turns a GitHub issue or local JSON fixture into a technical plan,
checklist, branch name, and acceptance criteria.

```bash
alg issue import issue.json
alg issue plan ISSUE_ID
alg issue export ISSUE_ID --output issue-plan.zip
```

These commands do not modify GitHub or Git. To create or switch the proposed
branch, cross the explicit apply boundary:

```bash
alg issue apply ISSUE_ID --repository .
```

GitHub URLs use the public issue API unless `--token` is supplied. Local fixture
files make the workflow reproducible and usable offline. Replay records contain
the issue ID, repository, number, title hash, and operation result rather than
the full issue body by default.

