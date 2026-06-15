"""Serialise a Weave document back to canonical YAML and save it atomically.

This is the write half of the language. ``document_to_weave_yaml`` emits a
stable, human-friendly ``coasys.weave.yml`` (deterministic key order, empty and
default values omitted), and ``save_document`` writes it atomically and only
inside the project root. Saving is *gated* by the caller: a document with
semantic errors should never be persisted.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .loader import DOCUMENT_NAMES, find_document
from .model import WeaveDocument

# Canonical top-level key order.
_TOP_ORDER = (
    "version",
    "weave",
    "workspace",
    "defaults",
    "environments",
    "starters",
    "seeds",
    "repos",
)
# Canonical per-repo key order.
_REPO_ORDER = (
    "tier",
    "target",
    "priority",
    "description",
    "source",
    "stack",
    "needs",
    "env",
    "timeout_seconds",
    "scaffold",
    "we",
    "playbooks",
)
_PLAYBOOK_ORDER = (
    "run",
    "check",
    "env",
    "working_dir",
    "timeout_seconds",
    "automatic",
    "allow_detected",
    "environment",
    "needs",
)


class _Dumper(yaml.SafeDumper):
    """A dumper that keeps insertion order and indents lists readably."""


def _repr_str(dumper: yaml.Dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _repr_str)


def _prune(value: Any) -> Any:
    """Drop ``None`` and empty containers so the file stays terse."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            pruned = _prune(item)
            if pruned is None or pruned == {} or pruned == []:
                continue
            out[key] = pruned
        return out
    if isinstance(value, list):
        return [_prune(item) for item in value]
    return value


def _ordered(mapping: dict[str, Any], order: tuple[str, ...]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in order:
        if key in mapping:
            out[key] = mapping[key]
    for key, item in mapping.items():  # any keys not in the explicit order
        if key not in out:
            out[key] = item
    return out


def document_to_canonical_mapping(document: WeaveDocument) -> dict[str, Any]:
    """A pruned, deterministically ordered plain mapping for serialisation."""
    raw = _prune(document.model_dump(exclude_none=True))

    # version always present for clarity.
    raw.setdefault("version", document.version)

    repos = raw.get("repos") or {}
    raw["repos"] = {
        name: _order_repo(repo) for name, repo in repos.items()
    }
    return _ordered(raw, _TOP_ORDER)


def _order_repo(repo: dict[str, Any]) -> dict[str, Any]:
    repo = dict(repo)
    playbooks = repo.get("playbooks")
    if playbooks:
        repo["playbooks"] = {
            profile: _ordered(pb, _PLAYBOOK_ORDER) for profile, pb in playbooks.items()
        }
    return _ordered(repo, _REPO_ORDER)


def document_to_weave_yaml(document: WeaveDocument) -> str:
    header = (
        "# Coasys fleet - Weave document\n"
        "# Configuration / design / deployment language. Edit here or via the\n"
        "# dashboard Weave tab (auto-saves). Validated on every save.\n\n"
    )
    body = yaml.dump(
        document_to_canonical_mapping(document),
        Dumper=_Dumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        width=100,
    )
    return header + body


def resolve_target_path(root: Path | None = None) -> Path:
    """Where a save should write.

    Prefer an existing native ``*.weave.yml``; otherwise create
    ``coasys.weave.yml`` at the root (leaving any legacy ``coasys.yml`` intact).
    """
    base = (root or Path.cwd()).resolve()
    existing = find_document(base)
    if existing is not None and existing.name in DOCUMENT_NAMES[:2]:
        return existing
    return base / "coasys.weave.yml"


def save_document(
    document: WeaveDocument,
    root: Path | None = None,
    target: Path | None = None,
) -> Path:
    """Atomically write ``document`` as canonical YAML.

    Writes to a temp file in the same directory then ``os.replace`` for
    atomicity. The target must live inside ``root`` (path-traversal guard).
    """
    base = (root or Path.cwd()).resolve()
    destination = (target or resolve_target_path(base)).resolve()
    # Path-traversal guard: never write outside the project root.
    if base not in destination.parents and destination.parent != base:
        raise ValueError(f"refusing to write outside project root: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    text = document_to_weave_yaml(document)
    fd, tmp_path = tempfile.mkstemp(dir=str(destination.parent), suffix=".weave.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, destination)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return destination


def current_file_hash(root: Path | None = None) -> str | None:
    """SHA-256 of the on-disk document the dashboard loaded, or ``None``.

    Used for optimistic concurrency: the file is also hand-editable (see module
    docstring), so a dashboard save carries the hash it loaded; if the bytes on
    disk changed underneath it, the save is refused rather than clobbering the
    external edit.
    """
    path = find_document(root)
    if path is None:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
