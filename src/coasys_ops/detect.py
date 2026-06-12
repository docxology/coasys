from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .models import CommandSpec


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _package_manager(path: Path) -> str:
    if (path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (path / "yarn.lock").exists():
        return "yarn"
    if (path / "bun.lockb").exists() or (path / "bun.lock").exists():
        return "bun"
    return "npm"


def _script_command(package_manager: str, script: str) -> list[str]:
    if package_manager == "bun":
        return ["bun", "run", script]
    return [package_manager, "run", script]


def _target_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    targets: set[str] = set()
    pattern = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith((" ", "\t", "#")):
            continue
        match = pattern.match(line)
        if match:
            targets.add(match.group(1))
    return targets


def _append_target_commands(
    *,
    commands: dict[str, list[CommandSpec]],
    targets: set[str],
    executable: str,
    source: str,
) -> None:
    validation_targets = ["test", "lint", "check", "typecheck"]
    for target in validation_targets:
        if target in targets:
            commands["validation"].append(
                CommandSpec(
                    name=f"{executable}:{target}",
                    command=[executable, target],
                    kind="validation",
                    source=source,
                )
            )
    for target in ["build"]:
        if target in targets:
            commands["build"].append(
                CommandSpec(
                    name=f"{executable}:{target}",
                    command=[executable, target],
                    kind="build",
                    source=source,
                )
            )
    for target in ["serve", "dev", "start"]:
        if target in targets:
            commands["start"].append(
                CommandSpec(
                    name=f"{executable}:{target}",
                    command=[executable, target],
                    kind="start",
                    source=source,
                )
            )
    for target in ["deploy", "release"]:
        if target in targets:
            commands["deploy"].append(
                CommandSpec(
                    name=f"{executable}:{target}",
                    command=[executable, target],
                    kind="deploy",
                    source=source,
                )
            )


def _taskfile_targets(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    return set(tasks) if isinstance(tasks, dict) else set()


def detect_repo(path: Path) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    stacks: set[str] = set()
    commands: dict[str, list[CommandSpec]] = {
        "validation": [],
        "build": [],
        "start": [],
        "deploy": [],
    }

    package_json = path / "package.json"
    if package_json.exists():
        package_payload = _read_json(package_json)
        scripts = package_payload.get("scripts") or {}
        dependencies = {
            **(package_payload.get("dependencies") or {}),
            **(package_payload.get("devDependencies") or {}),
        }
        stacks.add("javascript")
        if (path / "tsconfig.json").exists() or any("typescript" in key for key in dependencies):
            stacks.add("typescript")
        if "svelte" in dependencies or (path / "svelte.config.js").exists():
            stacks.add("svelte")
        if "@tauri-apps/api" in dependencies or (path / "src-tauri").exists():
            stacks.add("tauri")
        package_manager = _package_manager(path)
        for script_name in ["test", "lint", "typecheck", "check"]:
            if script_name in scripts:
                commands["validation"].append(
                    CommandSpec(
                        name=f"{package_manager}:{script_name}",
                        command=_script_command(package_manager, script_name),
                        kind="validation",
                        source="package.json",
                    )
                )
        if "build" in scripts:
            commands["build"].append(
                CommandSpec(
                    name=f"{package_manager}:build",
                    command=_script_command(package_manager, "build"),
                    kind="build",
                    source="package.json",
                )
            )
        for script_name in ["dev", "start"]:
            if script_name in scripts:
                commands["start"].append(
                    CommandSpec(
                        name=f"{package_manager}:{script_name}",
                        command=_script_command(package_manager, script_name),
                        kind="start",
                        source="package.json",
                    )
                )
        for script_name in ["deploy", "release"]:
            if script_name in scripts:
                commands["deploy"].append(
                    CommandSpec(
                        name=f"{package_manager}:{script_name}",
                        command=_script_command(package_manager, script_name),
                        kind="deploy",
                        source="package.json",
                    )
                )

    cargo_toml = path / "Cargo.toml"
    if cargo_toml.exists():
        stacks.add("rust")
        commands["validation"].append(
            CommandSpec(
                name="cargo:metadata",
                command=["cargo", "metadata", "--no-deps", "--format-version", "1"],
                kind="validation",
                source="Cargo.toml",
                automatic=True,
            )
        )
        commands["validation"].append(
            CommandSpec(
                name="cargo:test-no-run",
                command=["cargo", "test", "--no-run"],
                kind="validation",
                source="Cargo.toml",
            )
        )
        commands["build"].append(
            CommandSpec(
                name="cargo:build",
                command=["cargo", "build"],
                kind="build",
                source="Cargo.toml",
            )
        )

    deno_json = path / "deno.json"
    if not deno_json.exists():
        deno_json = path / "deno.jsonc"
    if deno_json.exists():
        stacks.add("deno")
        deno_payload = _read_json(deno_json)
        tasks = deno_payload.get("tasks") or {}
        for task_name in ["test", "check", "lint"]:
            if task_name in tasks:
                commands["validation"].append(
                    CommandSpec(
                        name=f"deno:{task_name}",
                        command=["deno", "task", task_name],
                        kind="validation",
                        source=deno_json.name,
                    )
                )
        if "build" in tasks:
            commands["build"].append(
                CommandSpec(
                    name="deno:build",
                    command=["deno", "task", "build"],
                    kind="build",
                    source=deno_json.name,
                )
            )

    if (path / "flake.nix").exists() or (path / "default.nix").exists():
        stacks.add("nix")
        commands["validation"].append(
            CommandSpec(
                name="nix:flake-check",
                command=["nix", "flake", "check"],
                kind="validation",
                source="flake.nix",
            )
        )

    makefile = path / "Makefile"
    if makefile.exists():
        stacks.add("make")
        _append_target_commands(
            commands=commands,
            targets=_target_names(makefile),
            executable="make",
            source="Makefile",
        )

    justfile = path / "justfile"
    if justfile.exists():
        stacks.add("just")
        _append_target_commands(
            commands=commands,
            targets=_target_names(justfile),
            executable="just",
            source="justfile",
        )

    taskfile_candidates = [path / "Taskfile.yml", path / "Taskfile.yaml"]
    taskfile = next((candidate for candidate in taskfile_candidates if candidate.exists()), None)
    if taskfile:
        stacks.add("taskfile")
        _append_target_commands(
            commands=commands,
            targets=_taskfile_targets(taskfile),
            executable="task",
            source=taskfile.name,
        )

    holochain_markers = [
        path / "dna.yaml",
        path / "happ.yaml",
        path / "workdir",
        path / "zomes",
    ]
    if any(marker.exists() for marker in holochain_markers):
        stacks.add("holochain")

    serialized = {
        kind: [spec.to_dict() for spec in specs if spec.command]
        for kind, specs in commands.items()
    }
    return sorted(stacks), serialized
