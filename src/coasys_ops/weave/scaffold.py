"""Scaffolding: turn a starter (create-ad4m-app) into a registered fleet app.

This is the developer on-ramp made part of the language. ``scaffold_command``
produces the exact ``npx create-ad4m-app`` invocation; ``register_app`` returns a
*new* document with the scaffolded app added as a first-class repo (WE app
binding + the full setup→start lifecycle + provenance), so a brand-new app shows
up in the topology, plans, and seeds immediately. Both functions are pure and
side-effect free; execution and persistence are the caller's concern.
"""

from __future__ import annotations

from .loader import parse_document
from .model import Starter, WeaveDocument

DEFAULT_CAPABILITIES = ["perspectives", "languages", "agents"]


def scaffold_command(starter: Starter, app_name: str, template: str | None) -> str:
    """The shell command a developer runs to scaffold the app."""
    cmd = f"{starter.command} {app_name}"
    chosen = template or starter.default_template
    if chosen:
        cmd += f" --template {chosen}"
    return cmd


def _next_dev_port(document: WeaveDocument) -> int:
    used = set()
    for repo in document.repos.values():
        if repo.we and repo.we.app and repo.we.app.paths and repo.we.app.paths.dev_server:
            used.add(repo.we.app.paths.dev_server.port)
    port = 3100
    while port in used:
        port += 1
    return port


def register_app(
    document: WeaveDocument,
    app_name: str,
    *,
    starter_key: str = "ad4m",
    template: str | None = None,
    route: str | None = None,
    port: int | None = None,
    tier: str = "active",
) -> tuple[WeaveDocument, str]:
    """Return ``(new_document, scaffold_command)`` with ``app_name`` registered.

    The new repo gets a WE app binding and the full lifecycle so it is a full
    member of the fleet. If an ``ad4m`` repo exists, the app ``needs`` it.
    """
    if app_name in document.repos:
        raise ValueError(f"repo {app_name!r} already exists")
    if starter_key not in document.starters:
        raise KeyError(f"unknown starter {starter_key!r}")
    starter = document.starters[starter_key]
    chosen = template or starter.default_template
    if chosen and starter.templates and chosen not in starter.templates:
        raise ValueError(
            f"unknown template {chosen!r}; available: {', '.join(sorted(starter.templates))}"
        )
    framework = ""
    if chosen and chosen in starter.templates:
        framework = starter.templates[chosen].framework or chosen
    caps = starter.capabilities or DEFAULT_CAPABILITIES
    dev_port = port or _next_dev_port(document)
    app_route = route or f"/{app_name}"
    needs = ["ad4m"] if "ad4m" in document.repos else []

    repo_entry = {
        "tier": tier,
        "description": f"AD4M app scaffolded from {starter_key}"
        + (f" ({chosen})" if chosen else ""),
        "stack": [framework] if framework else [],
        "needs": needs,
        "scaffold": {"starter": starter_key, "template": chosen},
        "we": {
            "app": {
                "id": app_name,
                "name": app_name,
                "route": app_route,
                "capabilities": list(caps),
                "paths": {
                    "project_root": f"../{app_name}",
                    "dist": f"../{app_name}/dist",
                    "dev_server": {"port": dev_port, "host": "localhost"},
                },
                "commands": {
                    "install": "pnpm install",
                    "build": "pnpm build",
                    "dev": "pnpm dev",
                },
            }
        },
        "playbooks": {
            "setup": {"run": ["pnpm install"], "check": ["test -f package.json"]},
            "validate": {"run": ["pnpm build"], "check": ["test -f package.json"]},
            "build": {"run": ["pnpm build"], "check": ["test -f package.json"]},
            "start": {"run": ["pnpm dev"], "check": ["test -f package.json"]},
        },
    }

    mapping = document.model_dump(exclude_none=True)
    mapping.setdefault("repos", {})[app_name] = repo_entry
    new_doc = parse_document(mapping)
    return new_doc, scaffold_command(starter, app_name, chosen)
