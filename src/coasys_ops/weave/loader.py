"""Loading and serialising Weave documents.

The loader accepts two concrete syntaxes and normalises both into a
:class:`WeaveDocument`:

1. **Native Weave** (``coasys.weave.yml``) - has a ``weave:`` or ``version:`` key.
2. **Legacy ops config** (``coasys.yml``) - the pre-Weave shape with
   ``org`` / ``repos.<name>.playbooks.<profile>.{commands,dry_run_commands}``.

This makes Weave a strict backward-compatible superset: any existing
``coasys.yml`` loads unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import WeaveDocument

# File names searched, in priority order.
DOCUMENT_NAMES = ("coasys.weave.yml", "coasys.weave.yaml", "coasys.yml")


def _is_native(payload: dict[str, Any]) -> bool:
    return "weave" in payload or "version" in payload


def _normalise_clone(defaults: dict[str, Any]) -> dict[str, Any]:
    """Translate legacy flat clone keys into the nested ``clone`` block."""
    clone: dict[str, Any] = {}
    if "clone_protocol" in defaults:
        clone["protocol"] = defaults["clone_protocol"]
    if "clone_depth" in defaults:
        clone["depth"] = defaults["clone_depth"]
    if "partial_clone" in defaults:
        clone["partial"] = defaults["partial_clone"]
    return clone


def _legacy_playbook(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, str):
        return {"run": [payload]}
    if isinstance(payload, list):
        return {"run": [str(item) for item in payload]}
    if not isinstance(payload, dict):
        raise TypeError("playbook must be a string, list, or mapping")
    out: dict[str, Any] = {}
    if payload.get("commands") is not None:
        out["run"] = _as_list(payload["commands"])
    if payload.get("dry_run_commands") is not None:
        out["check"] = _as_list(payload["dry_run_commands"])
    if payload.get("env_required") is not None:
        out["env"] = [str(item) for item in payload["env_required"]]
    for key in ("working_dir", "timeout_seconds", "automatic", "allow_detected", "environment"):
        if key in payload:
            out[key] = payload[key]
    if payload.get("needs") is not None:
        out["needs"] = [str(item) for item in payload["needs"]]
    return out


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise TypeError(f"expected string or list, got {type(value).__name__}")


def _legacy_repo(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload or {}
    repo: dict[str, Any] = {}
    if "tier" in payload:
        repo["tier"] = payload["tier"]
    if "timeout_seconds" in payload:
        repo["timeout_seconds"] = payload["timeout_seconds"]
    if payload.get("env_required"):
        repo["env"] = [str(item) for item in payload["env_required"]]
    if payload.get("clone_url"):
        repo.setdefault("source", {})["clone_url"] = payload["clone_url"]
    # Native-style fields may already be present in a hybrid file.
    for key in ("target", "priority", "description", "stack", "needs", "we", "source"):
        if key in payload:
            repo[key] = payload[key]
    playbooks = payload.get("playbooks") or {}
    if playbooks:
        repo["playbooks"] = {
            str(name): _legacy_playbook(pb) for name, pb in playbooks.items()
        }
    # Legacy ``profiles`` (bare command lists) become run-only playbooks.
    for name, commands in (payload.get("profiles") or {}).items():
        repo.setdefault("playbooks", {})[str(name)] = {"run": _as_list(commands)}
    if payload.get("validation_commands"):
        repo.setdefault("playbooks", {}).setdefault("validate", {})["run"] = _as_list(
            payload["validation_commands"]
        )
    return repo


def _from_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    defaults = dict(payload.get("defaults") or {})
    clone = _normalise_clone(defaults)
    native_defaults: dict[str, Any] = {}
    if "timeout_seconds" in defaults:
        native_defaults["timeout_seconds"] = defaults["timeout_seconds"]
    if "execute_detected_validation" in defaults:
        native_defaults["execute_detected_validation"] = defaults["execute_detected_validation"]
    if "package_manager" in defaults:
        native_defaults["package_manager"] = defaults["package_manager"]
    if clone:
        native_defaults["clone"] = clone

    native: dict[str, Any] = {
        "version": 1,
        "weave": {"org": str(payload.get("org") or "coasys")},
        "defaults": native_defaults,
        "repos": {
            str(name): _legacy_repo(repo or {})
            for name, repo in (payload.get("repos") or {}).items()
        },
    }
    if payload.get("workspace"):
        native["workspace"] = payload["workspace"]
    # Pass through native-only sections if present in a hybrid file.
    for key in ("environments", "seeds"):
        if key in payload:
            native[key] = payload[key]
    return native


def parse_document(payload: dict[str, Any] | None) -> WeaveDocument:
    """Build a :class:`WeaveDocument` from a parsed mapping (native or legacy)."""
    payload = payload or {}
    if not isinstance(payload, dict):
        raise TypeError("Weave document root must be a mapping")
    native = payload if _is_native(payload) else _from_legacy(payload)
    return WeaveDocument.model_validate(native)


def parse_text(text: str) -> WeaveDocument:
    return parse_document(yaml.safe_load(text) or {})


def find_document(root: Path | None = None) -> Path | None:
    base = (root or Path.cwd()).resolve()
    if base.is_file():
        return base
    for name in DOCUMENT_NAMES:
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def load_document(root: Path | None = None) -> WeaveDocument:
    """Load the fleet document from ``root`` (defaults to CWD).

    Prefers ``coasys.weave.yml``, falling back to legacy ``coasys.yml``. Returns
    an empty document if neither exists.
    """
    path = find_document(root)
    if path is None:
        return WeaveDocument()
    with path.open("r", encoding="utf-8") as handle:
        return parse_document(yaml.safe_load(handle) or {})


def document_to_mapping(document: WeaveDocument) -> dict[str, Any]:
    """Serialise a document back to a plain mapping (drops null/empty fields)."""
    return document.model_dump(exclude_none=True, exclude_defaults=False)


def document_to_yaml(document: WeaveDocument) -> str:
    return yaml.safe_dump(
        document_to_mapping(document), sort_keys=False, default_flow_style=False
    )
