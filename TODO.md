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
