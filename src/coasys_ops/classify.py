from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .config import RepoOverride
from .models import RepoMetadata

CORE_REPOS = {
    "ad4m",
    "we",
    "perspect3ve",
    "flux",
    "ad4m-host",
    "ad4m-devtools",
    "ad4m-wind-tunnel",
}

DEPENDENCY_FORKS = {
    "deno",
    "deno_core",
    "rusty_v8",
    "holochain",
    "lair",
    "tauri",
    "wasmer",
    "reqwest",
    "juniper",
    "rusqlite",
    "url2",
    "floneum",
    "scryer-prolog",
    "dashu",
    "hyper-util",
    "notify-rust",
    "webbrowser-rs",
    "holochain-client-js",
    "holochain-serialization",
    "holochain-wasmer",
    "hc_r2d2-sqlite",
    "r2d2-sqlite",
    "rustls-tokio-stream",
    "zip2",
    "influxive",
    "libffi-rs",
    "aead-gcm-stream",
}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify_repo(repo: RepoMetadata, override: RepoOverride | None = None) -> str:
    if override and override.tier:
        return override.tier

    name = repo.name.lower()
    description = repo.description.lower()

    if name in CORE_REPOS:
        return "core"
    if name in DEPENDENCY_FORKS:
        return "dependency-fork"
    if "language" in name or "link-language" in name:
        return "language"
    if "ad4m link language" in description or "ad4m expression language" in description:
        return "language"
    if repo.archived:
        return "stale"

    updated_at = _parse_timestamp(repo.updated_at)
    if updated_at and updated_at < datetime.now(UTC) - timedelta(days=365):
        return "stale"
    if updated_at and updated_at >= datetime.now(UTC) - timedelta(days=120):
        return "active"
    return "unknown"
