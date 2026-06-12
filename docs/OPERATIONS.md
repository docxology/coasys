# Coasys Operations Runbook

This repository is a local-first control plane for the public Coasys GitHub
fleet. Generated clones, logs, reports, and SQLite state live under
`workspace/` and stay ignored by git.

Related references:

- [Architecture](ARCHITECTURE.md)
- [CLI Reference](CLI.md)
- [Playbooks](PLAYBOOKS.md)
- [State and Reporting](STATE_AND_REPORTING.md)
- [Release Checklist](RELEASE_CHECKLIST.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## Release Verification

Run the full local release gate:

```bash
scripts/verify_release.sh
```

The gate runs lint, tests, whitespace checks, fleet status inspection, report
generation, API smoke checks, and a browser console check when
`chrome-devtools-axi` is installed.

The canonical report is regenerated at `workspace/state/REPORT.md`.

## Daily Operation

```bash
uv run coasys sync --org coasys
uv run coasys validate --all
uv run coasys operate --org coasys --tier core --execute-configured
uv run coasys report --output workspace/state/REPORT.md
uv run coasys serve --host 127.0.0.1 --port 5050
```

Use `--execute-configured` for configured dry-run playbooks. It does not deploy,
publish, or start persistent fleet services.

## Dry-Run Safety

This release is dry-run/readiness-only by default.

- Deployment remains blocked unless a repo has an explicit `deploy` playbook.
- Deploy execution requires a prior passing dry run and explicit operator flags.
- Required secret names may be stored in `coasys.yml`; secret values must stay in
  the operator environment or ignored local files.
- Detected deploy scripts are visible in the dashboard and report, but remain
  blocked until promoted into `coasys.yml`.

## Dashboard

Start the dashboard locally:

```bash
uv run coasys serve --host 127.0.0.1 --port 5050
```

Open `http://127.0.0.1:5050`.

If a detached dashboard was started with `screen`, stop it with:

```bash
screen -S coasys-dashboard -X quit
```

## Handoff Checklist

Before handing off the branch:

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest -q
git diff --check
uv run coasys status
uv run coasys report --output workspace/state/REPORT.md
```

Expected current fleet state:

- 98 repositories
- 98 cloned locally
- 0 dirty checkouts
- 0 behind remote
- 94 passed validations and 4 warnings
