from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _markdown_files() -> list[Path]:
    return sorted([ROOT / "README.md", *(ROOT / "docs").glob("*.md")])


def test_markdown_local_links_resolve() -> None:
    missing: list[str] = []
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        for raw_target in LOCAL_LINK_PATTERN.findall(text):
            target = raw_target.split("#", 1)[0].strip()
            if not target or "://" in target or target.startswith(("mailto:", "tel:")):
                continue
            target_path = (path.parent / target).resolve()
            if not target_path.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {raw_target}")

    assert missing == []


def test_readme_links_to_modular_documentation() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in [
        "docs/README.md",
        "docs/ARCHITECTURE.md",
        "docs/CLI.md",
        "docs/API.md",
        "docs/CONFIGURATION.md",
        "docs/PLAYBOOKS.md",
        "docs/STATE_AND_REPORTING.md",
        "docs/DASHBOARD.md",
        "docs/OPERATIONS.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/TROUBLESHOOTING.md",
    ]:
        assert target in readme

