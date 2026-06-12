# Troubleshooting

## GitHub API Rate Limits

Symptoms:

- `sync` fails while listing organization repositories.
- CI metadata appears as unavailable.

Fix:

```bash
export GITHUB_TOKEN=...
uv run coasys sync --org coasys
```

Use a token with read access to public repo metadata. Do not write it into
tracked files.

## Port 5050 Is Already In Use

Symptoms:

- `uv run coasys serve --host 127.0.0.1 --port 5050` fails.
- `scripts/verify_release.sh` reports the port is already in use.

Inspect:

```bash
lsof -nP -iTCP:5050 -sTCP:LISTEN
```

Use another port:

```bash
COASYS_PORT=5051 scripts/verify_release.sh
uv run coasys serve --host 127.0.0.1 --port 5051
```

If a detached dashboard was started with `screen`:

```bash
screen -S coasys-dashboard -X quit
```

## Repository Exists But Is Not a Git Checkout

Symptoms:

- A repo row has `last_error` mentioning that the path exists but is not a git
  checkout.

Fix:

1. Inspect `workspace/repos/<repo-name>`.
2. Move or remove the non-git directory if it is disposable.
3. Run:

   ```bash
   uv run coasys sync --org coasys
   ```

Do not delete anything under `workspace/repos/` without checking whether it
contains local work.

## Dirty or Behind Repositories

Symptoms:

- `uv run coasys status` reports dirty or behind counts.
- A repo validation status is `warn`.

Inspect:

```bash
git -C workspace/repos/<repo-name> status --short
git -C workspace/repos/<repo-name> rev-list --left-right --count HEAD...origin/<default-branch>
```

Fix local dirty state manually. Then fetch or sync:

```bash
uv run coasys sync --org coasys
uv run coasys validate --repo <repo-name>
```

## Missing Environment Blocks a Playbook

Symptoms:

- Report shows missing env vars.
- Deploy status is `deploy_blocked`.
- Profile execution returns a missing environment error.

Fix:

```bash
export GITHUB_TOKEN=...
export NPM_TOKEN=...
uv run coasys run <repo> deploy --dry-run
```

Only execute deploys after dry-run readiness and explicit approval.

## Detected Deploy Script Is Blocked

Symptoms:

- Report shows deploy status `detected`.
- `run <repo> deploy --dry-run` returns an explicit playbook error.

This is expected. Copy the command into `coasys.yml` only after reviewing it:

```yaml
repos:
  demo:
    playbooks:
      deploy:
        commands:
          - pnpm run deploy
        dry_run_commands:
          - pnpm run deploy -- --dry-run
```

## Validation Warning With No Local Command Failure

Possible causes:

- dirty checkout;
- local branch ahead of or behind remote;
- latest CI conclusion is not `success`, `neutral`, or `skipped`;
- CI metadata unavailable due to permissions or API errors.

Inspect repo detail in the dashboard or:

```bash
uv run coasys report | rg '<repo-name>|Validation Alerts|Deployment Gates'
```

## Command Times Out

Symptoms:

- run exit code `124`;
- status `failed` or `dry_run_failed`;
- log tail ends before normal completion.

Fix by adding a repo or playbook timeout:

```yaml
repos:
  demo:
    timeout_seconds: 1200
    playbooks:
      build:
        timeout_seconds: 1800
```

## Reset Generated State

Use this only when local generated state is disposable:

```bash
rm -f workspace/state/coasys.sqlite3
rm -rf workspace/state/logs
uv run coasys sync --org coasys
uv run coasys validate --all
```

This does not remove clones. Removing clones is more disruptive and should be
done repo by repo only after inspecting local changes.

