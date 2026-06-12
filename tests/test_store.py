from __future__ import annotations

from pathlib import Path

from conftest import make_repo_metadata

from coasys_ops.models import RepoSnapshot
from coasys_ops.store import Store


def test_store_round_trips_repo_and_runs(tmp_path: Path) -> None:
    store = Store(tmp_path / "state.sqlite3")
    metadata = make_repo_metadata("demo")
    snapshot = RepoSnapshot(
        metadata=metadata,
        tier="active",
        local_path=tmp_path / "repos" / "demo",
        exists=True,
        stacks=["typescript"],
        commands={"validation": [], "build": [], "start": [], "deploy": []},
        validation_status="passed",
    )

    store.upsert_repo(snapshot)
    repos = store.list_repos()

    assert len(repos) == 1
    assert repos[0]["name"] == "demo"
    assert repos[0]["exists"] is True
    assert repos[0]["stacks"] == ["typescript"]

    run_id = store.create_run("demo", "validation", "validate", [["echo", "ok"]])
    store.finish_run(run_id, "passed", 0, "ok", "/tmp/run.log")

    run = store.get_run(run_id)
    assert run is not None
    assert run["commands"] == [["echo", "ok"]]
    assert store.list_runs()[0]["status"] == "passed"


def test_repo_upsert_preserves_operational_state_when_snapshot_omits_it(tmp_path: Path) -> None:
    store = Store(tmp_path / "state.sqlite3")
    metadata = make_repo_metadata("demo")
    first = RepoSnapshot(
        metadata=metadata,
        tier="core",
        local_path=tmp_path / "repos" / "demo",
        exists=False,
        validation_status="missing",
        last_synced_at="2026-06-12T00:00:00+00:00",
        last_validated_at="2026-06-12T00:01:00+00:00",
    )
    second = RepoSnapshot(
        metadata=metadata,
        tier="core",
        local_path=tmp_path / "repos" / "demo",
        exists=True,
        branch="main",
    )

    store.upsert_repo(first)
    store.upsert_repo(second)
    row = store.get_repo("demo")

    assert row is not None
    assert row["exists"] is True
    assert row["branch"] == "main"
    assert row["validation_status"] == "missing"
    assert row["last_synced_at"] == "2026-06-12T00:00:00+00:00"
    assert row["last_validated_at"] == "2026-06-12T00:01:00+00:00"
