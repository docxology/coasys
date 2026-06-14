"""Compile a Weave ``seed`` into a real WE ``we-seed.json``.

This is the "design" half of the language made executable: a seed declaration
references repos' WE apps (or inlines them) and is compiled to the exact JSON
shape that ``coasys/we``'s ``initializeIntegrations.ts`` consumes.
"""

from __future__ import annotations

import json
from typing import Any

from .model import Seed, WeApp, WeaveDocument


def _resolve(document: WeaveDocument, app) -> WeApp | None:
    if app.app is not None:
        return app.app
    if app.use and app.use in document.repos:
        binding = document.repos[app.use].we
        if binding and binding.app:
            return binding.app
    return None


def _app_to_seed_json(app: WeApp, route_override: str | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": app.id,
        "name": app.name,
        "route": route_override or app.route,
        "capabilities": list(app.capabilities),
    }
    if app.paths is not None:
        paths: dict[str, Any] = {}
        if app.paths.project_root is not None:
            paths["projectRoot"] = app.paths.project_root
        if app.paths.dist is not None:
            paths["dist"] = app.paths.dist
        if app.paths.dev_server is not None:
            paths["devServer"] = {
                "port": app.paths.dev_server.port,
                "host": app.paths.dev_server.host,
            }
        if paths:
            entry["paths"] = paths
    if app.commands is not None:
        commands = {
            key: value
            for key, value in (
                ("install", app.commands.install),
                ("build", app.commands.build),
                ("dev", app.commands.dev),
            )
            if value is not None
        }
        if commands:
            entry["commands"] = commands
    return entry


def render_seed(document: WeaveDocument, seed_name: str) -> dict[str, Any]:
    """Return the ``we-seed.json`` payload for ``seed_name``.

    For a single-app seed the app is routed at ``/`` (WE full-screen mode) unless
    a route is explicitly set, matching WE's single-vs-multi-app convention.
    """
    if seed_name not in document.seeds:
        raise KeyError(f"unknown seed {seed_name!r}")
    seed: Seed = document.seeds[seed_name]

    apps_json: list[dict[str, Any]] = []
    single = len(seed.apps) == 1
    for app_ref in seed.apps:
        resolved = _resolve(document, app_ref)
        if resolved is None:
            raise ValueError(
                f"seed {seed_name!r} references an app that cannot be resolved "
                f"(use={app_ref.use!r})"
            )
        route = app_ref.route
        if route is None and single and resolved.route in ("", None):
            route = "/"
        apps_json.append(_app_to_seed_json(resolved, route))

    return {
        "project": {
            "name": seed.project.name,
            "version": seed.project.version,
            "description": seed.project.description,
            "author": seed.project.author,
        },
        "host": seed.host,
        "ad4m": seed.ad4m,
        "apps": apps_json,
    }


def render_seed_json(document: WeaveDocument, seed_name: str, indent: int = 2) -> str:
    return json.dumps(render_seed(document, seed_name), indent=indent)
