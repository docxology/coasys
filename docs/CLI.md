# CLI Reference

Run CLI commands through `uv` from the repository root:

```bash
uv run coasys --help
```

## Setup

```bash
uv sync --extra dev
uv run coasys sync --org coasys
uv run coasys status
```

`GITHUB_TOKEN` is optional for public metadata but recommended to avoid rate
limits and to read workflow metadata consistently.

## Commands

| Command | Purpose | Safe default |
| --- | --- | --- |
| `sync` | Fetch GitHub inventory and clone/fetch repos. | Yes |
| `validate` | Run progressive repo validation. | Yes |
| `operate` | Combined sync, validation, configured dry-run, and deploy readiness flow. | Yes |
| `run` | Run one configured repo profile. | Requires flags for gated profiles |
| `status` | Print compact fleet counts. | Yes |
| `report` | Print or write Markdown operating report. | Yes |
| `serve` | Serve dashboard locally. | Local dashboard only |

## `sync`

```bash
uv run coasys sync --org coasys
uv run coasys sync --org coasys --no-clone
uv run coasys sync --org coasys --limit 10
```

`sync` writes repository rows to SQLite. By default it clones missing repos and
fetches existing checkouts. The clone strategy uses shallow, partial clones when
enabled in `coasys.yml`.

## `validate`

```bash
uv run coasys validate --all
uv run coasys validate --tier core
uv run coasys validate --repo ad4m
uv run coasys validate --repo ad4m --execute-detected
```

If no selector is supplied, validation defaults to the `core` tier. Validation
always inspects Git state, local checkout availability, detected stacks,
detected commands, and latest CI metadata when available.

Detected package/build/test commands run only when:

- the command is marked automatic by detection, such as `cargo metadata`, or
- `--execute-detected` is passed, or
- `defaults.execute_detected_validation` is enabled, or
- a repo override enables `execute_detected_validation`.

## `operate`

```bash
uv run coasys operate --org coasys
uv run coasys operate --org coasys --tier core
uv run coasys operate --org coasys --tier core --execute-configured
uv run coasys operate --org coasys --deploy
```

`operate` is the lifecycle command. It can sync, validate, run configured
build/start dry runs, and evaluate deploy readiness.

Important flags:

| Flag | Effect |
| --- | --- |
| `--no-clone` | Use existing SQLite inventory without clone/fetch. |
| `--no-validate` | Skip validation. |
| `--tier <tier>` | Limit operation to one tier. |
| `--limit <n>` | Limit GitHub inventory processing. |
| `--execute-configured` | Run configured build/start dry-run playbooks. |
| `--deploy` | Run deploy dry-run readiness checks where configured. |
| `--execute-deploy` | Execute explicit deploy playbooks after a passing dry run. Not part of release-readiness verification. |

## `run`

```bash
uv run coasys run ad4m build --dry-run
uv run coasys run ad4m start --dry-run
uv run coasys run paperclip deploy --dry-run
```

Gated profiles are `start`, `dev`, `serve`, `deploy`, and `release`. They
require explicit configuration and either `--dry-run` or `--execute`.

Deploy execution is intentionally separate:

```bash
uv run coasys run paperclip deploy --execute
```

Use this only after a deploy dry run passes and after the operator has supplied
the required environment and approved real deployment.

## `status`

```bash
uv run coasys status
```

The expected release-readiness state is:

- `repositories: 98`
- `cloned: 98`
- `dirty: 0`
- `behind: 0`

## `report`

```bash
uv run coasys report
uv run coasys report --output workspace/state/REPORT.md
```

The report is the handoff ledger for playbook coverage, validation alerts,
deployment gates, unconfigured repos, tier groups, and the full operating
matrix.

## `serve`

```bash
uv run coasys serve --host 127.0.0.1 --port 5050
```

Open `http://127.0.0.1:5050` for the local dashboard. Stop it with Ctrl-C.

