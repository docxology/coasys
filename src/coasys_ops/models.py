from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class RepoMetadata:
    name: str
    full_name: str
    description: str
    html_url: str
    clone_url: str
    ssh_url: str
    default_branch: str
    visibility: str
    language: str | None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    updated_at: str | None = None
    pushed_at: str | None = None
    archived: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_github(cls, payload: dict[str, Any]) -> RepoMetadata:
        return cls(
            name=str(payload["name"]),
            full_name=str(payload.get("full_name") or payload["name"]),
            description=str(payload.get("description") or ""),
            html_url=str(payload.get("html_url") or ""),
            clone_url=str(payload.get("clone_url") or ""),
            ssh_url=str(payload.get("ssh_url") or ""),
            default_branch=str(payload.get("default_branch") or "main"),
            visibility=str(payload.get("visibility") or "public"),
            language=payload.get("language"),
            stars=int(payload.get("stargazers_count") or payload.get("stars") or 0),
            forks=int(payload.get("forks_count") or payload.get("forks") or 0),
            open_issues=int(payload.get("open_issues_count") or payload.get("open_issues") or 0),
            updated_at=payload.get("updated_at"),
            pushed_at=payload.get("pushed_at"),
            archived=bool(payload.get("archived", False)),
            raw=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CommandSpec:
    name: str
    command: list[str]
    kind: str
    source: str
    automatic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RepoSnapshot:
    metadata: RepoMetadata
    tier: str
    local_path: Path
    exists: bool
    branch: str | None = None
    local_head: str | None = None
    remote_head: str | None = None
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    stacks: list[str] = field(default_factory=list)
    commands: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ci_status: str | None = None
    ci_conclusion: str | None = None
    validation_status: str | None = None
    last_error: str | None = None
    last_synced_at: str | None = None
    last_validated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["local_path"] = str(self.local_path)
        return data


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str
    started_at: str
    finished_at: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def output_tail(self) -> str:
        output = "\n".join(part for part in [self.stdout, self.stderr] if part)
        return output[-20000:]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["cwd"] = str(self.cwd)
        return data
