from __future__ import annotations

from datetime import UTC, datetime, timedelta

from conftest import make_repo_metadata

from coasys_ops.classify import classify_repo
from coasys_ops.config import RepoOverride


def test_classifies_core_repo() -> None:
    assert classify_repo(make_repo_metadata("ad4m")) == "core"


def test_classifies_language_repo_by_name() -> None:
    assert classify_repo(make_repo_metadata("matrix-link-language")) == "language"


def test_classifies_dependency_fork_before_stale() -> None:
    old = (datetime.now(UTC) - timedelta(days=900)).isoformat()
    assert classify_repo(make_repo_metadata("deno", updated_at=old)) == "dependency-fork"


def test_classifies_stale_repo() -> None:
    old = (datetime.now(UTC) - timedelta(days=900)).isoformat()
    assert classify_repo(make_repo_metadata("old-app", updated_at=old)) == "stale"


def test_override_tier_wins() -> None:
    repo = make_repo_metadata("old-app")
    assert classify_repo(repo, RepoOverride(tier="core")) == "core"
