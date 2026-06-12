from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import RepoSnapshot, now_iso


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS repos (
                    name TEXT PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    html_url TEXT NOT NULL,
                    clone_url TEXT NOT NULL,
                    ssh_url TEXT NOT NULL,
                    default_branch TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    language TEXT,
                    stars INTEGER NOT NULL,
                    forks INTEGER NOT NULL,
                    open_issues INTEGER NOT NULL,
                    updated_at TEXT,
                    pushed_at TEXT,
                    archived INTEGER NOT NULL,
                    tier TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    exists_local INTEGER NOT NULL,
                    branch TEXT,
                    local_head TEXT,
                    remote_head TEXT,
                    dirty INTEGER NOT NULL,
                    ahead INTEGER NOT NULL,
                    behind INTEGER NOT NULL,
                    stacks_json TEXT NOT NULL,
                    commands_json TEXT NOT NULL,
                    ci_status TEXT,
                    ci_conclusion TEXT,
                    validation_status TEXT,
                    last_error TEXT,
                    last_synced_at TEXT,
                    last_validated_at TEXT,
                    raw_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_code INTEGER,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    commands_json TEXT NOT NULL,
                    output_tail TEXT NOT NULL,
                    log_path TEXT
                );
                """
            )

    def upsert_repo(self, snapshot: RepoSnapshot) -> None:
        metadata = snapshot.metadata
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO repos (
                    name, full_name, description, html_url, clone_url, ssh_url,
                    default_branch, visibility, language, stars, forks, open_issues,
                    updated_at, pushed_at, archived, tier, local_path, exists_local,
                    branch, local_head, remote_head, dirty, ahead, behind, stacks_json,
                    commands_json, ci_status, ci_conclusion, validation_status, last_error,
                    last_synced_at, last_validated_at, raw_json
                )
                VALUES (
                    :name, :full_name, :description, :html_url, :clone_url, :ssh_url,
                    :default_branch, :visibility, :language, :stars, :forks, :open_issues,
                    :updated_at, :pushed_at, :archived, :tier, :local_path, :exists_local,
                    :branch, :local_head, :remote_head, :dirty, :ahead, :behind, :stacks_json,
                    :commands_json, :ci_status, :ci_conclusion, :validation_status, :last_error,
                    :last_synced_at, :last_validated_at, :raw_json
                )
                ON CONFLICT(name) DO UPDATE SET
                    full_name=excluded.full_name,
                    description=excluded.description,
                    html_url=excluded.html_url,
                    clone_url=excluded.clone_url,
                    ssh_url=excluded.ssh_url,
                    default_branch=excluded.default_branch,
                    visibility=excluded.visibility,
                    language=excluded.language,
                    stars=excluded.stars,
                    forks=excluded.forks,
                    open_issues=excluded.open_issues,
                    updated_at=excluded.updated_at,
                    pushed_at=excluded.pushed_at,
                    archived=excluded.archived,
                    tier=excluded.tier,
                    local_path=excluded.local_path,
                    exists_local=excluded.exists_local,
                    branch=excluded.branch,
                    local_head=excluded.local_head,
                    remote_head=excluded.remote_head,
                    dirty=excluded.dirty,
                    ahead=excluded.ahead,
                    behind=excluded.behind,
                    stacks_json=excluded.stacks_json,
                    commands_json=excluded.commands_json,
                    ci_status=excluded.ci_status,
                    ci_conclusion=excluded.ci_conclusion,
                    validation_status=COALESCE(excluded.validation_status, repos.validation_status),
                    last_error=excluded.last_error,
                    last_synced_at=COALESCE(excluded.last_synced_at, repos.last_synced_at),
                    last_validated_at=COALESCE(excluded.last_validated_at, repos.last_validated_at),
                    raw_json=excluded.raw_json
                """,
                {
                    "name": metadata.name,
                    "full_name": metadata.full_name,
                    "description": metadata.description,
                    "html_url": metadata.html_url,
                    "clone_url": metadata.clone_url,
                    "ssh_url": metadata.ssh_url,
                    "default_branch": metadata.default_branch,
                    "visibility": metadata.visibility,
                    "language": metadata.language,
                    "stars": metadata.stars,
                    "forks": metadata.forks,
                    "open_issues": metadata.open_issues,
                    "updated_at": metadata.updated_at,
                    "pushed_at": metadata.pushed_at,
                    "archived": int(metadata.archived),
                    "tier": snapshot.tier,
                    "local_path": str(snapshot.local_path),
                    "exists_local": int(snapshot.exists),
                    "branch": snapshot.branch,
                    "local_head": snapshot.local_head,
                    "remote_head": snapshot.remote_head,
                    "dirty": int(snapshot.dirty),
                    "ahead": snapshot.ahead,
                    "behind": snapshot.behind,
                    "stacks_json": json.dumps(snapshot.stacks, sort_keys=True),
                    "commands_json": json.dumps(snapshot.commands, sort_keys=True),
                    "ci_status": snapshot.ci_status,
                    "ci_conclusion": snapshot.ci_conclusion,
                    "validation_status": snapshot.validation_status,
                    "last_error": snapshot.last_error,
                    "last_synced_at": snapshot.last_synced_at,
                    "last_validated_at": snapshot.last_validated_at,
                    "raw_json": json.dumps(metadata.raw, sort_keys=True),
                },
            )

    def _repo_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["archived"] = bool(data.pop("archived"))
        data["exists"] = bool(data.pop("exists_local"))
        data["dirty"] = bool(data["dirty"])
        data["stacks"] = json.loads(data.pop("stacks_json"))
        data["commands"] = json.loads(data.pop("commands_json"))
        data["raw"] = json.loads(data.pop("raw_json"))
        return data

    def list_repos(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM repos ORDER BY tier, updated_at DESC, name"
            ).fetchall()
        return [self._repo_from_row(row) for row in rows]

    def get_repo(self, name: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM repos WHERE name = ?", (name,)).fetchone()
        return self._repo_from_row(row) if row else None

    def create_run(self, repo_name: str, kind: str, profile: str, commands: list[list[str]]) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    repo_name, kind, profile, status, started_at, commands_json, output_tail
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (repo_name, kind, profile, "running", now_iso(), json.dumps(commands), ""),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        exit_code: int | None,
        output_tail: str,
        log_path: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET status = ?, exit_code = ?, finished_at = ?, output_tail = ?, log_path = ?
                WHERE id = ?
                """,
                (status, exit_code, now_iso(), output_tail, log_path, run_id),
            )

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["commands"] = json.loads(data.pop("commands_json"))
        return data

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        runs: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["commands"] = json.loads(data.pop("commands_json"))
            runs.append(data)
        return runs
