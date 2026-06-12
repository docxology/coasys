from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

from .classify import classify_repo
from .config import AppConfig, OperationPlaybook, RepoOverride, load_config
from .detect import detect_repo
from .github_api import GitHubClient
from .gitops import clone_or_fetch_repo, inspect_git_checkout, run_command
from .models import RepoMetadata, RepoSnapshot, now_iso
from .store import Store


class CoasysOps:
    def __init__(
        self,
        root: Path | None = None,
        config: AppConfig | None = None,
        store: Store | None = None,
        github: GitHubClient | None = None,
    ) -> None:
        self.config = config or load_config(root)
        self.config.workspace.repos_dir.mkdir(parents=True, exist_ok=True)
        self.config.workspace.state_dir.mkdir(parents=True, exist_ok=True)
        (self.config.workspace.state_dir / "logs").mkdir(parents=True, exist_ok=True)
        self.store = store or Store(self.config.workspace.state_dir / "coasys.sqlite3")
        self.github = github or GitHubClient()

    def list_repos(self) -> list[dict[str, Any]]:
        return [self._decorate_repo(repo) for repo in self.store.list_repos()]

    def get_repo(self, name: str) -> dict[str, Any] | None:
        repo = self.store.get_repo(name)
        return self._decorate_repo(repo) if repo else None

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_runs(limit=limit)

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        return self.store.get_run(run_id)

    def operate_fleet(
        self,
        *,
        org: str | None = None,
        clone: bool = True,
        validate: bool = True,
        deploy: bool = False,
        execute_deploy: bool = False,
        execute_configured: bool = False,
        tier: str | None = None,
        limit: int | None = None,
        execute_detected: bool = False,
    ) -> dict[str, Any]:
        existing_repos = self.store.list_repos()
        if clone or not existing_repos:
            synced = self.sync(org=org, clone=clone, limit=limit)
        else:
            synced = existing_repos[:limit] if limit else existing_repos
        selected = [repo for repo in synced if tier is None or repo["tier"] == tier]

        validated_count = 0
        deployed_count = 0
        deploy_blocked_count = 0
        deploy_skipped_count = 0
        configured_dry_run_count = 0

        if validate:
            for repo in selected:
                self.validate_repo(str(repo["name"]), execute_detected=execute_detected)
                validated_count += 1

        if execute_configured:
            for repo in selected:
                for profile in ("build", "start"):
                    if self._configured_playbook(str(repo["name"]), profile):
                        self.run_profile(str(repo["name"]), profile, dry_run=True)
                        configured_dry_run_count += 1

        if deploy:
            for repo in selected:
                refreshed = self.store.get_repo(str(repo["name"]))
                if not refreshed or not self._configured_playbook(str(repo["name"]), "deploy"):
                    deploy_blocked_count += 1
                    continue
                if execute_deploy:
                    try:
                        if not self._last_profile_status(
                            str(repo["name"]), "deploy", "dry_run_passed"
                        ):
                            self.run_profile(str(repo["name"]), "deploy", dry_run=True)
                        run = self.run_profile(str(repo["name"]), "deploy", execute=True)
                    except ValueError:
                        deploy_blocked_count += 1
                        continue
                    if run["status"] == "deploy_executed":
                        deployed_count += 1
                    else:
                        deploy_blocked_count += 1
                    continue
                try:
                    run = self.run_profile(str(repo["name"]), "deploy", dry_run=True)
                except ValueError:
                    deploy_blocked_count += 1
                    continue
                if run["status"] == "dry_run_passed":
                    deploy_skipped_count += 1
                else:
                    deploy_blocked_count += 1

        summary = self.summary()
        return {
            "generated_at": summary["generated_at"],
            "repo_count": len(selected),
            "synced_count": len(selected),
            "validated_count": validated_count,
            "deployed_count": deployed_count,
            "configured_dry_run_count": configured_dry_run_count,
            "deploy_blocked_count": deploy_blocked_count,
            "deploy_skipped_count": deploy_skipped_count,
            "summary": summary,
        }

    def summary(self) -> dict[str, Any]:
        repos = self.store.list_repos()
        tiers = self._count_values(repo.get("tier") or "unknown" for repo in repos)
        statuses = self._count_values(
            repo.get("validation_status") or "unknown" for repo in repos
        )
        languages = self._count_values(repo.get("language") or "unknown" for repo in repos)
        clone_statuses = self._count_values(self._clone_status(repo) for repo in repos)
        config_statuses = self._count_values(self._config_status(repo) for repo in repos)
        deploy_statuses = self._count_values(self._deploy_status(repo) for repo in repos)
        start_statuses = self._count_values(self._start_status(repo) for repo in repos)
        dry_run_statuses = self._count_values(self._dry_run_status(repo) for repo in repos)
        dirty_count = sum(1 for repo in repos if repo.get("dirty"))
        behind_count = sum(1 for repo in repos if int(repo.get("behind") or 0) > 0)
        cloned_count = sum(1 for repo in repos if repo.get("exists"))
        command_count = 0
        for repo in repos:
            for specs in (repo.get("commands") or {}).values():
                if isinstance(specs, list):
                    command_count += len(specs)
        return {
            "generated_at": now_iso(),
            "repo_count": len(repos),
            "cloned_count": cloned_count,
            "dirty_count": dirty_count,
            "behind_count": behind_count,
            "command_count": command_count,
            "tiers": tiers,
            "statuses": statuses,
            "languages": languages,
            "clone_statuses": clone_statuses,
            "config_statuses": config_statuses,
            "deploy_statuses": deploy_statuses,
            "start_statuses": start_statuses,
            "dry_run_statuses": dry_run_statuses,
        }

    def report_markdown(self) -> str:
        summary = self.summary()
        repos = [self._decorate_repo(repo) for repo in self.store.list_repos()]
        core_rows = [repo for repo in repos if repo.get("tier") == "core"]
        stale_rows = [repo for repo in repos if repo.get("tier") == "stale"]
        alert_rows = [
            repo
            for repo in repos
            if repo.get("validation_status") in {"blocked", "failed", "missing", "warn"}
        ]
        deployment_gate_rows = [
            repo
            for repo in repos
            if self._configured_playbook(str(repo["name"]), "deploy")
            or self._detected_profile_count(repo, "deploy")
            or repo.get("deploy_status") in {"deploy_ready", "deploy_executed"}
        ]
        unconfigured_rows = [repo for repo in repos if repo.get("config_status") == "unconfigured"]
        playbook_rows = [
            repo
            for repo in repos
            if repo.get("playbook_profiles") or repo.get("detected_profile_count")
        ]
        lines = [
            "# Coasys Repository Operations Report",
            "",
            f"Generated: {summary['generated_at']}",
            "",
            "## Summary",
            "",
            f"- Repositories: {summary['repo_count']}",
            f"- Cloned locally: {summary['cloned_count']}",
            f"- Dirty checkouts: {summary['dirty_count']}",
            f"- Behind remote: {summary['behind_count']}",
            f"- Detected commands: {summary['command_count']}",
            "",
            "## Tiers",
            "",
            "| Tier | Count |",
            "| --- | ---: |",
        ]
        lines.extend(self._markdown_count_rows(summary["tiers"]))
        lines.extend(["", "## Validation Statuses", "", "| Status | Count |", "| --- | ---: |"])
        lines.extend(self._markdown_count_rows(summary["statuses"]))
        lines.extend(["", "## Clone Statuses", "", "| Status | Count |", "| --- | ---: |"])
        lines.extend(self._markdown_count_rows(summary["clone_statuses"]))
        lines.extend(["", "## Configuration Statuses", "", "| Status | Count |", "| --- | ---: |"])
        lines.extend(self._markdown_count_rows(summary["config_statuses"]))
        lines.extend(["", "## Start Statuses", "", "| Status | Count |", "| --- | ---: |"])
        lines.extend(self._markdown_count_rows(summary["start_statuses"]))
        lines.extend(["", "## Dry Run Statuses", "", "| Status | Count |", "| --- | ---: |"])
        lines.extend(self._markdown_count_rows(summary["dry_run_statuses"]))
        lines.extend(["", "## Deployment Readiness", "", "| Status | Count |", "| --- | ---: |"])
        lines.extend(self._markdown_count_rows(summary["deploy_statuses"]))
        lines.extend(
            [
                "",
                "## Playbook Coverage",
                "",
                "| Repo | Tier | Config | Playbooks | Missing env | Next action |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        lines.extend(self._markdown_playbook_rows(playbook_rows))
        lines.extend(
            [
                "",
                "## Validation Alerts",
                "",
                "| Repo | Tier | Status | Reason |",
                "| --- | --- | --- | --- |",
            ]
        )
        lines.extend(self._markdown_alert_rows(alert_rows))
        lines.extend(
            [
                "",
                "## Deployment Gates",
                "",
                "| Repo | Tier | Status | Configured | Detected | Missing env | Reason |",
                "| --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        lines.extend(self._markdown_deployment_gate_rows(deployment_gate_rows))
        lines.extend(
            [
                "",
                "## Unconfigured Repositories",
                "",
                "| Repo | Tier | Stack |",
                "| --- | --- | --- |",
            ]
        )
        lines.extend(self._markdown_unconfigured_rows(unconfigured_rows))
        lines.extend(["", "## Core Repositories", "", "| Repo | Status | Branch | Updated |"])
        lines.append("| --- | --- | --- | --- |")
        lines.extend(self._markdown_repo_rows(core_rows))
        lines.extend(["", "## Stale Repositories", "", "| Repo | Status | Branch | Updated |"])
        lines.append("| --- | --- | --- | --- |")
        lines.extend(self._markdown_repo_rows(stale_rows[:30]))
        lines.extend(
            [
                "",
                "## Repository Operating Matrix",
                "",
                (
                    "| Repo | Tier | Clone | Config | Validation | Start | Deploy | "
                    "Commands | Stack |"
                ),
                "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
            ]
        )
        lines.extend(self._markdown_operating_rows(repos))
        return "\n".join(lines) + "\n"

    def sync(
        self,
        org: str | None = None,
        clone: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        repos = self.github.list_org_repos(org or self.config.org, limit=limit)
        return self.sync_repos(repos, clone=clone)

    def sync_repo(self, name: str, clone: bool = True) -> dict[str, Any]:
        org = self.config.org
        repos = self.github.list_org_repos(org)
        for repo in repos:
            if repo.name == name:
                return self.sync_repos([repo], clone=clone)[0]
        raise ValueError(f"Repository {name!r} was not found in github.com/{org}")

    def sync_repos(self, repos: list[RepoMetadata], clone: bool = True) -> list[dict[str, Any]]:
        synced: list[dict[str, Any]] = []
        for metadata in repos:
            override = self.config.override_for(metadata.name)
            local_path = self._repo_path(metadata.name)
            last_error = None
            existing = self.store.get_repo(metadata.name)
            if clone:
                result = clone_or_fetch_repo(
                    metadata,
                    local_path,
                    clone_url=override.clone_url,
                    timeout_seconds=self._timeout_for(override),
                    clone_depth=self.config.clone_depth,
                    partial_clone=self.config.partial_clone,
                )
                if not result.ok:
                    last_error = result.output_tail
            snapshot = self._snapshot_for(
                metadata,
                last_error=last_error,
                synced=True,
                existing=existing,
            )
            self.store.upsert_repo(snapshot)
            synced.append(self.store.get_repo(metadata.name) or snapshot.to_dict())
        return synced

    def validate_many(
        self,
        *,
        all_repos: bool = False,
        tier: str | None = None,
        repo_name: str | None = None,
        execute_detected: bool = False,
    ) -> list[dict[str, Any]]:
        if repo_name:
            return [self.validate_repo(repo_name, execute_detected=execute_detected)]
        repos = self.store.list_repos()
        if tier:
            repos = [repo for repo in repos if repo["tier"] == tier]
        elif not all_repos:
            repos = [repo for repo in repos if repo["tier"] == "core"]
        return [
            self.validate_repo(repo["name"], execute_detected=execute_detected)
            for repo in repos
        ]

    def validate_repo(self, name: str, execute_detected: bool = False) -> dict[str, Any]:
        row = self.store.get_repo(name)
        if row is None:
            return self.sync_repo(name, clone=True)

        metadata = self._metadata_from_row(row)
        override = self.config.override_for(name)
        local_path = self._repo_path(name)
        stacks, commands = (
            detect_repo(local_path) if local_path.exists() else ([], self._empty_commands())
        )
        ci_status, ci_conclusion = self._latest_ci(metadata)
        command_specs = self._validation_commands(commands, override, execute_detected)
        missing_env = [
            env_name for env_name in override.env_required if not os.environ.get(env_name)
        ]

        command_failed = False
        command_blocked = False
        if command_specs and missing_env:
            command_blocked = True
        elif command_specs:
            run = self._run_command_batch(
                repo_name=name,
                kind="validation",
                profile="validate",
                commands=[spec["command"] for spec in command_specs],
                timeout_seconds=self._timeout_for(override),
                cwd=local_path,
            )
            command_failed = run["status"] == "failed"

        snapshot = self._snapshot_for(
            metadata,
            stacks=stacks,
            commands=commands,
            ci_status=ci_status,
            ci_conclusion=ci_conclusion,
            validated=True,
            existing=row,
        )
        snapshot.validation_status = self._validation_status(
            snapshot=snapshot,
            command_failed=command_failed,
            command_blocked=command_blocked,
            missing_env=missing_env,
        )
        if missing_env:
            snapshot.last_error = f"Missing required environment: {', '.join(missing_env)}"
        self.store.upsert_repo(snapshot)
        return self.store.get_repo(name) or snapshot.to_dict()

    def run_profile(
        self,
        name: str,
        profile: str,
        *,
        dry_run: bool = False,
        execute: bool = False,
    ) -> dict[str, Any]:
        if dry_run and execute:
            raise ValueError("--dry-run and --execute are mutually exclusive")
        row = self.store.get_repo(name)
        if row is None:
            raise ValueError(f"Repository {name!r} has not been synced")

        override = self.config.override_for(name)
        local_path = self._repo_path(name)
        if not local_path.exists():
            raise ValueError(f"Repository {name!r} is not cloned at {local_path}")

        gated_profile = profile in {"start", "dev", "serve", "deploy", "release"}
        playbook = self._configured_playbook(name, profile)
        if gated_profile and not playbook:
            raise ValueError(
                f"Profile {profile!r} requires an explicit playbook in coasys.yml"
            )
        if gated_profile and not dry_run and not execute:
            raise ValueError(f"Profile {profile!r} requires --dry-run or --execute")
        if profile in {"deploy", "release"} and execute and not self._last_profile_status(
            name, "deploy", "dry_run_passed"
        ):
            raise ValueError("Deploy execution requires a passing dry run")

        commands = (
            self._configured_profile_commands(name, profile, dry_run=dry_run)
            if playbook
            else self._profile_commands(profile, override, local_path)
        )
        if not commands:
            raise ValueError(f"No runnable profile {profile!r} is configured for {name!r}")

        missing_env = self._missing_env_for(name, profile)
        if missing_env and execute:
            raise ValueError(f"Missing required environment: {', '.join(missing_env)}")

        success_status = "passed"
        failure_status = "failed"
        kind = "profile"
        if dry_run:
            success_status = "dry_run_passed"
            failure_status = "dry_run_failed"
            kind = "dry-run"
        elif profile in {"deploy", "release"} and execute:
            success_status = "deploy_executed"
            failure_status = "failed"
            kind = "deployment"
        elif profile in {"start", "dev", "serve"} and execute:
            success_status = "start_passed"
            failure_status = "failed"

        canonical_profile = profile
        if profile == "release":
            canonical_profile = "deploy"
        elif profile in {"dev", "serve"}:
            canonical_profile = "start"
        return self._run_command_batch(
            repo_name=name,
            kind=kind,
            profile=canonical_profile,
            commands=commands,
            timeout_seconds=self._timeout_for_profile(name, profile, override),
            cwd=self._profile_cwd(name, profile, local_path),
            success_status=success_status,
            failure_status=failure_status,
        )

    def _repo_path(self, name: str) -> Path:
        return self.config.workspace.repos_dir / name

    def _timeout_for(self, override: RepoOverride) -> int:
        return int(override.timeout_seconds or self.config.default_timeout_seconds)

    @staticmethod
    def _count_values(values: object) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:  # type: ignore[union-attr]
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _markdown_count_rows(counts: dict[str, int]) -> list[str]:
        return [f"| {name} | {count} |" for name, count in sorted(counts.items())]

    @staticmethod
    def _markdown_repo_rows(repos: list[dict[str, Any]]) -> list[str]:
        if not repos:
            return ["| none |  |  |  |"]
        return [
            "| {name} | {status} | {branch} | {updated} |".format(
                name=repo["name"],
                status=repo.get("validation_status") or "unknown",
                branch=repo.get("branch") or repo.get("default_branch") or "",
                updated=repo.get("updated_at") or "",
            )
            for repo in repos
        ]

    @staticmethod
    def _markdown_escape(value: object) -> str:
        return str(value or "").replace("|", "\\|").replace("\n", " ")

    def _markdown_alert_rows(self, repos: list[dict[str, Any]]) -> list[str]:
        if not repos:
            return ["| none |  |  |  |"]
        return [
            "| {name} | {tier} | {status} | {reason} |".format(
                name=self._markdown_escape(repo["name"]),
                tier=self._markdown_escape(repo.get("tier")),
                status=self._markdown_escape(repo.get("validation_status") or "unknown"),
                reason=self._markdown_escape(repo.get("last_error") or ""),
            )
            for repo in repos
        ]

    def _markdown_deployment_gate_rows(self, repos: list[dict[str, Any]]) -> list[str]:
        if not repos:
            return ["| none |  |  |  |  |  |  |"]
        return [
            (
                "| {name} | {tier} | {status} | {configured} | {detected} | "
                "{missing} | {reason} |"
            ).format(
                name=self._markdown_escape(repo["name"]),
                tier=self._markdown_escape(repo.get("tier")),
                status=self._markdown_escape(repo.get("deploy_status")),
                configured=int(repo.get("deploy_command_count") or 0),
                detected=self._detected_profile_count(repo, "deploy"),
                missing=self._markdown_escape(", ".join(repo.get("missing_env") or []) or "none"),
                reason=self._markdown_escape(repo.get("deploy_reason")),
            )
            for repo in repos
        ]

    def _markdown_unconfigured_rows(self, repos: list[dict[str, Any]]) -> list[str]:
        if not repos:
            return ["| none |  |  |"]
        return [
            "| {name} | {tier} | {stack} |".format(
                name=self._markdown_escape(repo["name"]),
                tier=self._markdown_escape(repo.get("tier")),
                stack=self._markdown_escape(", ".join(repo.get("stacks") or []) or "none"),
            )
            for repo in repos
        ]

    def _markdown_playbook_rows(self, repos: list[dict[str, Any]]) -> list[str]:
        if not repos:
            return ["| none |  |  |  |  |  |"]
        return [
            "| {name} | {tier} | {config} | {playbooks} | {missing} | {next_action} |".format(
                name=self._markdown_escape(repo["name"]),
                tier=self._markdown_escape(repo.get("tier")),
                config=self._markdown_escape(repo.get("config_status")),
                playbooks=self._markdown_escape(", ".join(repo.get("playbook_profiles") or [])),
                missing=self._markdown_escape(", ".join(repo.get("missing_env") or []) or "none"),
                next_action=self._markdown_escape(repo.get("next_action")),
            )
            for repo in repos
        ]

    def _markdown_operating_rows(self, repos: list[dict[str, Any]]) -> list[str]:
        if not repos:
            return ["| none |  |  |  |  |  |  |  |  |"]
        return [
            (
                "| {name} | {tier} | {clone} | {config} | {validation} | {start} | "
                "{deploy} | {commands} | {stack} |"
            ).format(
                name=self._markdown_escape(repo["name"]),
                tier=self._markdown_escape(repo.get("tier")),
                clone=self._markdown_escape(repo.get("clone_status")),
                config=self._markdown_escape(repo.get("config_status")),
                validation=self._markdown_escape(repo.get("validation_status") or "unknown"),
                start=self._markdown_escape(repo.get("start_status")),
                deploy=self._markdown_escape(repo.get("deploy_status")),
                commands=int(repo.get("configured_command_count") or 0),
                stack=self._markdown_escape(", ".join(repo.get("stacks") or []) or "none"),
            )
            for repo in repos
        ]

    @staticmethod
    def _clone_status(repo: dict[str, Any]) -> str:
        return "cloned" if repo.get("exists") else "missing"

    def _config_status(self, repo: dict[str, Any]) -> str:
        if not repo.get("exists"):
            return "pending"
        if repo.get("playbook_profiles") or self._playbook_profiles(str(repo["name"])):
            return "configured"
        commands = repo.get("commands") or {}
        command_count = sum(len(specs) for specs in commands.values() if isinstance(specs, list))
        if command_count or repo.get("stacks"):
            return "detected"
        return "unconfigured"

    def _deploy_status(self, repo: dict[str, Any]) -> str:
        repo_name = str(repo["name"])
        if self._last_profile_status(repo_name, "deploy", "deploy_executed"):
            return "deploy_executed"
        if not repo.get("exists"):
            return "deploy_blocked"
        if not self._configured_playbook(repo_name, "deploy"):
            if self._detected_profile_count(repo, "deploy"):
                return "detected"
            return "deploy_blocked"
        if self._missing_env_for(repo_name, "deploy"):
            return "deploy_blocked"
        if self._last_profile_status(repo_name, "deploy", "dry_run_passed"):
            return "deploy_ready"
        return "configured"

    def _start_status(self, repo: dict[str, Any]) -> str:
        repo_name = str(repo["name"])
        if self._last_profile_status(repo_name, "start", "start_passed"):
            return "start_passed"
        if self._last_profile_status(repo_name, "start", "dry_run_passed"):
            return "dry_run_passed"
        if self._configured_playbook(repo_name, "start"):
            return "configured"
        if self._detected_profile_count(repo, "start"):
            return "detected"
        return "blocked"

    def _dry_run_status(self, repo: dict[str, Any]) -> str:
        repo_name = str(repo["name"])
        latest = self._latest_dry_run(repo_name)
        if latest:
            return str(latest["status"])
        if self._playbook_profiles(repo_name):
            return "configured"
        return "none"

    def _deploy_reason(self, repo: dict[str, Any]) -> str:
        repo_name = str(repo["name"])
        if self._last_profile_status(repo_name, "deploy", "deploy_executed"):
            return "deploy profile executed successfully"
        if not repo.get("exists"):
            return "repository is not cloned locally"
        if not self._configured_playbook(repo_name, "deploy"):
            if self._detected_profile_count(repo, "deploy"):
                return "deploy script detected but blocked until copied into coasys.yml"
            return "no deploy playbook configured"
        missing_env = self._missing_env_for(repo_name, "deploy")
        if missing_env:
            return f"missing required environment: {', '.join(missing_env)}"
        if self._last_profile_status(repo_name, "deploy", "dry_run_passed"):
            return "deploy dry run passed; explicit execution is still required"
        if self._configured_playbook(repo_name, "deploy"):
            return "deploy playbook configured; run a dry run before execution"
        if not repo.get("exists"):
            return "repository is not cloned locally"
        return "no deploy playbook configured"

    def _decorate_repo(self, repo: dict[str, Any]) -> dict[str, Any]:
        decorated = dict(repo)
        commands = decorated.get("commands") or {}
        configured_command_count = sum(
            len(specs) for specs in commands.values() if isinstance(specs, list)
        )
        repo_name = str(decorated["name"])
        deploy_command_count = len(self._configured_profile_commands(repo_name, "deploy"))
        detected_profile_count = sum(
            self._detected_profile_count(decorated, profile)
            for profile in ("validation", "build", "start", "deploy")
        )
        decorated["clone_status"] = self._clone_status(decorated)
        decorated["playbook_profiles"] = self._playbook_profiles(repo_name)
        decorated["missing_env"] = self._missing_env_for(repo_name)
        decorated["config_status"] = self._config_status(decorated)
        decorated["start_status"] = self._start_status(decorated)
        decorated["deploy_status"] = self._deploy_status(decorated)
        decorated["deploy_reason"] = self._deploy_reason(decorated)
        decorated["next_action"] = self._next_action(decorated)
        decorated["configured_command_count"] = configured_command_count
        decorated["deploy_command_count"] = deploy_command_count
        decorated["detected_profile_count"] = detected_profile_count
        return decorated

    def _latest_run_for_profile(self, repo_name: str, profile: str) -> dict[str, Any] | None:
        for run in self.store.list_runs(limit=500):
            if run["repo_name"] == repo_name and run["profile"] == profile:
                return run
        return None

    def _latest_dry_run(self, repo_name: str) -> dict[str, Any] | None:
        for run in self.store.list_runs(limit=500):
            if run["repo_name"] == repo_name and run["status"].startswith("dry_run_"):
                return run
        return None

    def _last_profile_status(self, repo_name: str, profile: str, status: str) -> bool:
        run = self._latest_run_for_profile(repo_name, profile)
        return bool(run and run["status"] == status)

    def _snapshot_for(
        self,
        metadata: RepoMetadata,
        *,
        stacks: list[str] | None = None,
        commands: dict[str, list[dict[str, Any]]] | None = None,
        ci_status: str | None = None,
        ci_conclusion: str | None = None,
        last_error: str | None = None,
        synced: bool = False,
        validated: bool = False,
        existing: dict[str, Any] | None = None,
    ) -> RepoSnapshot:
        local_path = self._repo_path(metadata.name)
        git_state = inspect_git_checkout(local_path, metadata.default_branch)
        if stacks is None or commands is None:
            stacks, commands = (
                detect_repo(local_path)
                if local_path.exists()
                else ([], self._empty_commands())
            )
        override = self.config.override_for(metadata.name)
        snapshot = RepoSnapshot(
            metadata=metadata,
            tier=classify_repo(metadata, override),
            local_path=local_path,
            exists=bool(git_state.get("exists", False)),
            branch=git_state.get("branch") if isinstance(git_state.get("branch"), str) else None,
            local_head=git_state.get("local_head")
            if isinstance(git_state.get("local_head"), str)
            else None,
            remote_head=git_state.get("remote_head")
            if isinstance(git_state.get("remote_head"), str)
            else None,
            dirty=bool(git_state.get("dirty", False)),
            ahead=int(git_state.get("ahead", 0) or 0),
            behind=int(git_state.get("behind", 0) or 0),
            stacks=stacks,
            commands=self._merge_configured_commands(commands, override),
            ci_status=ci_status,
            ci_conclusion=ci_conclusion,
            last_error=last_error or self._git_error(git_state),
            last_synced_at=now_iso() if synced else self._existing_text(existing, "last_synced_at"),
            last_validated_at=now_iso()
            if validated
            else self._existing_text(existing, "last_validated_at"),
        )
        snapshot.validation_status = self._existing_text(existing, "validation_status")
        return snapshot

    @staticmethod
    def _empty_commands() -> dict[str, list[dict[str, Any]]]:
        return {"validation": [], "build": [], "start": [], "deploy": []}

    def _merge_configured_commands(
        self,
        commands: dict[str, list[dict[str, Any]]],
        override: RepoOverride,
    ) -> dict[str, list[dict[str, Any]]]:
        merged = {key: list(value) for key, value in commands.items()}
        for command in override.validation_commands:
            merged.setdefault("validation", []).append(
                {
                    "name": command,
                    "command": shlex.split(command),
                    "kind": "validation",
                    "source": "coasys.yml",
                    "automatic": True,
                }
            )
        for profile, profile_commands in override.profiles.items():
            merged.setdefault("profiles", [])
            for command in profile_commands:
                merged["profiles"].append(
                    {
                        "name": profile,
                        "command": shlex.split(command),
                        "kind": "profile",
                        "source": "coasys.yml",
                        "configured": True,
                        "automatic": False,
                    }
                )
        for profile, playbook in override.playbooks.items():
            command_group = self._command_group_for_profile(profile)
            merged.setdefault(command_group, [])
            for index, command in enumerate(playbook.commands, start=1):
                merged[command_group].append(
                    {
                        "name": f"{profile}:{index}",
                        "command": shlex.split(command),
                        "kind": profile,
                        "source": "coasys.yml",
                        "configured": True,
                        "automatic": playbook.automatic,
                        "working_dir": playbook.working_dir,
                        "env_required": list(playbook.env_required),
                    }
                )
        return merged

    @staticmethod
    def _command_group_for_profile(profile: str) -> str:
        if profile in {"validate", "validation", "test"}:
            return "validation"
        if profile == "build":
            return "build"
        if profile in {"start", "dev", "serve"}:
            return "start"
        if profile in {"deploy", "release"}:
            return "deploy"
        return "profiles"

    def _validation_commands(
        self,
        commands: dict[str, list[dict[str, Any]]],
        override: RepoOverride,
        execute_detected: bool,
    ) -> list[dict[str, Any]]:
        if override.do_not_run_automatically:
            return []
        should_execute_detected = (
            execute_detected
            or self.config.execute_detected_validation
            or bool(override.execute_detected_validation)
        )
        selected: list[dict[str, Any]] = []
        for spec in commands.get("validation", []):
            if spec.get("source") == "coasys.yml" and spec.get("automatic"):
                selected.append(spec)
            elif spec.get("automatic") or should_execute_detected:
                selected.append(spec)
        return selected

    def _profile_commands(
        self,
        profile: str,
        override: RepoOverride,
        local_path: Path,
    ) -> list[list[str]]:
        if profile in override.profiles:
            return [shlex.split(command) for command in override.profiles[profile]]

        _stacks, detected = detect_repo(local_path)
        if profile in {"validate", "validation", "test"}:
            return [spec["command"] for spec in detected.get("validation", [])]
        if profile == "build":
            return [spec["command"] for spec in detected.get("build", [])]
        if profile in {"start", "dev", "serve"}:
            return [spec["command"] for spec in detected.get("start", [])]
        if profile in {"deploy", "release"}:
            return [spec["command"] for spec in detected.get("deploy", [])]
        return []

    def _configured_playbook(self, repo_name: str, profile: str) -> OperationPlaybook | None:
        override = self.config.override_for(repo_name)
        if profile in override.playbooks:
            return override.playbooks[profile]
        if profile in override.profiles:
            return OperationPlaybook(commands=override.profiles[profile])
        return None

    def _playbook_profiles(self, repo_name: str) -> list[str]:
        override = self.config.override_for(repo_name)
        profiles = {*override.playbooks.keys(), *override.profiles.keys()}
        if override.validation_commands:
            profiles.add("validation")
        return sorted(profiles)

    def _configured_profile_commands(
        self,
        repo_name: str,
        profile: str,
        *,
        dry_run: bool = False,
    ) -> list[list[str]]:
        playbook = self._configured_playbook(repo_name, profile)
        if not playbook:
            return []
        commands = playbook.dry_run_commands if dry_run else playbook.commands
        if dry_run and not commands:
            commands = ["git status --short"]
        return [shlex.split(command) for command in commands]

    def _profile_cwd(self, repo_name: str, profile: str, local_path: Path) -> Path:
        playbook = self._configured_playbook(repo_name, profile)
        if not playbook or not playbook.working_dir:
            return local_path
        cwd = (local_path / playbook.working_dir).resolve()
        root = local_path.resolve()
        if root not in [cwd, *cwd.parents]:
            raise ValueError(f"Configured working_dir escapes repository: {playbook.working_dir}")
        return cwd

    def _timeout_for_profile(self, repo_name: str, profile: str, override: RepoOverride) -> int:
        playbook = self._configured_playbook(repo_name, profile)
        if playbook and playbook.timeout_seconds:
            return int(playbook.timeout_seconds)
        return self._timeout_for(override)

    def _missing_env_for(self, repo_name: str, profile: str | None = None) -> list[str]:
        override = self.config.override_for(repo_name)
        required = list(override.env_required)
        if profile:
            playbook = self._configured_playbook(repo_name, profile)
            if playbook:
                required.extend(playbook.env_required)
        else:
            for playbook in override.playbooks.values():
                required.extend(playbook.env_required)
        return sorted({env_name for env_name in required if not os.environ.get(env_name)})

    @staticmethod
    def _detected_profile_count(repo: dict[str, Any], profile: str) -> int:
        commands = repo.get("commands") or {}
        group = "validation" if profile in {"validate", "test"} else profile
        specs = commands.get(group) or []
        return sum(1 for spec in specs if spec.get("source") != "coasys.yml")

    def _next_action(self, repo: dict[str, Any]) -> str:
        if not repo.get("exists"):
            return "sync repository"
        if repo.get("validation_status") in {None, "missing", "failed", "blocked", "warn"}:
            return "inspect validation"
        if repo.get("deploy_status") == "deploy_blocked" and self._configured_playbook(
            str(repo["name"]), "deploy"
        ):
            return "provide deploy env or keep blocked"
        if repo.get("deploy_status") == "configured":
            return "run deploy dry run"
        if repo.get("deploy_status") == "deploy_ready":
            return "execute deploy only if intended"
        if repo.get("start_status") == "configured":
            return "run start dry run"
        if repo.get("config_status") == "detected":
            return "promote detected commands into playbook"
        return "monitor"

    def _run_command_batch(
        self,
        *,
        repo_name: str,
        kind: str,
        profile: str,
        commands: list[list[str]],
        timeout_seconds: int,
        cwd: Path,
        success_status: str = "passed",
        failure_status: str = "failed",
    ) -> dict[str, Any]:
        run_id = self.store.create_run(repo_name, kind, profile, commands)
        output_parts: list[str] = []
        exit_code = 0
        failed = False
        for command in commands:
            result = run_command(command, cwd=cwd, timeout_seconds=timeout_seconds)
            output_parts.append(f"$ {' '.join(command)}\n{result.output_tail}")
            if not result.ok:
                failed = True
                exit_code = result.exit_code
                break
        output_tail = "\n\n".join(output_parts)[-20000:]
        log_path = self._write_run_log(run_id, output_tail)
        self.store.finish_run(
            run_id=run_id,
            status=failure_status if failed else success_status,
            exit_code=exit_code,
            output_tail=output_tail,
            log_path=str(log_path),
        )
        run = self.store.get_run(run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} disappeared")
        return run

    def _write_run_log(self, run_id: int, output: str) -> Path:
        log_path = self.config.workspace.state_dir / "logs" / f"run-{run_id}.log"
        log_path.write_text(output, encoding="utf-8")
        return log_path

    def _latest_ci(self, metadata: RepoMetadata) -> tuple[str | None, str | None]:
        try:
            run = self.github.latest_workflow_run(metadata.full_name, metadata.default_branch)
        except Exception as exc:  # CI metadata is helpful, not load-bearing.
            return "unavailable", exc.__class__.__name__
        if not run:
            return None, None
        return run.get("status"), run.get("conclusion")

    @staticmethod
    def _validation_status(
        *,
        snapshot: RepoSnapshot,
        command_failed: bool,
        command_blocked: bool,
        missing_env: list[str],
    ) -> str:
        if not snapshot.exists:
            return "missing"
        if command_failed:
            return "failed"
        if command_blocked or missing_env:
            return "blocked"
        if snapshot.dirty or snapshot.ahead or snapshot.behind:
            return "warn"
        successful_conclusions = {"success", "neutral", "skipped"}
        if snapshot.ci_conclusion and snapshot.ci_conclusion not in successful_conclusions:
            return "warn"
        return "passed"

    @staticmethod
    def _git_error(git_state: dict[str, object]) -> str | None:
        value = git_state.get("last_error")
        return value if isinstance(value, str) else None

    @staticmethod
    def _existing_text(existing: dict[str, Any] | None, key: str) -> str | None:
        if not existing:
            return None
        value = existing.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _metadata_from_row(row: dict[str, Any]) -> RepoMetadata:
        return RepoMetadata(
            name=row["name"],
            full_name=row["full_name"],
            description=row["description"],
            html_url=row["html_url"],
            clone_url=row["clone_url"],
            ssh_url=row["ssh_url"],
            default_branch=row["default_branch"],
            visibility=row["visibility"],
            language=row.get("language"),
            stars=int(row["stars"]),
            forks=int(row["forks"]),
            open_issues=int(row["open_issues"]),
            updated_at=row.get("updated_at"),
            pushed_at=row.get("pushed_at"),
            archived=bool(row["archived"]),
            raw=row.get("raw") or {},
        )
