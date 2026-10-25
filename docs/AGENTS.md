# coasys — Agent Notes

## Layout

- `src/` — Python implementation (control plane, dashboard server);
  pytest with coverage configured in `pyproject.toml`
  (`[tool.pytest.ini_options]`).
- `coasys.yml` — fleet configuration: `org: coasys`, workspace repo and
  state directories (`workspace/repos`, `workspace/state`), default
  timeouts.
- `docs/` — 14 topic files (API, ARCHITECTURE, CLI, CONFIGURATION,
  DASHBOARD, OPERATIONS, PLAYBOOKS, README, RELEASE_CHECKLIST, plus
  others) with an `images/` subfolder.

## Conventions observed

- Plain Markdown relative links across `docs/` (all verified resolving).
- Configuration is YAML-driven via `coasys.yml`; docs reference the same
  defaults.

## Maintenance

- Add `docs/AGENTS.md` updates when new operational docs land; keep the
  file list matched to actual topics.
- `docs/README.md` is the human index — new topic files should be added
  there.

## Docs provenance

`docs/AGENTS.md` added by the 2026-08-29 docs-audit; all other content is
pre-existing and was verified link-clean, not rewritten.
