from __future__ import annotations

import json
from pathlib import Path

from coasys_ops.detect import detect_repo


def test_detects_typescript_package_commands(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest",
                    "build": "vite build",
                    "dev": "vite",
                    "deploy": "wrangler deploy",
                },
                "devDependencies": {"typescript": "^6.0.0", "svelte": "^5.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")

    stacks, commands = detect_repo(tmp_path)

    assert stacks == ["javascript", "svelte", "typescript"]
    assert commands["validation"][0]["command"] == ["pnpm", "run", "test"]
    assert commands["build"][0]["command"] == ["pnpm", "run", "build"]
    assert commands["start"][0]["command"] == ["pnpm", "run", "dev"]
    assert commands["deploy"][0]["command"] == ["pnpm", "run", "deploy"]


def test_detects_rust_and_nix(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / "flake.nix").write_text("{}", encoding="utf-8")

    stacks, commands = detect_repo(tmp_path)

    assert stacks == ["nix", "rust"]
    assert ["cargo", "metadata", "--no-deps", "--format-version", "1"] in [
        command["command"] for command in commands["validation"]
    ]
    assert ["nix", "flake", "check"] in [command["command"] for command in commands["validation"]]


def test_detects_common_repo_task_files(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "test:\n\tpytest\nbuild:\n\tpython -m build\nserve:\n\tpython -m http.server\n",
        encoding="utf-8",
    )
    (tmp_path / "justfile").write_text(
        "lint:\n    ruff check .\ndeploy:\n    echo deploy\n",
        encoding="utf-8",
    )
    (tmp_path / "Taskfile.yml").write_text(
        "version: '3'\ntasks:\n  check:\n    cmds:\n      - echo check\n",
        encoding="utf-8",
    )

    stacks, commands = detect_repo(tmp_path)

    assert "make" in stacks
    assert "just" in stacks
    assert "taskfile" in stacks
    assert ["make", "test"] in [command["command"] for command in commands["validation"]]
    assert ["just", "lint"] in [command["command"] for command in commands["validation"]]
    assert ["task", "check"] in [command["command"] for command in commands["validation"]]
    assert ["make", "build"] in [command["command"] for command in commands["build"]]
    assert ["make", "serve"] in [command["command"] for command in commands["start"]]
    assert ["just", "deploy"] in [command["command"] for command in commands["deploy"]]
