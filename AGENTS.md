# AGENTS.md — coasys

Guidance for agents working in this repository.

## What this repository is

`coasys-ops` — a local-first control plane for the public `github.com/coasys`
repository fleet. It clones and updates those repositories, records freshness and
CI metadata, detects build/start/deploy commands across npm, Rust, Deno, Nix,
Make, and Holochain, and serves a local dashboard backed by SQLite.

On top of the operator sits **Weave**: a configuration/design/deployment language
that is a backward-compatible superset of `coasys.yml`. `coasys.yml` remains
valid Weave; do not break that compatibility.

Python 3.13, FastAPI + Typer + Pydantic, managed with `uv`. There is no frontend
build: the dashboard is plain static HTML/CSS/JS under `src/coasys_ops/static/`.

## Commands

```bash
uv sync --extra dev                 # install editable, with dev deps
uv run ruff check .                 # lint (line length 100; rules E,F,I,UP,B)
uv run pytest -q                    # tests
uv run coasys serve --port 5050     # dashboard on http://127.0.0.1:5050
scripts/verify_release.sh           # full gate: lint + tests + smoke
```

## Layout

| Path | Role |
|---|---|
| `src/coasys_ops/` | Application package; `static/` holds the dashboard assets |
| `coasys.yml` | Operator configuration, also valid as Weave |
| `examples/` | Example configurations and usage |
| `scripts/verify_release.sh` | Release gate |
| `tests/` | pytest suite |
| `docs/` | Documentation hub |

Entry point is the `coasys` console script declared in `pyproject.toml`
(`coasys_ops.cli:app`). Add subcommands there rather than adding standalone
scripts.

## Conventions

- The control plane runs locally and binds to loopback. Do not add a mode that
  exposes the dashboard on a public interface.
- Repository operations touch other people's checkouts. Anything that clones,
  updates, or rewrites a fleet repository must be visible as an operator command,
  never an implicit side effect of `serve`.
- Weave is a superset of `coasys.yml`. A new field is additive; an existing
  field keeps its meaning.
- Static dashboard assets are served as-is. Render untrusted metadata as text;
  never interpolate fleet data into HTML without escaping.
- `uv` is the only dependency manager. `uv.lock` is committed and should be
  refreshed deliberately, not regenerated as a side effect of an unrelated edit.

## Verification

Run `scripts/verify_release.sh` before claiming a change is ready — it is the
documented gate. For narrower work, `uv run ruff check .` and `uv run pytest -q`
are the two checks CI runs. Report the command and its result.

## Relationship to `CLAUDE.md`

A vendor-specific `CLAUDE.md` still exists in this repository and duplicates part
of this file. This `AGENTS.md` is the canonical entry point; `CLAUDE.md` is
slated for removal as part of the repository's tooling-neutrality pass.
