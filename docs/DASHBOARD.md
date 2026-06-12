# Dashboard

The dashboard is a static frontend served by the FastAPI app.

```bash
uv run coasys serve --host 127.0.0.1 --port 5050
```

Open `http://127.0.0.1:5050`.

## Views

| View | Purpose |
| --- | --- |
| Overview | Fleet counts, validation warnings, deploy readiness, top alerts. |
| Repos | Filterable repository matrix with status, stack, branch, and deploy state. |
| Runs | Recent validation, dry-run, profile, and deployment attempts. |
| Topology | Tier-grouped repository overview. |

## Repository Detail

Click a repository name in the Repos view to open details. The detail panel
shows:

- validation, config, start, and deploy status;
- deploy reason and next action;
- playbook profiles;
- missing environment variable names;
- local clone path;
- GitHub link;
- branch, ahead/behind, and dirty state;
- detected and configured command groups;
- recent runs for the repo.

## Dashboard Actions

The dashboard can trigger local API actions:

| Action | API call | Safety |
| --- | --- | --- |
| Refresh | `GET /api/summary`, `GET /api/repos`, `GET /api/runs` | Read-only |
| Sync + Validate | `POST /api/operate` | Sync/fetch and validation only |
| Operate Local | `POST /api/operate?execute_configured=true` | Configured dry-run/start readiness only |
| Sync | `POST /api/repos/{name}/sync` | Clone/fetch one repo |
| Validate | `POST /api/repos/{name}/validate` | Validation checks |
| Build Dry Run | `POST /api/repos/{name}/run/build?dry_run=true` | Configured dry run |
| Start Dry Run | `POST /api/repos/{name}/run/start?dry_run=true` | Configured dry run |
| Deploy Dry Run | `POST /api/repos/{name}/run/deploy?dry_run=true` | Deploy readiness only |

The dashboard does not provide a deploy execute button in the release-readiness
handoff path.

## Browser Smoke Test

Use the release gate:

```bash
scripts/verify_release.sh
```

Or run a manual browser check:

```bash
uv run coasys serve --host 127.0.0.1 --port 5050
/opt/homebrew/bin/chrome-devtools-axi open http://127.0.0.1:5050
/opt/homebrew/bin/chrome-devtools-axi console --type error
```

Expected console result:

```text
<no console messages found>
```

Stop the server with Ctrl-C after smoke testing.

