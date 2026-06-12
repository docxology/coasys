# State and Reporting

Runtime state is generated under `workspace/` and ignored by git.

## Workspace Layout

```text
workspace/
  repos/
    <repo-name>/
  state/
    coasys.sqlite3
    REPORT.md
    release-smoke-server.log
    logs/
      run-<id>.log
```

| Path | Purpose |
| --- | --- |
| `workspace/repos/<repo-name>` | Managed clone for one Coasys repository. |
| `workspace/state/coasys.sqlite3` | Repository inventory and run history. |
| `workspace/state/REPORT.md` | Generated Markdown handoff report. |
| `workspace/state/logs/run-<id>.log` | Captured output tail for one run. |
| `workspace/state/release-smoke-server.log` | Temporary dashboard smoke-test log. |

## SQLite Tables

### `repos`

The `repos` table stores one row per repository. It includes:

- GitHub metadata: name, full name, URLs, default branch, visibility, language,
  stars, forks, open issues, updated/pushed timestamps, archived flag.
- Local state: local path, clone existence, current branch, local HEAD, remote
  HEAD, dirty flag, ahead/behind counts.
- Detection: stack list and command groups as JSON.
- Validation: CI status/conclusion, validation status, error text, sync and
  validation timestamps.
- Raw GitHub metadata JSON for local state only. Raw payload is stripped from
  API responses.

### `runs`

The `runs` table records command attempts:

- `kind`: `validation`, `profile`, `dry-run`, or `deployment`.
- `profile`: canonical profile such as `validate`, `build`, `start`, `deploy`.
- `status`: result state such as `passed`, `dry_run_passed`, or `failed`.
- `exit_code`
- timestamps
- command argv JSON
- output tail
- log path

## Derived Statuses

The API and report derive several statuses at read time:

| Status family | Values |
| --- | --- |
| Clone | `cloned`, `missing` |
| Config | `configured`, `detected`, `unconfigured`, `pending` |
| Validation | `passed`, `warn`, `blocked`, `failed`, `missing` |
| Start | `blocked`, `detected`, `configured`, `dry_run_passed`, `start_passed` |
| Dry run | `none`, `configured`, `dry_run_passed`, `dry_run_failed` |
| Deploy | `deploy_blocked`, `detected`, `configured`, `deploy_ready`, `deploy_executed` |

## Validation Status Rules

Validation status is set in this order:

1. Missing clone -> `missing`.
2. Failed selected command -> `failed`.
3. Missing required env or blocked command -> `blocked`.
4. Dirty checkout, ahead/behind remote, or non-success CI conclusion -> `warn`.
5. Otherwise -> `passed`.

CI conclusions treated as successful are `success`, `neutral`, and `skipped`.
Unavailable CI metadata is recorded as helpful context, not a hard failure.

## Report Sections

Generate the report with:

```bash
uv run coasys report --output workspace/state/REPORT.md
```

The report includes:

- summary counts;
- tier counts;
- validation status counts;
- clone/config/start/dry-run/deploy status counts;
- playbook coverage;
- validation alerts;
- deployment gates;
- unconfigured repositories;
- core and stale repository snapshots;
- full repository operating matrix.

`/api/report` returns the same Markdown.

## Logs

Each command batch writes a tail log to:

```text
workspace/state/logs/run-<id>.log
```

The SQLite row stores the same tail in `runs.output_tail` plus the log path.
Logs are intentionally local generated state and are not tracked.

