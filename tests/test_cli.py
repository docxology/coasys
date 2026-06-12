from __future__ import annotations

from pathlib import Path

from conftest import make_repo_metadata
from typer.testing import CliRunner

from coasys_ops.cli import app
from coasys_ops.config import AppConfig, WorkspaceConfig
from coasys_ops.models import RepoSnapshot
from coasys_ops.store import Store


def test_cli_status_and_report_commands(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "coasys.yml").write_text(
        "org: coasys\nworkspace:\n  repos_dir: workspace/repos\n  state_dir: workspace/state\n",
        encoding="utf-8",
    )
    config = AppConfig(
        root=tmp_path,
        org="coasys",
        workspace=WorkspaceConfig(
            repos_dir=tmp_path / "workspace/repos",
            state_dir=tmp_path / "workspace/state",
        ),
    )
    store = Store(config.workspace.state_dir / "coasys.sqlite3")
    store.upsert_repo(
        RepoSnapshot(
            metadata=make_repo_metadata("demo"),
            tier="active",
            local_path=config.workspace.repos_dir / "demo",
            exists=False,
            validation_status="missing",
        )
    )

    runner = CliRunner()
    status = runner.invoke(app, ["status"])
    report = runner.invoke(app, ["report"])
    operate = runner.invoke(app, ["operate", "--no-clone", "--no-validate"])

    assert status.exit_code == 0
    assert "repositories: 1" in status.output
    assert "missing: 1" in status.output
    assert report.exit_code == 0
    assert "# Coasys Repository Operations Report" in report.output
    assert operate.exit_code == 0
    assert "operated repositories: 1" in operate.output


def test_cli_run_profile_supports_dry_run_and_execute_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    (tmp_path / "coasys.yml").write_text(
        """
org: coasys
workspace:
  repos_dir: workspace/repos
  state_dir: workspace/state
repos:
  demo:
    playbooks:
      start:
        commands:
          - echo start
        dry_run_commands:
          - echo start-ready
""",
        encoding="utf-8",
    )
    repos_dir = tmp_path / "workspace/repos"
    state_dir = tmp_path / "workspace/state"
    local_path = repos_dir / "demo"
    local_path.mkdir(parents=True)
    store = Store(state_dir / "coasys.sqlite3")
    store.upsert_repo(
        RepoSnapshot(
            metadata=make_repo_metadata("demo"),
            tier="active",
            local_path=local_path,
            exists=True,
            validation_status="passed",
        )
    )

    runner = CliRunner()
    dry_run = runner.invoke(app, ["run", "demo", "start", "--dry-run"])
    operate = runner.invoke(
        app,
        ["operate", "--no-clone", "--no-validate", "--execute-configured"],
    )

    assert dry_run.exit_code == 0
    assert "dry_run_passed" in dry_run.output
    assert operate.exit_code == 0
    assert "configured dry runs:" in operate.output
