# Weave — formal grammar and operational semantics

This document gives the *formal* specification of the Weave language: the
concrete grammar (EBNF), the abstract domains, and the operational semantics for
the **setup** and **deployment** lifecycles. It complements the prose reference
in [WEAVE_LANGUAGE.md](WEAVE_LANGUAGE.md) and is the authority when the two
disagree. The implementation lives in `coasys_ops.weave` and is checked against
these rules by `tests/test_weave.py`.

## 1. Concrete grammar (EBNF)

Weave's concrete syntax is YAML 1.1. The grammar below constrains the *parsed*
structure (a mapping tree), not the YAML surface bytes. `STRING`, `INT`, `BOOL`
are YAML scalars; `{ … }` is a mapping, `[ … ]` a sequence. `?` = optional,
`*` = zero-or-more, `|` = alternation.

```ebnf
document     = "version" INT ,
               [ "weave" meta ] ,
               [ "workspace" workspace ] ,
               [ "defaults" defaults ] ,
               [ "environments" "{" { ident ":" environment } "}" ] ,
               [ "starters" "{" { ident ":" starter } "}" ] ,
               [ "seeds" "{" { ident ":" seed } "}" ] ,
               [ "repos" "{" { ident ":" repo } "}" ] ;

starter      = "command" STRING ,
               [ "repo" ident ] , [ "description" STRING ] , [ "docs_url" STRING ] ,
               [ "default_template" ident ] , [ "capabilities" [ capability * ] ] ,
               [ "templates" "{" { ident ":" starter_template } "}" ] ;
starter_template = { "framework" STRING | "description" STRING | "default" BOOL } ;

meta         = { "name" STRING | "org" STRING | "description" STRING } ;

workspace    = { "repos_dir" STRING | "state_dir" STRING } ;

defaults     = { "timeout_seconds" INT
               | "clone" clone
               | "execute_detected_validation" BOOL
               | "package_manager" STRING } ;
clone        = { "protocol" ( "https" | "ssh" )
               | "depth" ( INT | null )
               | "partial" BOOL } ;

environment  = { "description" STRING
               | "requires_env" [ STRING * ]
               | "protected" BOOL } ;

repo         = { "tier" tier
               | "target" BOOL
               | "priority" INT
               | "description" STRING
               | "source" source
               | "stack" [ STRING * ]
               | "needs" [ ident * ]          (* build-ordering edges *)
               | "env" [ STRING * ]
               | "timeout_seconds" INT
               | "we" we_binding
               | "scaffold" scaffold_ref
               | "playbooks" "{" { profile ":" playbook } "}" } ;
scaffold_ref = "starter" ident , [ "template" ident ] ;
tier         = "core" | "active" | "language" | "dependency-fork" | "stale" | "unknown" ;
source       = { "url" STRING | "clone_url" STRING | "branch" STRING } ;

profile      = "setup" | "validate" | "build" | "start" | "deploy" | ident ;
playbook     = { "run" [ STRING * ]            (* real commands *)
               | "check" [ STRING * ]          (* dry-run gate commands *)
               | "env" [ STRING * ]
               | "working_dir" STRING
               | "timeout_seconds" INT
               | "automatic" BOOL
               | "allow_detected" BOOL
               | "environment" ident            (* deploy only *)
               | "needs" [ ident * ] } ;        (* deploy-ordering edges *)

we_binding   = { "app" we_app } ;
we_app       = "id" STRING , "name" STRING ,
               [ "route" STRING ] ,
               [ "capabilities" [ capability * ] ] ,
               [ "paths" app_paths ] , [ "commands" app_commands ] ;
capability   = "perspectives" | "languages" | "agents" | "filesystem" | "network" ;
app_paths    = { "project_root" STRING | "dist" STRING | "dev_server" dev_server } ;
dev_server   = "port" INT , [ "host" STRING ] ;
app_commands = { "install" STRING | "build" STRING | "dev" STRING } ;

seed         = "project" seed_project ,
               [ "host" mapping ] , [ "ad4m" mapping ] ,
               [ "apps" [ seed_app * ] ] ;
seed_project = "name" STRING , [ "version" STRING ] ,
               [ "description" STRING ] , [ "author" STRING ] ;
seed_app     = { "use" ident | "route" STRING | "app" we_app } ;

ident        = STRING ;   (* a repo/seed/environment key *)
```

Unknown keys are rejected (the model is `extra="forbid"`), so typos surface as
structural errors. The legacy `coasys.yml` shape is accepted by a normalising
front-end (see WEAVE_LANGUAGE §8) and is grammatically equivalent after
translation (`commands→run`, `dry_run_commands→check`, `env_required→env`).

## 2. Abstract domains

Let a document `D` denote:

- `R` — the set of repo identifiers (`dom(repos)`).
- `E` — the set of environment identifiers.
- `S` — the set of seed identifiers.
- `P(r) ⊆ {setup,validate,build,start,deploy,…}` — profiles defined for `r`.
- `needs : R → 𝒫(R)` — build-ordering edges.
- `dneeds : R ⇀ 𝒫(R)` — deploy-ordering edges (defined when `deploy ∈ P(r)`).
- `env : R ⇀ E` — deploy environment (from `playbooks.deploy.environment`).
- `uses : S → 𝒫(R)` — seed→app design edges.

## 3. Well-formedness (static semantics)

`D` is **well-formed** iff all of the following hold (violations are the error
codes emitted by `validate_document`):

1. **Resolvable build edges.** ∀ r, needs(r) ⊆ R and r ∉ needs(r).
   *(`dangling-need`, `self-dependency`)*
2. **Resolvable deploy edges.** ∀ r with deploy ∈ P(r): dneeds(r) ⊆ R.
   *(`dangling-deploy-need`)*
3. **Defined environments.** ∀ r with env(r) defined: env(r) ∈ E.
   *(`unknown-environment`)*
4. **Acyclicity.** The relations `needs` and `dneeds` are each acyclic.
   *(`dependency-cycle`)*
5. **Seed resolvability.** ∀ s, ∀ a ∈ apps(s): a has an inline `app`, or
   `a.use ∈ R` and `repos[a.use].we.app` is defined. *(`unresolvable-seed-app`)*
6. **Unique seed routes.** Within a seed, the routes of its apps are distinct.
   *(`duplicate-route`)*

Warnings (non-blocking): unknown tier, deploy without a `check` gate, duplicate
dev-server ports across WE apps, empty seeds, protected env with no secrets.

## 4. The dependency order and waves

Define the **wave function** `W` over a dependency relation `≺` on a node set
`N` as the Kahn layering:

```
W₀ = { n ∈ N : preds(n) = ∅ }
Wₖ = { n ∈ N : preds(n) ⊆ ⋃_{i<k} Wᵢ } \ ⋃_{i<k} Wᵢ
```

The layering terminates iff `≺` is acyclic (rule 3.4); any residual nodes form
the reported cycle set. Two layerings are used:

- **build/setup waves** = `W` over `needs` on `R`.
- **deploy waves** = `W` over `dneeds` on `{ r : deploy ∈ P(r) }`.

Members of the same wave are mutually independent and may be operated
concurrently; wave order is a valid sequential execution order.

## 5. Lifecycle (canonical order)

The lifecycle profiles are totally ordered:

```
setup ≺ validate ≺ build ≺ start          deploy  (gated, see §7)
```

`setup` is the bootstrapping phase — installing toolchains and dependencies
(`pnpm install`, `yarn install`, `cargo fetch`, `uv sync`). For any profile
`p`, the **operation plan** is the sequence of waves over `needs`, where wave
`Wₖ` contributes the steps `{ (r, playbooks[r][p]) : r ∈ Wₖ ∧ p ∈ P(r) }`.
Thus a repo is only setup/built/started after everything it `needs`.

## 6. Setup readiness

A repo `r` is **setup-ready** when `setup ∈ P(r)` and every `s ∈ needs(r)` is
itself setup-ready (transitively grounded in wave 0). The setup plan
(`coasys weave plan setup`) emits the setup commands in wave order; the visual
**Topology** view colours each node by whether it carries a `setup` playbook.

## 7. Deployment readiness (gating predicate)

For a repo `r` with `deploy ∈ P(r)`, let `pb = playbooks[r].deploy`,
`e = env(r)`, and `present ⊆ STRING` the set of available environment-variable
names. Define:

```
required(r)  = repo.env ∪ pb.env ∪ (e ? environments[e].requires_env : ∅)
missing(r)   = required(r) \ present
hasGate(r)   = pb.check ≠ ∅
envOK(r)     = e is undefined  ∨  e ∈ E
danglingNeeds(r) = pb.needs \ R
```

The **readiness state** is:

```
state(r) = blocked          if ¬envOK(r) ∨ ¬hasGate(r) ∨ missing(r) ≠ ∅ ∨ danglingNeeds(r) ≠ ∅
         = needs-approval   else if environments[e].protected
         = ready            otherwise
```

The fleet is **ready to roll** iff no deployable repo is `blocked` and `dneeds`
is acyclic. The **rollout** is the deploy-wave sequence restricted to deployable
repos. This predicate is implemented in `weave/deploy.py` and is side-effect
free: it never executes a deploy. Real execution additionally requires an
explicit operator decision (protected environments) and a passing dry run.

## 8. Visual ↔ formal correspondence

The interactive Topology view is a faithful drawing of the multigraph
`(N, edges)` where `N = R ∪ S ∪ E` and edges are exactly:

```
needs        : r' → r   for r' ∈ needs(r)
deploy-needs : r' → r   for r' ∈ dneeds(r)
uses         : s → r    for r ∈ uses(s)
deploy-to    : r → e    for env(r) = e
```

Layout is either the wave layering of §4 (the "Waves" layout) or a force
simulation over the same graph (the "Force" layout). Because both the picture
and the planner consume `build_graph(D)`, the topology, the plan, and the
deploy gate cannot diverge.
```
