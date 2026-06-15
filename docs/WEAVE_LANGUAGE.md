# Weave — the Coasys configuration / design / deployment language

Weave is a declarative, visual-and-textual language for describing how the
`github.com/coasys` repository fleet is **configured**, **designed** (via the WE
launcher/seed system), and **deployed**. It is a strict, backward-compatible
superset of the legacy `coasys.yml` operations config: every existing file keeps
working, and a Weave document compiles *back down* to `coasys.yml` so the
operations layer is unchanged.

One model, three surfaces:

- **Textual** — `coasys.weave.yml` (YAML), authored by hand or generated.
- **Programmatic** — the `coasys weave …` CLI and `/api/weave/*` HTTP API.
- **Visual** — an **interactive network topology**, **schema-driven forms**, and
  a **deployment** view in the dashboard (`serve` → *Weave* tab).

For the formal specification — EBNF grammar, abstract domains, well-formedness
rules, and the operational semantics of the setup/deployment lifecycles — see
[WEAVE_GRAMMAR.md](WEAVE_GRAMMAR.md).

The full lifecycle is `setup ≺ validate ≺ build ≺ start` plus a gated `deploy`,
where `setup` is the bootstrapping phase (`pnpm install`, `cargo fetch`,
`uv sync`). `coasys weave plan setup` emits the dependency-ordered setup waves.

All three are derived mechanically from a single pydantic model
(`coasys_ops.weave.model`), so the picture, the forms, the CLI, and the planner
can never drift apart.

---

## 1. Why a language

The fleet is not a flat list of repos. It is a **typed dependency graph** with
three intertwined concerns that the old `coasys.yml` could only express as loose
command lists:

1. **Configuration** — which repos exist, their tier and priority, where they
   come from, and global defaults (clone strategy, timeouts, package manager).
2. **Design** — how a repo plugs into the WE ecosystem as an embeddable app, and
   how those apps are *woven* into launcher **seeds** (`we-seed.json`).
3. **Deployment** — the lifecycle profiles (`validate` / `build` / `start` /
   `deploy`), the **ordering** between repos, the target **environments**, and
   the **gates** that keep deploys safe.

Weave makes the edges between these concerns first-class. "Build `ad4m` before
`flux`", "the Flux launcher *uses* the Flux app", and "deploying Flux to
production requires `ad4m` and `we` first" are all expressible and all show up in
the same graph.

---

## 2. Concepts and type system

A Weave document denotes a typed multigraph.

### Node kinds

| Kind          | Declared in    | Meaning                                              |
| ------------- | -------------- | --------------------------------------------------- |
| `repo`        | `repos:`       | A managed repository in the fleet.                  |
| `seed`        | `seeds:`       | A WE launcher definition that compiles to `we-seed.json`. |
| `environment` | `environments:`| A named deploy target (e.g. staging, production).   |

### Edge kinds

| Edge          | Source → target | Source of truth                  | Visual            |
| ------------- | --------------- | -------------------------------- | ----------------- |
| `needs`       | repo → repo     | `repos.<r>.needs`                | solid arrow       |
| `deploy-needs`| repo → repo     | `repos.<r>.playbooks.deploy.needs` | red dashed arrow |
| `uses`        | seed → repo     | `seeds.<s>.apps[].use`           | thick green arrow |
| `deploy-to`   | repo → env      | `repos.<r>.playbooks.deploy.environment` | amber dotted arrow |

### Derived semantics

- **Targets** — repos with `target: true` *or* tier `core`, ordered by
  descending `priority` then name. This realises "starting with the most
  important target ones". (`coasys weave targets`.)
- **Build waves** — a Kahn topological layering over `needs`. Wave 0 has no
  unmet dependencies; each later wave depends only on earlier ones. Members of a
  wave can be operated in parallel.
- **Deploy waves** — the same layering restricted to repos with a `deploy`
  playbook, over `deploy-needs`.
- **Cycles** — any nodes that never resolve are reported as a dependency cycle
  (error).

---

## 3. Document structure

```yaml
version: 1                 # language version
weave:                     # fleet metadata
  name: coasys-fleet
  org: coasys
  description: ...
workspace:                 # where clones + state live
  repos_dir: workspace/repos
  state_dir: workspace/state
defaults: { ... }          # global defaults
environments: { ... }      # deploy targets
seeds: { ... }             # WE launcher definitions (design layer)
repos: { ... }             # the fleet
```

### 3.1 `defaults`

| Field                         | Type   | Default | Meaning                                       |
| ----------------------------- | ------ | ------- | --------------------------------------------- |
| `timeout_seconds`             | int    | 600     | Per-command timeout unless overridden.        |
| `clone.protocol`              | enum   | https   | `https` or `ssh`.                             |
| `clone.depth`                 | int?   | 1       | Shallow clone depth (`null` = full).          |
| `clone.partial`              | bool   | true    | Use partial clone.                            |
| `execute_detected_validation` | bool   | false   | Run auto-detected validation commands.        |
| `package_manager`             | string | uv      | Default tool; the ops control plane itself uses **uv**. |

### 3.2 `environments`

```yaml
environments:
  production:
    description: Public release channel.
    requires_env: [NPM_TOKEN, GITHUB_TOKEN]   # names only — never secrets
    protected: true                            # requires explicit operator decision
```

### 3.3 `repos`

| Field             | Type              | Meaning                                                       |
| ----------------- | ----------------- | ------------------------------------------------------------ |
| `tier`            | enum              | `core`, `active`, `language`, `dependency-fork`, `stale`, `unknown`. |
| `target`          | bool              | Mark as a priority target (core repos are targets implicitly). |
| `priority`        | int               | Higher operates first among targets.                          |
| `description`     | string            | Human description.                                            |
| `source`          | object            | `url`, `clone_url`, `branch`.                                 |
| `stack`           | list[str]         | e.g. `[typescript, rust]`.                                    |
| `needs`           | list[str]         | **Build/operate ordering** edges (repo names).                |
| `env`             | list[str]         | Required env var names for this repo.                         |
| `timeout_seconds` | int?              | Override default timeout.                                     |
| `playbooks`       | map[str,Playbook] | Lifecycle profiles.                                           |
| `we`              | object            | The **design binding** — `we.app` (a `WeApp`).               |

#### Playbook

```yaml
playbooks:
  build:
    run: [pnpm run build]          # the real commands
    check: [test -f package.json]  # cheap dry-run readiness commands
    env: [NPM_TOKEN]               # required env var names
    working_dir: app               # optional subdir
    timeout_seconds: 1200
    automatic: false               # may run unattended during validate
    environment: production        # (deploy only) target environment
    needs: [ad4m, we]              # (deploy only) deploy-ordering edges
```

The four lifecycle profile names are `validate`, `build`, `start`, `deploy`.
`run` are the real commands; `check` are the gating dry-run commands. **Deploys
are gated**: a deploy should declare `check` (a passing dry run), an
`environment`, and the required `env` names — and protected environments still
require an explicit operator decision.

### 3.4 `we` binding (design layer)

A repo becomes embeddable in WE by declaring `we.app`, mirroring the
`coasys/we` seed-system app schema exactly:

```yaml
we:
  app:
    id: flux
    name: Flux
    route: /flux
    capabilities: [perspectives, languages, agents]   # AD4M capabilities
    paths:
      project_root: ../flux/app
      dist: ../flux/app/dist
      dev_server: { port: 3030, host: localhost }
    commands: { install: yarn install, build: yarn build, dev: yarn dev }
```

Capabilities are validated against the WE set:
`perspectives`, `languages`, `agents`, `filesystem`, `network`.

### 3.5 `seeds` (design layer → `we-seed.json`)

A seed weaves repo apps into a launcher:

```yaml
seeds:
  coasys-workspace:
    project: { name: Coasys Workspace, version: 1.0.0, author: coasys }
    host: { ui: { enableTemplateSwitching: true } }
    ad4m: {}
    apps:
      - use: flux        # reference repo's we.app
      - use: we
      # or inline: { app: { id: ..., name: ..., ... } }
      # optional per-app route override: { use: flux, route: / }
```

`coasys weave seed coasys-workspace` compiles this to the exact `we-seed.json`
that WE's `initializeIntegrations.ts` consumes. Single-app seeds route at `/`
(WE full-screen mode) when no route is given; multi-app seeds keep their routes
(WE sidebar mode). Duplicate routes and dev-server port collisions are
validation errors/warnings.

---

## 4. The visual language

The dashboard *Weave* tab renders the model directly.

### Topology view (interactive)

A live, interactive network graph rendered with the real **WE design tokens**
(`--we-*`, themeable via the WE theme switcher: light / dark / cyberpunk):

- **Two layouts**, toggled in the toolbar: **Waves** (the §4 dependency
  layering — seeds left, one lane per build wave, environments right) and
  **Force** (a force-directed simulation over the same graph).
- **Direct manipulation**: drag nodes, scroll to zoom, drag the background to
  pan, **Reset view** to relayout.
- **Hover a node** to focus it and its neighbours (everything else dims).
- **Edge-kind filters** (`needs` / `deploy-needs` / `uses` / `deploy-to`) and a
  **tier highlight** filter.
- **Node colour** encodes tier; **shape** encodes kind (rounded = repo,
  pill = seed, square = environment). A **gold ring** marks targets; dots mark
  *deployable* (red), *has WE app* (green), and *has setup* (amber).
- Click any node for a detail panel (lifecycle profiles, stack, needs, WE app);
  click a seed node to open its compiled `we-seed.json`.

### Schema view

Form-driven editing generated from the model: each repo is a card with editable
`tier`, `target`, `priority`, `needs`, `stack`, and WE route. Edits are
validated live against `/api/weave/validate` (structure + semantics, including
cycle detection) and can be downloaded. Seeds expose one-click `we-seed.json`
compilation.

### Notation legend

```
[ rounded ]  repo        ──▶  needs (build order)
( pill    )  seed        ╌╌▶  deploy-needs
[ square  ]  environment ══▶  uses (design)
  ⭐ gold ring = target   ┄┄▶  deploy-to (environment)
  ● red = deployable      ● green = has WE app
```

---

## 4b. Starters & scaffolding (developer on-ramp)

To drive ecosystem adoption, Weave models the
[`create-ad4m-app`](https://github.com/coasys/create-ad4m-app) starter toolkit as
a first-class concept. A `starters:` section registers scaffolding toolkits:

```yaml
starters:
  ad4m:
    command: npx create-ad4m-app
    repo: create-ad4m-app          # the source repo in the fleet
    default_template: solid
    capabilities: [perspectives, languages, agents]
    templates:
      solid: { framework: solidjs, default: true }
      react: { framework: react }
      vue:   { framework: vue }
      r3f:   { framework: react-three-fiber }
```

`coasys weave create-app my-notes --template react --register` (or the dashboard
**Onboard** tab, or `POST /api/weave/create-app`) does two things:

1. Prints the exact scaffold command (`npx create-ad4m-app my-notes --template react`).
2. With `--register`, adds `my-notes` to the document as a full fleet member — a
   WE app binding (auto-assigned dev-server port, `/my-notes` route), the
   `setup → validate → build → start` lifecycle, a `needs: [ad4m]` edge, and
   `scaffold:` provenance — then validates and atomically saves. The new app
   appears immediately in the topology, plans, and (if added to a seed) launchers.

`--run` additionally executes the `npx` command. Scaffolded repos carry their
origin:

```yaml
repos:
  my-notes:
    scaffold: { starter: ad4m, template: react }
```

## 5. CLI reference

```bash
coasys weave lint [--path P] [--strict]   # structure + semantic validation
coasys weave targets [--path P]           # priority targets, most important first
coasys weave graph -f json|mermaid|dot    # the visual backbone, as data
coasys weave plan build|deploy [--path P] # ordered, wave-by-wave execution plan
coasys weave deploy-check [-e env] [--strict] # deployment readiness + rollout
coasys weave starters                     # list scaffolding starters + templates
coasys weave create-app <name> [-t solid] [--register] [--run]  # scaffold an AD4M app
coasys weave seed <name> [-o we-seed.json]# compile a launcher seed
coasys weave export-yml [-o coasys.yml]   # compile down to legacy ops config
coasys weave fmt [--check]                # rewrite (or check) canonical form
coasys weave schema [-o schema.json]      # JSON Schema (drives the forms)
```

## 6. HTTP API reference

| Method & path                       | Returns                                            |
| ----------------------------------- | -------------------------------------------------- |
| `GET  /api/weave/document`          | `{document, issues, targets}`                      |
| `GET  /api/weave/graph`             | `{nodes, edges, build_waves, deploy_waves, targets, cycles}` |
| `GET  /api/weave/graph.mmd`         | Mermaid source (text)                              |
| `GET  /api/weave/plan?profile=`     | ordered execution plan                             |
| `GET  /api/weave/seed/{name}`       | compiled `we-seed.json`                            |
| `GET  /api/weave/deploy-check?environment=` | deployment-readiness report                  |
| `GET  /api/weave/starters`          | scaffolding starters + templates                   |
| `POST /api/weave/create-app`        | scaffold + register an app (gated save)            |
| `GET  /api/weave/schema`            | JSON Schema for a document                         |
| `POST /api/weave/validate`          | `{ok, issues}` for a posted document               |
| `POST /api/weave/document`          | **validate-gated save**: `{ok, saved, issues, path}` |

### Saving and auto-save

`POST /api/weave/document` is the write path. It is **validate-gated**: the
posted document is parsed and semantically validated, and is written to disk
**only if there are no errors** (warnings are allowed). Writes are **atomic**
(temp file + `os.replace`) and **path-guarded** (never outside the project
root). The target is the existing `*.weave.yml`, or a freshly created
`coasys.weave.yml` (a legacy `coasys.yml` is left untouched, giving a clean
migration path).

The dashboard **Schema** tab uses this for **auto-save**: edits are debounced
(~0.7s) and saved automatically, with a live status indicator
(`unsaved → saving… → saved ✓`). Invalid edits are rejected, surfaced in the
issues panel, and never persisted. Auto-save can be toggled off, and **Save
now** forces an immediate write. `coasys weave fmt` performs the same canonical
write from the CLI (`--check` verifies a file is already canonical, for CI).

---

## 7. Validation rules

Pydantic enforces **structure** (types, unknown keys rejected, capability and
clone-protocol enums). The semantic validator (`coasys weave lint`) adds:

| Code                     | Level   | Checks                                              |
| ------------------------ | ------- | -------------------------------------------------- |
| `unknown-tier`           | warning | tier outside the known set                          |
| `self-dependency`        | error   | a repo lists itself in `needs`                       |
| `dangling-need`          | error   | `needs` references a missing repo                    |
| `dangling-deploy-need`   | error   | `deploy.needs` references a missing repo             |
| `unknown-environment`    | error   | `deploy.environment` not defined                     |
| `deploy-without-dry-run` | warning | deploy has no `check` gate                            |
| `duplicate-route`        | error   | two seed apps share a route                          |
| `duplicate-dev-port`     | warning | two WE apps share a dev-server port                  |
| `unresolvable-seed-app`  | error   | seed app has neither a valid `use` nor inline `app`  |
| `empty-seed`             | warning | seed has no apps                                     |
| `protected-no-secrets`   | info    | protected env declares no required env vars          |
| `dependency-cycle`       | error   | a cycle in `needs` / `deploy-needs`                  |

---

## 8. Relationship to `coasys.yml`

Weave is a **superset**. The loader accepts either file (preferring
`coasys.weave.yml`) and normalises both into the same model:

| Legacy `coasys.yml`                     | Weave                                  |
| --------------------------------------- | -------------------------------------- |
| `org`                                   | `weave.org`                            |
| `defaults.clone_depth` / `partial_clone`| `defaults.clone.depth` / `.partial`    |
| `playbooks.<p>.commands`                | `playbooks.<p>.run`                    |
| `playbooks.<p>.dry_run_commands`        | `playbooks.<p>.check`                  |
| `playbooks.<p>.env_required`            | `playbooks.<p>.env`                    |

`coasys weave export-yml` performs the reverse, so the existing operations layer
(`coasys sync/validate/operate/run`) consumes Weave transparently. Migrate by
renaming `coasys.yml` → `coasys.weave.yml` and incrementally adding `needs`,
`we`, `seeds`, `environments`, `target`, and `priority`.

---

## 9. Worked example

See [`examples/coasys.weave.yml`](../examples/coasys.weave.yml) for the full
fleet (AD4M / WE / Flux core targets, active members, two launcher seeds, and
staging/production environments) and
[`examples/flux-launcher.weave.yml`](../examples/flux-launcher.weave.yml) for a
minimal single-launcher document.

```bash
cd examples
coasys weave lint --path coasys.weave.yml
coasys weave targets --path coasys.weave.yml
coasys weave plan deploy --path coasys.weave.yml
coasys weave seed flux-launcher --path coasys.weave.yml -o ../we-seed.json
```
