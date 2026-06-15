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


def _seed_weave(tmp_path: Path) -> Path:
    example = Path(__file__).resolve().parents[1] / "examples" / "coasys.weave.yml"
    target = tmp_path / "coasys.weave.yml"
    target.write_text(example.read_text())
    return target


def test_weave_onboard_create_app_registers_and_persists(tmp_path: Path) -> None:
    """Backend the dashboard Onboard tab drives: scaffold + register + save."""
    weave_file = _seed_weave(tmp_path)
    client = TestClient(create_app(tmp_path))

    # Onboard tab loads starters to populate the form.
    starters = client.get("/api/weave/starters").json()["starters"]
    assert "ad4m" in starters

    before = client.get("/api/weave/document").json()
    assert "demo-notes" not in before["document"]["repos"]

    created = client.post(
        "/api/weave/create-app",
        json={"name": "demo-notes", "template": "react"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True and body["saved"] is True
    assert body["command"] == "npx create-ad4m-app demo-notes --template react"
    assert body["repo"] == "demo-notes"

    # Persisted to disk and visible on the next document load.
    assert "demo-notes" in weave_file.read_text()
    after = client.get("/api/weave/document").json()
    assert "demo-notes" in after["document"]["repos"]


def test_weave_onboard_create_app_requires_name(tmp_path: Path) -> None:
    _seed_weave(tmp_path)
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/weave/create-app", json={"name": "  "}).status_code == 400


def test_weave_save_rejects_stale_base_hash(tmp_path: Path) -> None:
    """Optimistic concurrency: a save built on an out-of-date file is refused."""
    weave_file = _seed_weave(tmp_path)
    client = TestClient(create_app(tmp_path))

    payload = client.get("/api/weave/document").json()
    document = payload["document"]
    stale_hash = payload["hash"]
    assert stale_hash  # GET exposes the on-disk hash

    # Someone edits the file on disk after the dashboard loaded it.
    weave_file.write_text(weave_file.read_text() + "\n# hand edit\n")

    conflicted = client.post(
        "/api/weave/document",
        json=document,
        headers={"X-Weave-Base-Hash": stale_hash},
    ).json()
    assert conflicted["saved"] is False and conflicted["conflict"] is True

    # Re-fetching gives the current hash; the same save then succeeds.
    fresh = client.get("/api/weave/document").json()
    ok = client.post(
        "/api/weave/document",
        json=fresh["document"],
        headers={"X-Weave-Base-Hash": fresh["hash"]},
    ).json()
    assert ok["saved"] is True and ok["hash"]
