from __future__ import annotations

import subprocess
from pathlib import Path

from .models import CommandResult, RepoMetadata, now_iso


def run_command(command: list[str], cwd: Path, timeout_seconds: int = 600) -> CommandResult:
    started_at = now_iso()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            started_at=started_at,
            finished_at=now_iso(),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
            started_at=started_at,
            finished_at=now_iso(),
            timed_out=True,
        )


def clone_or_fetch_repo(
    repo: RepoMetadata,
    destination: Path,
    clone_url: str | None = None,
    timeout_seconds: int = 600,
    clone_depth: int | None = 1,
    partial_clone: bool = True,
) -> CommandResult:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        command = ["git", "clone"]
        if partial_clone:
            command.extend(["--filter=blob:none"])
        if clone_depth:
            command.extend(["--depth", str(clone_depth)])
        if repo.default_branch:
            command.extend(["--single-branch", "--branch", repo.default_branch])
        command.extend([clone_url or repo.clone_url, str(destination)])
        return run_command(
            command,
            cwd=destination.parent,
            timeout_seconds=timeout_seconds,
        )
    if (destination / ".git").exists():
        command = ["git", "fetch", "--prune", "origin"]
        if clone_depth:
            command.extend(["--depth", str(clone_depth)])
        return run_command(command, cwd=destination, timeout_seconds=timeout_seconds)
    return CommandResult(
        command=["git", "fetch", "--prune", "origin"],
        cwd=destination,
        exit_code=2,
        stdout="",
        stderr=f"{destination} exists but is not a git checkout",
        started_at=now_iso(),
        finished_at=now_iso(),
    )


def _git_text(path: Path, args: list[str], timeout_seconds: int = 60) -> str | None:
    result = run_command(["git", *args], cwd=path, timeout_seconds=timeout_seconds)
    if not result.ok:
        return None
    return result.stdout.strip()


def inspect_git_checkout(path: Path, default_branch: str) -> dict[str, object]:
    if not (path / ".git").exists():
        return {"exists": path.exists(), "last_error": "missing git checkout"}

    branch = _git_text(path, ["branch", "--show-current"])
    local_head = _git_text(path, ["rev-parse", "HEAD"])
    remote_ref = f"refs/remotes/origin/{default_branch}"
    remote_head = _git_text(path, ["rev-parse", "--verify", remote_ref])
    dirty = bool(_git_text(path, ["status", "--porcelain"]))
    ahead = 0
    behind = 0
    if remote_head:
        counts = _git_text(path, ["rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"])
        if counts:
            left, right = counts.split()
            ahead = int(left)
            behind = int(right)

    return {
        "exists": True,
        "branch": branch,
        "local_head": local_head,
        "remote_head": remote_head,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
    }
