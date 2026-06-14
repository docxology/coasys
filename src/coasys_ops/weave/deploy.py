"""Deployment-readiness analysis.

This is the "deployment" concern of Weave made inspectable. Given a document
(and optionally a set of environment variables actually present), it computes a
per-repo readiness report and a fleet-level rollout plan. It is intentionally
read-only and side-effect free: it answers "is this deployable, and in what
order" without ever running a deploy. Actual execution stays behind the existing
operations gates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .graph import build_graph
from .model import WeaveDocument

# Readiness states, worst-first for sorting.
STATE_ORDER = ("blocked", "needs-approval", "ready", "not-deployable")


@dataclass
class DeployStatus:
    repo: str
    deployable: bool
    state: str
    environment: str | None
    protected: bool
    has_dry_run_gate: bool
    missing_env: list[str] = field(default_factory=list)
    unmet_needs: list[str] = field(default_factory=list)
    wave: int | None = None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "deployable": self.deployable,
            "state": self.state,
            "environment": self.environment,
            "protected": self.protected,
            "has_dry_run_gate": self.has_dry_run_gate,
            "missing_env": self.missing_env,
            "unmet_needs": self.unmet_needs,
            "wave": self.wave,
            "reasons": self.reasons,
        }


def _present_env(provided: set[str] | None) -> set[str]:
    if provided is not None:
        return set(provided)
    return {key for key, value in os.environ.items() if value}


def deploy_readiness(
    document: WeaveDocument,
    environment: str | None = None,
    provided_env: set[str] | None = None,
) -> dict:
    """Compute deployment readiness for every repo with a deploy playbook.

    ``environment`` optionally filters to repos targeting that environment.
    ``provided_env`` is the set of env var names treated as available; when
    omitted, the current process environment is used.
    """
    present = _present_env(provided_env)
    graph = build_graph(document)
    deploy_wave_of: dict[str, int] = {}
    for index, wave in enumerate(graph.deploy_waves):
        for repo in wave:
            deploy_wave_of[repo] = index

    statuses: list[DeployStatus] = []
    for name in sorted(document.repos):
        repo = document.repos[name]
        deploy = repo.playbooks.get("deploy")
        if deploy is None:
            statuses.append(
                DeployStatus(
                    repo=name,
                    deployable=False,
                    state="not-deployable",
                    environment=None,
                    protected=False,
                    has_dry_run_gate=False,
                    reasons=["no deploy playbook"],
                )
            )
            continue

        env_name = deploy.environment
        if environment is not None and env_name != environment:
            continue

        env_obj = document.environments.get(env_name) if env_name else None
        protected = bool(env_obj.protected) if env_obj else False

        # Required env names: repo-level + playbook-level + environment-level.
        required: list[str] = []
        for source in (repo.env, deploy.env, env_obj.requires_env if env_obj else []):
            for var in source:
                if var not in required:
                    required.append(var)
        missing_env = [var for var in required if var not in present]

        # A deploy need that references a non-existent repo blocks; needs that
        # point at libraries (no deploy playbook) are build-order hints, not
        # deploy blockers, and are surfaced as the rollout ordering instead.
        unmet_needs = [dep for dep in deploy.needs if dep not in document.repos]
        has_gate = bool(deploy.check)

        reasons: list[str] = []
        if env_name and env_obj is None:
            reasons.append(f"undefined environment {env_name!r}")
        if not has_gate:
            reasons.append("no dry-run gate (`check`)")
        if missing_env:
            reasons.append("missing env: " + ", ".join(missing_env))
        if unmet_needs:
            reasons.append("deploy needs unknown repo: " + ", ".join(unmet_needs))

        blocked = bool(reasons)
        if blocked:
            state = "blocked"
        elif protected:
            state = "needs-approval"
            reasons.append("protected environment requires an explicit operator decision")
        else:
            state = "ready"

        statuses.append(
            DeployStatus(
                repo=name,
                deployable=True,
                state=state,
                environment=env_name,
                protected=protected,
                has_dry_run_gate=has_gate,
                missing_env=missing_env,
                unmet_needs=unmet_needs,
                wave=deploy_wave_of.get(name),
                reasons=reasons,
            )
        )

    counts: dict[str, int] = {state: 0 for state in STATE_ORDER}
    for status in statuses:
        counts[status.state] = counts.get(status.state, 0) + 1

    # Rollout waves: only deployable repos, in deploy-wave order.
    rollout: list[dict] = []
    by_name = {status.repo: status for status in statuses}
    for index, wave in enumerate(graph.deploy_waves):
        members = []
        for repo in wave:
            status = by_name.get(repo)
            if status is None or not status.deployable:
                continue
            if environment is not None and status.environment != environment:
                continue
            members.append({"repo": repo, "state": status.state})
        if members:
            rollout.append({"wave": index, "repos": members})

    return {
        "environment": environment,
        "counts": counts,
        "cycles": graph.cycles,
        "statuses": [status.to_dict() for status in statuses if status.deployable],
        "rollout": rollout,
        "ready_to_roll": counts.get("blocked", 0) == 0 and not graph.cycles,
    }
