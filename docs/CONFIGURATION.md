# Configuration

`coasys.yml` is the operator-controlled policy file. It configures workspace
paths, clone behavior, per-repo tier overrides, runnable playbooks, timeouts,
and required environment variable names.

Secrets do not belong in `coasys.yml`. Store only env var names such as
`GITHUB_TOKEN` or `NPM_TOKEN`.

## Top-Level Schema

```yaml
org: coasys
workspace:
  repos_dir: workspace/repos
  state_dir: workspace/state
defaults:
  timeout_seconds: 600
  clone_depth: 1
  partial_clone: true
  execute_detected_validation: false
repos: {}
```

| Key | Meaning |
| --- | --- |
| `org` | GitHub organization to sync by default. |
| `workspace.repos_dir` | Managed clone directory. |
| `workspace.state_dir` | SQLite database, logs, and generated report directory. |
| `defaults.timeout_seconds` | Default command timeout. |
| `defaults.clone_depth` | Shallow clone/fetch depth. Set null for full history. |
| `defaults.partial_clone` | Use `git clone --filter=blob:none` for new clones. |
| `defaults.execute_detected_validation` | Run detected validation commands globally. Keep false for release-readiness. |
| `repos` | Per-repo overrides keyed by repository name. |

Relative workspace paths are resolved from the project root.

## Repo Override Schema

```yaml
repos:
  ad4m:
    clone_url: https://github.com/coasys/ad4m.git
    tier: core
    timeout_seconds: 900
    env_required:
      - GITHUB_TOKEN
    do_not_run_automatically: false
    execute_detected_validation: false
    validation_commands:
      - pnpm run lint
    profiles:
      inspect:
        - git status --short
    playbooks:
      build:
        commands:
          - pnpm run build
        dry_run_commands:
          - test -f package.json
```

| Key | Meaning |
| --- | --- |
| `clone_url` | Override the GitHub clone URL. Useful for forks or local fixtures. |
| `tier` | Override classification. |
| `timeout_seconds` | Repo-wide command timeout. |
| `env_required` | Env vars required for repo-level automatic commands. |
| `do_not_run_automatically` | Prevent automatic validation command execution. |
| `execute_detected_validation` | Allow detected validation command execution for this repo. |
| `validation_commands` | Extra automatic validation commands sourced from config. |
| `profiles` | Legacy/simple profile command lists. |
| `playbooks` | Structured profile definitions with dry-run and env gates. |

## Playbook Schema

```yaml
playbooks:
  deploy:
    commands:
      - pnpm run deploy
    dry_run_commands:
      - pnpm run deploy -- --dry-run
    env_required:
      - GITHUB_TOKEN
      - NPM_TOKEN
    working_dir: packages/app
    timeout_seconds: 1200
    automatic: false
    allow_detected: false
```

| Key | Meaning |
| --- | --- |
| `commands` | Commands used for real execution. |
| `dry_run_commands` | Readiness commands used with `--dry-run`. |
| `env_required` | Env vars required for this playbook. |
| `working_dir` | Subdirectory inside the repo clone. Cannot escape the repo. |
| `timeout_seconds` | Playbook-specific timeout. |
| `automatic` | Marks configured validation commands as automatic. |
| `allow_detected` | Parsed for future policy use; detected commands are still not promoted automatically. |

Command strings are split with shell-like parsing. Shell features such as pipes
and redirection are not interpreted unless the command explicitly invokes a
shell, for example `bash -lc 'pnpm test | tee test.log'`.

## Tier Overrides

Classification precedence:

1. `repos.<name>.tier` from `coasys.yml`.
2. Built-in core repository list.
3. Built-in dependency-fork list.
4. Repository name or description containing language markers.
5. Archived repositories as `stale`.
6. Updated more than 365 days ago as `stale`.
7. Updated within 120 days as `active`.
8. Fallback `unknown`.

## Environment Requirements

Missing env vars block execution where they matter:

- repo-level `env_required` blocks configured automatic validation commands;
- profile-level `env_required` blocks profile execution;
- deploy playbooks with missing env report `deploy_blocked`.

Only names are recorded in state and report output.

## Working Directory Guard

`working_dir` is resolved relative to the local clone. If the resolved path is
outside the clone, the run is rejected. This prevents config from accidentally
running commands elsewhere on the machine.

