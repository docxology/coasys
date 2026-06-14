"""Semantic validation for Weave documents.

Pydantic enforces *structure* (types, unknown keys, enums). This module enforces
*meaning*: cross-references resolve, the graph is acyclic, environments exist,
launcher seeds are wirable, and routes/ports don't collide. Issues are returned
rather than raised so the visual editor can surface them inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .graph import build_graph
from .model import KNOWN_TIERS, WeaveDocument

Level = Literal["error", "warning", "info"]


@dataclass
class Issue:
    level: Level
    code: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


def validate_document(document: WeaveDocument) -> list[Issue]:
    issues: list[Issue] = []
    repo_names = set(document.repos)

    # -- tiers -----------------------------------------------------------------
    for name, repo in document.repos.items():
        if repo.tier is not None and repo.tier not in KNOWN_TIERS:
            issues.append(
                Issue(
                    "warning",
                    "unknown-tier",
                    f"repo {name!r} has unknown tier {repo.tier!r}",
                    f"repos.{name}.tier",
                )
            )

    # -- build-ordering references --------------------------------------------
    for name, repo in document.repos.items():
        for dep in repo.needs:
            if dep == name:
                issues.append(
                    Issue("error", "self-dependency", f"repo {name!r} depends on itself",
                          f"repos.{name}.needs")
                )
            elif dep not in repo_names:
                issues.append(
                    Issue("error", "dangling-need",
                          f"repo {name!r} needs unknown repo {dep!r}",
                          f"repos.{name}.needs")
                )

    # -- deploy playbooks ------------------------------------------------------
    for name, repo in document.repos.items():
        deploy = repo.playbooks.get("deploy")
        if deploy is None:
            continue
        for dep in deploy.needs:
            if dep not in repo_names:
                issues.append(
                    Issue("error", "dangling-deploy-need",
                          f"repo {name!r} deploy needs unknown repo {dep!r}",
                          f"repos.{name}.playbooks.deploy.needs")
                )
        if deploy.environment and deploy.environment not in document.environments:
            issues.append(
                Issue("error", "unknown-environment",
                      f"repo {name!r} deploy targets undefined environment "
                      f"{deploy.environment!r}",
                      f"repos.{name}.playbooks.deploy.environment")
            )
        if not deploy.check:
            issues.append(
                Issue("warning", "deploy-without-dry-run",
                      f"repo {name!r} deploy has no dry-run `check` commands; "
                      "deploys should be gated by a passing dry run",
                      f"repos.{name}.playbooks.deploy.check")
            )

    # -- environments requiring secrets ---------------------------------------
    for env_name, env in document.environments.items():
        if env.protected and not env.requires_env:
            issues.append(
                Issue("info", "protected-no-secrets",
                      f"protected environment {env_name!r} declares no required env vars",
                      f"environments.{env_name}")
            )

    # -- seeds -----------------------------------------------------------------
    for seed_name, seed in document.seeds.items():
        if not seed.apps:
            issues.append(
                Issue("warning", "empty-seed", f"seed {seed_name!r} has no apps",
                      f"seeds.{seed_name}.apps")
            )
        routes: dict[str, str] = {}
        for index, app in enumerate(seed.apps):
            path = f"seeds.{seed_name}.apps[{index}]"
            resolved = _resolve_seed_app(document, app)
            if resolved is None:
                issues.append(
                    Issue("error", "unresolvable-seed-app",
                          f"seed {seed_name!r} app #{index} has neither a valid "
                          "`use` repo (with a `we.app`) nor an inline `app`",
                          path)
                )
                continue
            route = app.route or resolved.route
            if route in routes:
                issues.append(
                    Issue("error", "duplicate-route",
                          f"seed {seed_name!r} reuses route {route!r} "
                          f"({routes[route]} and {resolved.id})",
                          path)
                )
            routes[route] = resolved.id

    # -- dev server port collisions (across all WE apps) -----------------------
    ports: dict[int, str] = {}
    for name, repo in document.repos.items():
        if repo.we and repo.we.app and repo.we.app.paths and repo.we.app.paths.dev_server:
            port = repo.we.app.paths.dev_server.port
            if port in ports:
                issues.append(
                    Issue("warning", "duplicate-dev-port",
                          f"dev server port {port} used by both {ports[port]!r} and {name!r}",
                          f"repos.{name}.we.app.paths.dev_server.port")
                )
            ports[port] = name

    # -- cycles (from the graph) ----------------------------------------------
    graph = build_graph(document)
    for cycle in graph.cycles:
        if cycle:
            issues.append(
                Issue("error", "dependency-cycle",
                      "dependency cycle among: " + ", ".join(cycle),
                      "repos")
            )

    return issues


def _resolve_seed_app(document: WeaveDocument, app):  # -> WeApp | None
    if app.app is not None:
        return app.app
    if app.use and app.use in document.repos:
        binding = document.repos[app.use].we
        if binding and binding.app:
            return binding.app
    return None


def has_errors(issues: list[Issue]) -> bool:
    return any(issue.level == "error" for issue in issues)
