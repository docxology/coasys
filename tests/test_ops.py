from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from conftest import make_repo_metadata

from coasys_ops.config import OperationPlaybook, RepoOverride
from coasys_ops.github_api import GitHubClient
from coasys_ops.models import CommandResult, RepoSnapshot, now_iso
from coasys_ops.ops import CoasysOps


class FakeGitHub(GitHubClient):
    def __init__(self, repos: list[Any]) -> None:
        self.repos = repos

    def list_org_repos(self, org: str, limit: int | None = None) -> list[Any]:
        return self.repos[:limit] if limit else self.repos

    def latest_workflow_run(
        self, full_name: str, branch: str | None = None
    ) -> dict[str, Any] | None:
        return {"status": "completed", "conclusion": "success"}


def _git(command: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *command],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_sync_clones_local_git_repo(app_config, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    remote = tmp_path / "remote-demo"
    remote.mkdir()
    _git(["init", "-b", "main"], remote)
    _git(["config", "user.email", "test@example.com"], remote)
    _git(["config", "user.name", "Test"], remote)
    (remote / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(["add", "README.md"], remote)
    _git(["commit", "-m", "initial"], remote)

    metadata = make_repo_metadata("demo", clone_url=str(remote))
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))

    synced = ops.sync_repos([metadata], clone=True)

    assert synced[0]["name"] == "demo"
    assert synced[0]["exists"] is True
    assert (app_config.workspace.repos_dir / "demo" / "README.md").exists()


def test_sync_uses_shallow_partial_clone_by_default(app_config, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    remote = tmp_path / "remote-shallow"
    remote.mkdir()
    _git(["init", "-b", "main"], remote)
    _git(["config", "user.email", "test@example.com"], remote)
    _git(["config", "user.name", "Test"], remote)
    (remote / "README.md").write_text("# one\n", encoding="utf-8")
    _git(["add", "README.md"], remote)
    _git(["commit", "-m", "one"], remote)
    (remote / "README.md").write_text("# two\n", encoding="utf-8")
    _git(["commit", "-am", "two"], remote)

    metadata = make_repo_metadata("shallow", clone_url=remote.resolve().as_uri())
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))

    ops.sync_repos([metadata], clone=True)

    clone = app_config.workspace.repos_dir / "shallow"
    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"],
        cwd=clone,
        text=True,
        capture_output=True,
        check=True,
    )
    assert count.stdout.strip() == "1"


def test_validate_detects_missing_clone(app_config) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.sync_repos([metadata], clone=False)

    result = ops.validate_repo("demo")

    assert result["validation_status"] == "missing"
    assert result["ci_conclusion"] == "success"


def test_summary_and_markdown_report_include_tiers_and_statuses(app_config) -> None:  # type: ignore[no-untyped-def]
    repos = [
        make_repo_metadata("ad4m"),
        make_repo_metadata("matrix-link-language"),
    ]
    ops = CoasysOps(config=app_config, github=FakeGitHub(repos))
    ops.sync_repos(repos, clone=False)
    ops.validate_repo("ad4m")

    summary = ops.summary()
    report = ops.report_markdown()

    assert summary["repo_count"] == 2
    assert summary["tiers"]["core"] == 1
    assert summary["tiers"]["language"] == 1
    assert summary["statuses"]["missing"] == 1
    assert "# Coasys Repository Operations Report" in report
    assert "| core | 1 |" in report
    assert "| missing | 1 |" in report
    assert "## Repository Operating Matrix" in report
    assert (
        "| ad4m | core | missing | pending | missing | blocked | deploy_blocked | 0 | none |"
        in report
    )


def test_operate_fleet_reports_clone_config_validate_and_deploy_readiness(app_config) -> None:  # type: ignore[no-untyped-def]
    repos = [
        make_repo_metadata("ad4m"),
        make_repo_metadata("matrix-link-language"),
    ]
    ops = CoasysOps(config=app_config, github=FakeGitHub(repos))

    result = ops.operate_fleet(clone=False, validate=True, deploy=False)
    summary = ops.summary()

    assert result["repo_count"] == 2
    assert result["validated_count"] == 2
    assert result["deployed_count"] == 0
    assert summary["clone_statuses"]["missing"] == 2
    assert summary["config_statuses"]["pending"] == 2
    assert summary["deploy_statuses"]["deploy_blocked"] == 2
    assert "## Deployment Readiness" in ops.report_markdown()


def test_repo_rows_include_operating_statuses(app_config) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.sync_repos([metadata], clone=False)

    repo = ops.list_repos()[0]

    assert repo["clone_status"] == "missing"
    assert repo["config_status"] == "pending"
    assert repo["deploy_status"] == "deploy_blocked"
    assert repo["deploy_command_count"] == 0
    assert "not cloned" in repo["deploy_reason"]


def test_run_profile_blocks_detected_deploy_without_configured_playbook(app_config) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    local_path = app_config.workspace.repos_dir / "demo"
    local_path.mkdir(parents=True)
    (local_path / "Makefile").write_text("deploy:\n\t@echo deploy\n", encoding="utf-8")
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.store.upsert_repo(
        RepoSnapshot(
            metadata=metadata,
            tier="active",
            local_path=local_path,
            exists=True,
            commands={"validation": [], "build": [], "start": [], "deploy": []},
            validation_status="passed",
        )
    )

    with pytest.raises(ValueError, match="explicit playbook"):
        ops.run_profile("demo", "deploy", dry_run=True)


def test_run_profile_dry_run_uses_configured_playbook_commands(app_config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    local_path = app_config.workspace.repos_dir / "demo"
    local_path.mkdir(parents=True)
    (local_path / "Makefile").write_text("deploy:\n\t@echo detected\n", encoding="utf-8")
    app_config.repos["demo"] = RepoOverride(
        playbooks={
            "deploy": OperationPlaybook(
                commands=["echo configured-deploy"],
                dry_run_commands=["echo dry-run-deploy"],
            )
        }
    )
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.store.upsert_repo(
        RepoSnapshot(
            metadata=metadata,
            tier="active",
            local_path=local_path,
            exists=True,
            commands={"validation": [], "build": [], "start": [], "deploy": []},
            validation_status="passed",
        )
    )
    seen: list[list[str]] = []

    def fake_run_command(command, cwd, timeout_seconds):  # type: ignore[no-untyped-def]
        seen.append(command)
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout="ok\n",
            stderr="",
            started_at=now_iso(),
            finished_at=now_iso(),
        )

    monkeypatch.setattr("coasys_ops.ops.run_command", fake_run_command)

    run = ops.run_profile("demo", "deploy", dry_run=True)

    assert run["status"] == "dry_run_passed"
    assert run["commands"] == [["echo", "dry-run-deploy"]]
    assert seen == [["echo", "dry-run-deploy"]]
    repo = ops.get_repo("demo")
    assert repo is not None
    assert repo["deploy_status"] == "deploy_ready"


def test_execute_deploy_requires_passing_dry_run(app_config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    local_path = app_config.workspace.repos_dir / "demo"
    local_path.mkdir(parents=True)
    app_config.repos["demo"] = RepoOverride(
        playbooks={
            "deploy": OperationPlaybook(
                commands=["echo deploy"],
                dry_run_commands=["echo dry-run"],
            )
        }
    )
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.store.upsert_repo(
        RepoSnapshot(
            metadata=metadata,
            tier="active",
            local_path=local_path,
            exists=True,
            commands={"validation": [], "build": [], "start": [], "deploy": []},
            validation_status="passed",
        )
    )

    def fake_run_command(command, cwd, timeout_seconds):  # type: ignore[no-untyped-def]
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout="ok\n",
            stderr="",
            started_at=now_iso(),
            finished_at=now_iso(),
        )

    monkeypatch.setattr("coasys_ops.ops.run_command", fake_run_command)

    with pytest.raises(ValueError, match="passing dry run"):
        ops.run_profile("demo", "deploy", execute=True)

    dry_run = ops.run_profile("demo", "deploy", dry_run=True)
    deploy = ops.run_profile("demo", "deploy", execute=True)

    assert dry_run["status"] == "dry_run_passed"
    assert deploy["status"] == "deploy_executed"
    repo = ops.get_repo("demo")
    assert repo is not None
    assert repo["deploy_status"] == "deploy_executed"


def test_configured_start_dry_run_records_start_status(app_config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    local_path = app_config.workspace.repos_dir / "demo"
    local_path.mkdir(parents=True)
    app_config.repos["demo"] = RepoOverride(
        playbooks={
            "start": OperationPlaybook(
                commands=["npm run start"],
                dry_run_commands=["echo start-ready"],
            )
        }
    )
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.store.upsert_repo(
        RepoSnapshot(
            metadata=metadata,
            tier="active",
            local_path=local_path,
            exists=True,
            commands={"validation": [], "build": [], "start": [], "deploy": []},
            validation_status="passed",
        )
    )

    def fake_run_command(command, cwd, timeout_seconds):  # type: ignore[no-untyped-def]
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=0,
            stdout="ready\n",
            stderr="",
            started_at=now_iso(),
            finished_at=now_iso(),
        )

    monkeypatch.setattr("coasys_ops.ops.run_command", fake_run_command)

    run = ops.run_profile("demo", "start", dry_run=True)

    assert run["status"] == "dry_run_passed"
    repo = ops.get_repo("demo")
    assert repo is not None
    assert repo["start_status"] == "dry_run_passed"
    assert "## Playbook Coverage" in ops.report_markdown()


def test_validation_playbook_respects_automatic_flag(app_config, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    metadata = make_repo_metadata("demo")
    local_path = app_config.workspace.repos_dir / "demo"
    local_path.mkdir(parents=True)
    app_config.repos["demo"] = RepoOverride(
        playbooks={
            "validate": OperationPlaybook(
                commands=["echo should-not-run"],
                automatic=False,
            )
        }
    )
    ops = CoasysOps(config=app_config, github=FakeGitHub([metadata]))
    ops.store.upsert_repo(
        RepoSnapshot(
            metadata=metadata,
            tier="active",
            local_path=local_path,
            exists=True,
            commands={"validation": [], "build": [], "start": [], "deploy": []},
        )
    )

    def fail_if_called(command, cwd, timeout_seconds):  # type: ignore[no-untyped-def]
        raise AssertionError(command)

    monkeypatch.setattr("coasys_ops.ops.run_command", fail_if_called)

    result = ops.validate_repo("demo")

    assert result["validation_status"] == "passed"
