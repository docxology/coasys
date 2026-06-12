# Coasys Repository Operations Dashboard

Local-first control plane for the public `github.com/coasys` repository fleet.

The project clones and updates Coasys repositories, records freshness and CI
metadata, detects local validation/build/start/deploy commands, and serves a
local dashboard for navigating the ecosystem.

## Documentation

The documentation is split by operator task and maintainer concern:

- [Documentation index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [CLI reference](docs/CLI.md)
- [API reference](docs/API.md)
- [Configuration](docs/CONFIGURATION.md)
- [Playbooks](docs/PLAYBOOKS.md)
- [State and reporting](docs/STATE_AND_REPORTING.md)
- [Dashboard](docs/DASHBOARD.md)
- [Operations runbook](docs/OPERATIONS.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Quick Start

```bash
uv sync --extra dev
uv run coasys sync --org coasys
uv run coasys validate --all
uv run coasys operate --org coasys
uv run coasys status
uv run coasys report --output workspace/state/REPORT.md
uv run coasys serve --host 127.0.0.1 --port 5050
```

Open `http://127.0.0.1:5050` after `serve` starts.

For release-readiness handoff, run the dry-run gate:

```bash
scripts/verify_release.sh
```

The release gate runs lint, tests, whitespace checks, fleet status inspection,
report generation, API smoke checks, and a dashboard console smoke check when
`chrome-devtools-axi` is installed. It starts only a temporary dashboard smoke
server and stops it before exiting.

Generated clones and state live under `workspace/`, which is intentionally
ignored by git:

- `workspace/repos/<repo-name>` for managed clones
- `workspace/state/coasys.sqlite3` for local inventory and run history
- `workspace/state/logs/` for command output tails

## CLI

```bash
uv run coasys sync --org coasys
uv run coasys validate --all
uv run coasys validate --tier core
uv run coasys validate --repo ad4m --execute-detected
uv run coasys operate --org coasys --tier core
uv run coasys operate --org coasys --tier core --execute-configured
uv run coasys operate --org coasys --deploy
uv run coasys run ad4m build --dry-run
uv run coasys run ad4m start --dry-run
uv run coasys run paperclip deploy --dry-run
uv run coasys status
uv run coasys report
uv run coasys report --output workspace/state/REPORT.md
uv run coasys serve --host 127.0.0.1 --port 5050
```

`validate` is conservative by default. It always checks Git state, metadata,
detected stacks, detected commands, and latest GitHub Actions metadata when
available. It only runs detected package/build/test commands when
`--execute-detected` is passed or a repo config enables automatic validation.

`operate` is the fleet lifecycle command. By default it syncs GitHub metadata,
performs shallow partial clone/fetch operations, validates repositories, and
updates lifecycle summaries. `--execute-configured` runs configured build/start
dry-run playbooks for the selected tier. Deployments are intentionally gated:

- `--deploy` runs configured deploy dry-run playbooks and records readiness.
- Detected deploy scripts are visible, but blocked until promoted into
  `coasys.yml`.
- Real deploy execution is outside the release-readiness handoff. It requires an
  explicit deploy playbook, required environment, a passing dry run, and a
  separate operator decision.

Startup and deploy commands are config-gated through `coasys.yml`; secrets must
stay outside the repository. Store only the required environment variable names.

`report` emits an operating ledger with clone/configuration/validation/deploy
readiness counts, alert lists, deployment gates, unconfigured repositories, and
a row for every repository in the fleet.

Command detection currently recognizes:

- `package.json` scripts for npm, pnpm, yarn, and bun projects
- `Cargo.toml` for Rust metadata/test/build checks
- `deno.json` / `deno.jsonc` tasks
- `flake.nix` / `default.nix`
- `Makefile`, `justfile`, and `Taskfile.yml` / `Taskfile.yaml`
- Holochain marker directories/files for stack classification

## Configuration

`coasys.yml` contains defaults and optional per-repo overrides:

```yaml
org: coasys
workspace:
  repos_dir: workspace/repos
  state_dir: workspace/state
repos:
  ad4m:
    tier: core
    timeout_seconds: 900
    playbooks:
      validate:
        commands:
          - pnpm run lint
        dry_run_commands:
          - test -f package.json
        automatic: false
      build:
        commands:
          - pnpm run build-libs
        dry_run_commands:
          - test -f package.json
      start:
        commands:
          - pnpm run serve
        dry_run_commands:
          - test -f package.json
```

Playbook keys are profile names such as `validate`, `build`, `start`, and
`deploy`. Each playbook can set `commands`, `dry_run_commands`, `env_required`,
`working_dir`, `timeout_seconds`, and `automatic`.

Secrets should not be stored in this repository. Use normal GitHub auth,
`GITHUB_TOKEN`, and ignored local environment files.

## API

- `GET /api/repos`
- `GET /api/repos/{name}`
- `GET /api/summary`
- `GET /api/report`
- `POST /api/repos/{name}/sync`
- `POST /api/repos/{name}/validate`
- `POST /api/repos/{name}/run/{profile}?dry_run=true`
- `POST /api/repos/{name}/run/{profile}?execute=true` is intentionally excluded
  from release verification and should not be used without deploy approval.
- `POST /api/operate?execute_configured=true`
- `GET /api/runs`
- `GET /api/runs/{id}`

## Verification

```bash
scripts/verify_release.sh
uv run --extra dev ruff check .
uv run --extra dev pytest -q
git diff --check
uv run coasys status
uv run coasys report --output workspace/state/REPORT.md
```

Operational handoff notes live in `docs/OPERATIONS.md`. GitHub Actions also
runs the lint and test gate on pushes and pull requests.
