from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_verification_script_is_dry_run_only_and_self_checking() -> None:
    script = ROOT / "scripts" / "verify_release.sh"

    assert script.exists()
    assert os.access(script, os.X_OK)
    text = script.read_text(encoding="utf-8")
    for expected in [
        "uv run --extra dev ruff check .",
        "uv run --extra dev pytest -q",
        "git diff --check",
        "uv run coasys status",
        "uv run coasys report --output workspace/state/REPORT.md",
        "uv run coasys serve --host 127.0.0.1",
        "/api/summary",
        "/api/report",
    ]:
        assert expected in text
    assert "--execute-deploy" not in text
    assert "?execute=true" not in text


def test_release_runbook_and_ci_cover_handoff_contract() -> None:
    runbook = ROOT / "docs" / "OPERATIONS.md"
    workflow = ROOT / ".github" / "workflows" / "ci.yml"

    assert runbook.exists()
    runbook_text = runbook.read_text(encoding="utf-8")
    for expected in [
        "dry-run",
        "Deployment remains blocked",
        "workspace/state/REPORT.md",
        "screen -S coasys-dashboard -X quit",
    ]:
        assert expected in runbook_text

    assert workflow.exists()
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "uv run --extra dev ruff check ." in workflow_text
    assert "uv run --extra dev pytest -q" in workflow_text
