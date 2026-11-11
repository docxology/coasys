# Coasys Ops — TODO / Scope

Top-level scope tracker for the operations dashboard. Done items are kept as a
record of what shipped; open items are the live backlog.

## Shipped

### Operations dashboard (baseline)
- [x] Clone/update fleet repos, record freshness + CI metadata (`sync`)
- [x] Detect validate/build/start/deploy commands per repo (`validate`, `operate`)
- [x] Local dashboard: Overview / Repos / Runs / Topology tabs (`serve`)
- [x] SQLite inventory + run history under `workspace/state/`
- [x] `report` operating ledger; `scripts/verify_release.sh` release gate
- [x] GitHub Actions lint + test gate on push/PR

### Weave language workstream
- [x] Weave model + loader (backward-compatible superset of `coasys.yml`)
- [x] Validator (structure + semantics), canonical writer (atomic, deterministic)
- [x] Dependency/deploy graph + Mermaid export; priority targets
- [x] Setup/deploy plans (dependency-ordered waves); deploy-readiness gates
- [x] WE seed compilation (`weave seed`); `export-yml`, `fmt`
- [x] CLI surface: `lint targets graph plan deploy-check schema seed starters create-app`
- [x] Dashboard Weave tab: Graph / Schema (form editor, auto-save) / Deploy / Onboard
- [x] Onboard tab: AD4M app starters + scaffold-and-register (`create-ad4m-app`)
- [x] Loader pass-through fix: `starters` now survives the legacy `coasys.yml` path
- [x] Optimistic concurrency on save (`X-Weave-Base-Hash`) — refuse clobbering hand edits
- [x] Tests: 70 passing (Weave engine + API round-trips + concurrency guard)
- [x] Docs: README screenshots, WEAVE_LANGUAGE.md, WEAVE_GRAMMAR.md

## Open

### Next phase — wire Weave into the operate path
The Weave document already produces operation plans (`/api/weave/plan`,
`weave plan`), but `coasys operate` still reads `coasys.yml` overrides directly.
Unify so `operate` consumes the Weave document as the source of truth.
- [ ] Decide: Weave doc drives `operate` directly, or `export-yml` stays the bridge?
- [ ] Propose design before building (touches core fleet lifecycle) — not a blind change.

### Smaller follow-ups
- [ ] Topology "Waves" layout renders nodes in a single column — spread by
      dependency depth and draw edges (cosmetic; graph data is correct).
- [ ] `verify_release.sh` `behind_count == 0` gate fails on dev machines with
      repos behind remote — environment drift, not a code issue. Consider a
      `--local` mode that skips remote-freshness gates.
- [ ] Surface the save-conflict state in the Schema view with a one-click reload.

<!-- ponytail: scope record, not a project-management tool. Edit in place. -->

## Workflowz review — 2026-11-10

- [ ] WR-001 — P1 — Render fleet metadata as text in the legacy dashboard views so a repository name, description, error, branch, or command containing HTML cannot become markup. `statusPill()` interpolates the status directly into `innerHTML` (`src/coasys_ops/static/app.js:29-32`), alerts include `repo.name` and `repo.last_error || repo.description` (`src/coasys_ops/static/app.js:82-89`), and the repository table interpolates names, deploy reasons, stacks, branches, and timestamps (`src/coasys_ops/static/app.js:134-148`). Escape every interpolated value for its HTML/text/attribute context (or construct DOM nodes with `textContent`), while retaining the intentional static markup; apply the same treatment to run rows and the detail view (`src/coasys_ops/static/app.js:174-187`, `src/coasys_ops/static/app.js:226-236`). This implements the explicit untrusted-metadata rule in `AGENTS.md:53-54`, without changing the API or adding a frontend build. Acceptance: from the repository root, run `uv run pytest -q` and require all tests to pass; additionally serve a local test state containing a repository whose description is `<img src=x onerror="window.__fleetXss=1">` and open Overview/Repos, requiring the literal text to be visible and `window.__fleetXss` to remain unset. Dependencies: none; use only the existing static HTML/CSS/JS architecture.
- [ ] WR-002 — P2 — Fail fast when Weave document discovery finds no document, instead of surfacing an implementation traceback. Both the CLI loader (`src/coasys_ops/weave/cli.py:31-32`) and dashboard API (`src/coasys_ops/api.py:125-133`) call `load_document` on the current/root directory; commands such as `lint` immediately validate the returned value (`src/coasys_ops/weave/cli.py:42-44`). Make the missing-document contract explicit in `load_document` and translate it to a concise Typer error and an appropriate HTTP response rather than an attribute/parse traceback; preserve the documented preference for `coasys.weave.yml`, then `coasys.yml` (`src/coasys_ops/weave/cli.py:1-6`). Acceptance: from a temporary empty working directory with the package installed, run `uv run coasys weave lint --path .` and require exit code 1 with a concise message naming the expected `coasys.weave.yml`/`coasys.yml` files and no traceback; then copy `coasys.yml` into that directory and require the same command to validate it. Also run `uv run pytest -q` with all tests passing. Dependencies: first inspect the unexcerpted `src/coasys_ops/weave/loader.py` and existing CLI/API tests to preserve the current loader contract; no dependency or runtime change is required.

Runtime/dependency review: retain the declared Python floor `>=3.13` and Ruff `py313` target (`pyproject.toml:6`, `pyproject.toml:35`) for this bounded review. The project documentation explicitly declares Python 3.13 (`AGENTS.md:16`); no supplied deployment or lock excerpt establishes Python 3.15.2 compatibility, so no evidence-based version bump is proposed. No blind dependency upgrades were identified from the visible lower-bound declarations (`pyproject.toml:7-21`).
