# Playbooks

Playbooks convert detected repository commands into explicit operator policy.
They are the boundary between "the dashboard saw a script" and "the operator
allows this command to run."

## Profiles

Common profile names:

| Profile | Command group | Gate |
| --- | --- | --- |
| `validate`, `validation`, `test` | validation | Configured validation may run automatically. |
| `build` | build | Dry-run friendly, not treated as service startup. |
| `start`, `dev`, `serve` | start | Requires explicit playbook and `--dry-run` or `--execute`. |
| `deploy`, `release` | deploy | Requires explicit playbook, passing dry run, env, and operator approval. |

## State Model

| State | Meaning |
| --- | --- |
| `detected` | Commands were found in repo files, but no explicit playbook exists. |
| `configured` | A playbook or profile exists in `coasys.yml`. |
| `dry_run_passed` | The latest dry-run profile completed successfully. |
| `dry_run_failed` | The latest dry-run profile failed or timed out. |
| `start_passed` | A configured start profile executed successfully. |
| `deploy_ready` | Deploy playbook exists, env is available, and latest deploy dry run passed. |
| `deploy_blocked` | Deploy is unavailable or blocked by missing playbook/env/dry run. |
| `deploy_executed` | Deploy profile was explicitly executed successfully. |

Release-readiness work should stop at `dry_run_passed` and `deploy_ready`.
Actual deploy execution is not part of normal verification.

## Promotion Workflow

1. Inspect detected commands in the dashboard, report, or `/api/repos/{name}`.
2. Decide whether the command is safe and meaningful for local operation.
3. Copy it into `coasys.yml` as a playbook.
4. Add `dry_run_commands` that check readiness without starting persistent
   services or publishing artifacts.
5. Declare `env_required` names, not secret values.
6. Run the dry run:

   ```bash
   uv run coasys run <repo> <profile> --dry-run
   ```

7. Regenerate the report:

   ```bash
   uv run coasys report --output workspace/state/REPORT.md
   ```

## Examples

### Build

```yaml
repos:
  demo:
    playbooks:
      build:
        commands:
          - pnpm run build
        dry_run_commands:
          - test -f package.json
```

### Start

```yaml
repos:
  demo:
    playbooks:
      start:
        commands:
          - pnpm run dev
        dry_run_commands:
          - test -f package.json
          - test -f pnpm-lock.yaml
        timeout_seconds: 120
```

Use start dry runs to confirm prerequisites. Do not use release-readiness dry
runs to leave services running.

### Deploy

```yaml
repos:
  demo:
    playbooks:
      deploy:
        commands:
          - pnpm run deploy
        dry_run_commands:
          - pnpm run deploy -- --dry-run
        env_required:
          - GITHUB_TOKEN
          - NPM_TOKEN
```

Deploy execution requires:

- configured deploy playbook;
- no missing deploy env vars;
- latest deploy dry run has `dry_run_passed`;
- explicit operator execution:

  ```bash
  uv run coasys run demo deploy --execute
  ```

## Tier Rollout

Use tiers to avoid treating all repositories as equal:

1. `core`: AD4M and primary application/runtime repos.
2. `active`: active support services and apps.
3. `language`: link/expression language repos.
4. `dependency-fork`: forked dependencies and upstream-adjacent code.
5. `stale`: older or archived repositories.

Recommended progression:

```bash
uv run coasys operate --org coasys --tier core --execute-configured
uv run coasys operate --org coasys --tier active --execute-configured
uv run coasys operate --org coasys --tier language
```

Dependency forks and stale repos should remain detected-only until a maintainer
chooses a real local operating contract.

## Current Configured Set

The current release config contains explicit playbooks for:

- `ad4m`
- `we`
- `perspect3ve`
- `flux`
- `ad4m-host`
- `ad4m-devtools`
- `ad4m-wind-tunnel`
- `paperclip`
- `joining-service`
- `social-dna`
- `zeroclaw`

`flux` and `paperclip` have deploy playbooks but remain deploy-blocked until
their required environment variables are present and an operator chooses to
proceed beyond dry-run readiness.

