# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

`coasys-ops` — a **local-first control plane** for the public `github.com/coasys`
repository fleet. It clones/updates repos, records freshness + CI metadata,
detects build/start/deploy commands, and serves a local dashboard. On top of
that sits **Weave**: a configuration/design/deployment language that is a
backward-compatible superset of `coasys.yml`.

Python 3.13, FastAPI + Typer + Pydantic, managed with `uv`. No frontend build —
the dashboard is plain static HTML/CSS/JS in `src/coasys_ops/static/`.

## Commands

```bash
uv sync --extra dev                 # install (editable) with dev deps
uv run ruff check .                 # lint  (line-length 100; E,F,I,UP,B)
uv run pytest -q                    # tests
uv run coasys serve --port 5050     # dashboard at http://127.0.0.1:5050
scripts/verify_release.sh           # full release gate (lint+tests+smoke)
```

Running `pytest` without the editable install fails with
`ModuleNotFoundError: coasys_ops` — use `uv run`, or `PYTHONPATH=src pytest`.

## Layout

- `src/coasys_ops/cli.py` — Typer CLI (`sync validate operate run status report serve weave`)
- `src/coasys_ops/api.py` — FastAPI app (`create_app(root)`); serves API + static dashboard
- `src/coasys_ops/ops.py`, `store.py`, `gitops.py` — fleet lifecycle, SQLite inventory, git
- `src/coasys_ops/weave/` — the Weave language:
  - `model.py` (Pydantic doc), `loader.py` (parse + legacy `coasys.yml` bridge),
    `validate.py`, `writer.py` (atomic canonical save + `current_file_hash`),
    `graph.py`, `export.py` (plans/schema/yml), `deploy.py`, `seed.py`,
    `scaffold.py` (create-ad4m-app register), `cli.py` (weave subcommands)
- `src/coasys_ops/static/` — dashboard (`index.html`, `weave.js`, `styles.css`)
- `coasys.yml` — the live fleet config (Weave reads it via the legacy bridge)
- `examples/coasys.weave.yml` — native Weave document example
- `tests/` — pytest; `conftest.py` has `make_repo_metadata`; `_seed_weave` copies the example

## Conventions

- **Saves are validate-gated**: never persist a Weave document with semantic
  errors. Writes are atomic (temp file + `os.replace`) and refuse paths outside
  the project root.
- **Optimistic concurrency**: dashboard saves send `X-Weave-Base-Hash`; a stale
  hash returns `{conflict: true}` instead of clobbering an external edit.
- **Deploys are gated**: detected deploy scripts are visible but blocked until
  promoted into config with required env + a passing dry run. Real deploys are
  out of scope for the release gate.
- **Secrets stay out of the repo** — store only required env var *names*.
- Keep changes lint-clean (ruff) and green (pytest) before committing.

## Verifying dashboard changes

Start `coasys serve`, then drive real Chrome via `chrome-devtools-axi`
(`open <url>`, `snapshot`, `click @uid`, `screenshot <abs-path>`). uids reset on
each `open`/navigation — re-`snapshot` to get fresh ones. Screenshots must use
**absolute** paths. Check `console --type error` after interacting.

See `TODO.md` for current scope and `docs/` for per-task documentation.
