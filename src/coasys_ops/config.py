from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class OperationPlaybook:
    commands: list[str] = field(default_factory=list)
    dry_run_commands: list[str] = field(default_factory=list)
    env_required: list[str] = field(default_factory=list)
    working_dir: str | None = None
    timeout_seconds: int | None = None
    automatic: bool = False
    allow_detected: bool = False


@dataclass(slots=True)
class RepoOverride:
    clone_url: str | None = None
    tier: str | None = None
    validation_commands: list[str] = field(default_factory=list)
    profiles: dict[str, list[str]] = field(default_factory=dict)
    playbooks: dict[str, OperationPlaybook] = field(default_factory=dict)
    env_required: list[str] = field(default_factory=list)
    timeout_seconds: int | None = None
    do_not_run_automatically: bool = False
    execute_detected_validation: bool | None = None


@dataclass(slots=True)
class WorkspaceConfig:
    repos_dir: Path
    state_dir: Path


@dataclass(slots=True)
class AppConfig:
    root: Path
    org: str
    workspace: WorkspaceConfig
    default_timeout_seconds: int = 600
    clone_depth: int | None = 1
    partial_clone: bool = True
    execute_detected_validation: bool = False
    repos: dict[str, RepoOverride] = field(default_factory=dict)

    def override_for(self, repo_name: str) -> RepoOverride:
        return self.repos.get(repo_name, RepoOverride())


def _as_command_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise TypeError(f"Expected command string or list, got {type(value).__name__}")


def _load_playbook(payload: Any) -> OperationPlaybook:
    if isinstance(payload, str | list) or payload is None:
        return OperationPlaybook(commands=_as_command_list(payload))
    if not isinstance(payload, dict):
        raise TypeError("repo playbook must be a string, list, or mapping")
    return OperationPlaybook(
        commands=_as_command_list(payload.get("commands")),
        dry_run_commands=_as_command_list(payload.get("dry_run_commands")),
        env_required=[str(item) for item in payload.get("env_required", [])],
        working_dir=payload.get("working_dir"),
        timeout_seconds=payload.get("timeout_seconds"),
        automatic=bool(payload.get("automatic", False)),
        allow_detected=bool(payload.get("allow_detected", False)),
    )


def _load_repo_override(payload: dict[str, Any]) -> RepoOverride:
    profiles: dict[str, list[str]] = {}
    raw_profiles = payload.get("profiles") or {}
    if not isinstance(raw_profiles, dict):
        raise TypeError("repo profiles must be a mapping")
    for name, commands in raw_profiles.items():
        profiles[str(name)] = _as_command_list(commands)

    playbooks: dict[str, OperationPlaybook] = {}
    raw_playbooks = payload.get("playbooks") or {}
    if not isinstance(raw_playbooks, dict):
        raise TypeError("repo playbooks must be a mapping")
    for name, playbook_payload in raw_playbooks.items():
        playbooks[str(name)] = _load_playbook(playbook_payload)

    return RepoOverride(
        clone_url=payload.get("clone_url"),
        tier=payload.get("tier"),
        validation_commands=_as_command_list(payload.get("validation_commands")),
        profiles=profiles,
        playbooks=playbooks,
        env_required=[str(item) for item in payload.get("env_required", [])],
        timeout_seconds=payload.get("timeout_seconds"),
        do_not_run_automatically=bool(payload.get("do_not_run_automatically", False)),
        execute_detected_validation=payload.get("execute_detected_validation"),
    )


def find_project_root(start: Path | None = None) -> Path:
    cursor = (start or Path.cwd()).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for candidate in [cursor, *cursor.parents]:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return cursor


def load_config(root: Path | None = None) -> AppConfig:
    project_root = find_project_root(root)
    config_path = project_root / "coasys.yml"
    payload: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}

    workspace_payload = payload.get("workspace") or {}
    defaults = payload.get("defaults") or {}
    repos_dir = Path(workspace_payload.get("repos_dir", "workspace/repos"))
    state_dir = Path(workspace_payload.get("state_dir", "workspace/state"))
    if not repos_dir.is_absolute():
        repos_dir = project_root / repos_dir
    if not state_dir.is_absolute():
        state_dir = project_root / state_dir

    repos_payload = payload.get("repos") or {}
    if not isinstance(repos_payload, dict):
        raise TypeError("coasys.yml repos must be a mapping")

    repos = {
        str(repo_name): _load_repo_override(repo_payload or {})
        for repo_name, repo_payload in repos_payload.items()
    }

    return AppConfig(
        root=project_root,
        org=str(payload.get("org") or "coasys"),
        workspace=WorkspaceConfig(repos_dir=repos_dir, state_dir=state_dir),
        default_timeout_seconds=int(defaults.get("timeout_seconds") or 600),
        clone_depth=defaults.get("clone_depth", 1),
        partial_clone=bool(defaults.get("partial_clone", True)),
        execute_detected_validation=bool(defaults.get("execute_detected_validation", False)),
        repos=repos,
    )
