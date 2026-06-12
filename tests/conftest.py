from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coasys_ops.config import AppConfig, WorkspaceConfig
from coasys_ops.models import RepoMetadata


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        root=tmp_path,
        org="coasys",
        workspace=WorkspaceConfig(repos_dir=tmp_path / "repos", state_dir=tmp_path / "state"),
    )


def make_repo_metadata(
    name: str,
    *,
    clone_url: str = "",
    language: str | None = "TypeScript",
    updated_at: str | None = None,
) -> RepoMetadata:
    if updated_at is None:
        updated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    return RepoMetadata(
        name=name,
        full_name=f"coasys/{name}",
        description="fixture repository",
        html_url=f"https://github.com/coasys/{name}",
        clone_url=clone_url or f"https://github.com/coasys/{name}.git",
        ssh_url=f"git@github.com:coasys/{name}.git",
        default_branch="main",
        visibility="public",
        language=language,
        updated_at=updated_at,
        pushed_at=updated_at,
        raw={"name": name},
    )
