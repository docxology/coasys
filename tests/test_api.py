from __future__ import annotations

from pathlib import Path

from conftest import make_repo_metadata
from fastapi.testclient import TestClient

from coasys_ops.api import create_app
from coasys_ops.config import AppConfig, OperationPlaybook, RepoOverride, WorkspaceConfig
from coasys_ops.models import RepoSnapshot
from coasys_ops.store import Store


def test_api_lists_repos_and_runs(tmp_path: Path) -> None:
    config = AppConfig(
        root=tmp_path,
        org="coasys",
        workspace=WorkspaceConfig(
            repos_dir=tmp_path / "workspace/repos",
            state_dir=tmp_path / "workspace/state",
        ),
    )
    store = Store(config.workspace.state_dir / "coasys.sqlite3")
    metadata = make_repo_metadata("demo")
    store.upsert_repo(
        RepoSnapshot(
            metadata=metadata,
            tier="active",
            local_path=config.workspace.repos_dir / "demo",
            exists=False,
            validation_status="missing",
        )
    )

    app = create_app(tmp_path)
    client = TestClient(app)

    repos = client.get("/api/repos")
    assert repos.status_code == 200
    assert repos.json()["count"] == 1
    assert repos.json()["repos"][0]["name"] == "demo"
    assert repos.json()["repos"][0]["deploy_status"] == "deploy_blocked"

    repo = client.get("/api/repos/demo")
    assert repo.status_code == 200
    assert repo.json()["repo"]["validation_status"] == "missing"

    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()["runs"] == []

    summary = client.get("/api/summary")
    assert summary.status_code == 200
    assert summary.json()["repo_count"] == 1
    assert summary.json()["statuses"]["missing"] == 1

    report = client.get("/api/report")
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    assert "# Coasys Repository Operations Report" in report.text

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 204

    operate = client.post("/api/operate", params={"clone": False, "validate": False})
    assert operate.status_code == 200
    assert operate.json()["repo_count"] == 1


def test_api_returns_404_for_unknown_repo(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)

    response = client.get("/api/repos/nope")

    assert response.status_code == 404


def test_api_run_profile_accepts_dry_run_flag(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / "coasys.yml"
    config_path.write_text(
        """
org: coasys
workspace:
  repos_dir: workspace/repos
  state_dir: workspace/state
repos:
  demo:
    playbooks:
      deploy:
        commands:
          - echo deploy
        dry_run_commands:
          - echo dry-run
""",
        encoding="utf-8",
    )
    config = AppConfig(
        root=tmp_path,
        org="coasys",
        workspace=WorkspaceConfig(
            repos_dir=tmp_path / "workspace/repos",
            state_dir=tmp_path / "workspace/state",
        ),
        repos={
            "demo": RepoOverride(
                playbooks={
                    "deploy": OperationPlaybook(
                        commands=["echo deploy"],
                        dry_run_commands=["echo dry-run"],
                    )
                }
            )
        },
    )
    local_path = config.workspace.repos_dir / "demo"
    local_path.mkdir(parents=True)
    store = Store(config.workspace.state_dir / "coasys.sqlite3")
    store.upsert_repo(
        RepoSnapshot(
            metadata=make_repo_metadata("demo"),
            tier="active",
            local_path=local_path,
            exists=True,
            validation_status="passed",
        )
    )

    app = create_app(tmp_path)
    client = TestClient(app)

    response = client.post("/api/repos/demo/run/deploy", params={"dry_run": True})

    assert response.status_code == 200
    assert response.json()["run"]["status"] == "dry_run_passed"
