# Coasys Ops Documentation

This directory is the operator and maintainer documentation for the local-first
Coasys repository operations dashboard.

Start here by goal:

| Goal | Document |
| --- | --- |
| Understand the system shape | [Architecture](ARCHITECTURE.md) |
| Run fleet commands safely | [CLI Reference](CLI.md) |
| Call the local dashboard API | [API Reference](API.md) |
| Configure repositories and playbooks | [Configuration](CONFIGURATION.md) |
| Promote detected commands into safe operations | [Playbooks](PLAYBOOKS.md) |
| Interpret SQLite state, logs, and reports | [State and Reporting](STATE_AND_REPORTING.md) |
| Navigate and smoke-test the web UI | [Dashboard](DASHBOARD.md) |
| Operate the current local fleet | [Operations Runbook](OPERATIONS.md) |
| Prepare a handoff release | [Release Checklist](RELEASE_CHECKLIST.md) |
| Diagnose common failures | [Troubleshooting](TROUBLESHOOTING.md) |

The project is intentionally local-first. Generated clones, logs, SQLite state,
and reports live under `workspace/`, which is ignored by git. Secrets are never
stored in tracked files.

## Current Fleet Contract

The current handoff state is a public `github.com/coasys` fleet sync:

- 98 repositories discovered and cloned locally.
- 11 repositories have explicit configured playbooks.
- 84 repositories have detected-only commands.
- 3 repositories are unconfigured because no runnable stack was detected.
- Deployment remains blocked by default unless a repo has an explicit deploy
  playbook, required environment, and a passing dry run.

Regenerate the live numbers with:

```bash
uv run coasys status
uv run coasys report --output workspace/state/REPORT.md
```

