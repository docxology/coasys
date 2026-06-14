"""Exporters: round-trip Weave to the legacy ops config, JSON Schema, and plans.

These keep Weave interoperable. ``to_coasys_yml`` proves backward compatibility
(a Weave document compiles down to a config the existing operations layer reads),
``json_schema`` powers the schema-driven visual forms, and ``operation_plan``
turns the graph waves into an ordered execution plan.
"""

from __future__ import annotations

from typing import Any

import yaml

from .graph import build_graph
from .model import WeaveDocument


def to_coasys_yml_mapping(document: WeaveDocument) -> dict[str, Any]:
    """Compile a Weave document down to the legacy ``coasys.yml`` mapping."""
    defaults: dict[str, Any] = {
        "timeout_seconds": document.defaults.timeout_seconds,
        "clone_protocol": document.defaults.clone.protocol,
        "clone_depth": document.defaults.clone.depth,
        "partial_clone": document.defaults.clone.partial,
        "execute_detected_validation": document.defaults.execute_detected_validation,
    }

    repos: dict[str, Any] = {}
    for name, repo in document.repos.items():
        entry: dict[str, Any] = {}
        if repo.tier:
            entry["tier"] = repo.tier
        if repo.timeout_seconds is not None:
            entry["timeout_seconds"] = repo.timeout_seconds
        if repo.env:
            entry["env_required"] = list(repo.env)
        if repo.source and repo.source.clone_url:
            entry["clone_url"] = repo.source.clone_url
        playbooks: dict[str, Any] = {}
        for profile, pb in repo.playbooks.items():
            pb_entry: dict[str, Any] = {}
            if pb.run:
                pb_entry["commands"] = list(pb.run)
            if pb.check:
                pb_entry["dry_run_commands"] = list(pb.check)
            if pb.env:
                pb_entry["env_required"] = list(pb.env)
            if pb.working_dir:
                pb_entry["working_dir"] = pb.working_dir
            if pb.timeout_seconds is not None:
                pb_entry["timeout_seconds"] = pb.timeout_seconds
            if pb.automatic:
                pb_entry["automatic"] = True
            if pb.allow_detected:
                pb_entry["allow_detected"] = True
            playbooks[profile] = pb_entry
        if playbooks:
            entry["playbooks"] = playbooks
        repos[name] = entry

    return {
        "org": document.weave.org,
        "workspace": {
            "repos_dir": document.workspace.repos_dir,
            "state_dir": document.workspace.state_dir,
        },
        "defaults": defaults,
        "repos": repos,
    }


def to_coasys_yml(document: WeaveDocument) -> str:
    return yaml.safe_dump(
        to_coasys_yml_mapping(document), sort_keys=False, default_flow_style=False
    )


def json_schema() -> dict[str, Any]:
    """The JSON Schema for a Weave document (drives the visual schema forms)."""
    return WeaveDocument.model_json_schema()


def operation_plan(document: WeaveDocument, profile: str = "build") -> dict[str, Any]:
    """An ordered execution plan for ``profile`` based on graph waves.

    For ``deploy`` the deploy waves and deploy-needs edges are used; otherwise the
    build waves are used. Only repos that actually declare the profile are
    included in each wave, but ordering respects the full dependency layering.
    """
    graph = build_graph(document)
    waves = graph.deploy_waves if profile == "deploy" else graph.build_waves
    plan_waves: list[dict[str, Any]] = []
    for index, wave in enumerate(waves):
        steps = []
        for name in wave:
            repo = document.repos.get(name)
            if repo is None or profile not in repo.playbooks:
                continue
            pb = repo.playbooks[profile]
            steps.append(
                {
                    "repo": name,
                    "run": pb.run,
                    "check": pb.check,
                    "env": pb.env,
                    "environment": pb.environment,
                    "automatic": pb.automatic,
                }
            )
        if steps:
            plan_waves.append({"wave": index, "steps": steps})
    return {
        "profile": profile,
        "targets": graph.targets,
        "waves": plan_waves,
        "cycles": graph.cycles,
    }
