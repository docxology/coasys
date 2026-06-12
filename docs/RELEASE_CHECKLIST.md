# Release Checklist

This checklist prepares the branch for handoff without committing, pushing,
publishing, deploying, or leaving services running.

## One-Command Gate

```bash
scripts/verify_release.sh
```

The script runs:

1. `uv run --extra dev ruff check .`
2. `uv run --extra dev pytest -q`
3. `git diff --check`
4. `uv run coasys status`
5. `uv run coasys report --output workspace/state/REPORT.md`
6. temporary dashboard smoke server
7. `/api/summary` and `/api/report` smoke checks
8. Chrome console smoke check when `chrome-devtools-axi` is installed

The temporary server is stopped before the script exits.

## Manual Gate

Use these commands when you need to inspect each step separately:

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest -q
git diff --check
uv run coasys status
uv run coasys report --output workspace/state/REPORT.md
uv run coasys serve --host 127.0.0.1 --port 5050
```

Then in another shell:

```bash
curl -fsS http://127.0.0.1:5050/api/summary
curl -fsS http://127.0.0.1:5050/api/report
/opt/homebrew/bin/chrome-devtools-axi open http://127.0.0.1:5050
/opt/homebrew/bin/chrome-devtools-axi console --type error
```

Stop the dashboard with Ctrl-C.

## Expected Current State

`uv run coasys status` should report:

```text
repositories: 98
cloned: 98
dirty: 0
behind: 0
```

The report should show:

- 11 configured repositories;
- 84 detected-only repositories;
- 3 unconfigured repositories;
- 94 passed validations;
- 4 validation warnings;
- deploy readiness blocked except detected/configured readiness gates.

## Handoff Rules

- Do not commit, push, or open a PR unless the operator asks.
- Do not run real deploys.
- Do not publish packages.
- Do not leave a persistent dashboard or fleet process running.
- Keep `workspace/` ignored.
- Keep secrets outside tracked files.

## Final Worktree Review

```bash
git status --short --branch
git check-ignore -v workspace/state/REPORT.md workspace/repos/ad4m
```

The generated workspace paths should be ignored by `.gitignore`.

