"""Weave: the configuration / design / deployment language for the Coasys fleet.

Weave is a declarative, visual-and-textual language for describing how the
``github.com/coasys`` repositories are configured, designed (via the WE
launcher/seed system), and deployed. It is a backward-compatible superset of
the legacy ``coasys.yml`` operations config.

The package is intentionally dependency-light (pydantic + pyyaml) and free of
runtime coupling to the operations layer, so it can be imported and tested in
isolation.

Public surface
--------------
- :class:`~coasys_ops.weave.model.WeaveDocument` and friends: the language model.
- :func:`~coasys_ops.weave.loader.load_document`: load ``*.weave.yml`` or legacy
  ``coasys.yml`` into a :class:`WeaveDocument`.
- :func:`~coasys_ops.weave.validate.validate_document`: semantic validation.
- :func:`~coasys_ops.weave.graph.build_graph`: dependency / deploy graph + waves.
- :func:`~coasys_ops.weave.seed.render_seed`: emit a real WE ``we-seed.json``.
- :mod:`~coasys_ops.weave.export`: round-trip to ``coasys.yml`` / JSON Schema /
  Mermaid / DOT.
"""

from __future__ import annotations

from .deploy import deploy_readiness
from .graph import build_graph
from .loader import (
    document_to_mapping,
    load_document,
    parse_document,
)
from .model import (
    CAPABILITIES,
    KNOWN_TIERS,
    Environment,
    Playbook,
    Repo,
    Seed,
    Starter,
    WeApp,
    WeaveDocument,
)
from .scaffold import register_app, scaffold_command
from .validate import Issue, validate_document
from .writer import document_to_weave_yaml, save_document

__all__ = [
    "CAPABILITIES",
    "KNOWN_TIERS",
    "Environment",
    "Issue",
    "Playbook",
    "Repo",
    "Seed",
    "Starter",
    "WeApp",
    "WeaveDocument",
    "build_graph",
    "deploy_readiness",
    "document_to_mapping",
    "document_to_weave_yaml",
    "register_app",
    "save_document",
    "scaffold_command",
    "load_document",
    "parse_document",
    "validate_document",
]

LANGUAGE_VERSION = 1
