from __future__ import annotations

from coasys_ops.config import load_config


def test_load_config_parses_structured_playbooks(tmp_path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (tmp_path / "coasys.yml").write_text(
        """
org: coasys
workspace:
  repos_dir: workspace/repos
  state_dir: workspace/state
repos:
  demo:
    tier: core
    playbooks:
      deploy:
        commands:
          - pnpm run release
        dry_run_commands:
          - pnpm run release:preflight
        env_required:
          - GITHUB_TOKEN
        working_dir: packages/app
        timeout_seconds: 1200
        automatic: false
""",
        encoding="utf-8",
    )

    config = load_config(tmp_path)
    playbook = config.repos["demo"].playbooks["deploy"]

    assert playbook.commands == ["pnpm run release"]
    assert playbook.dry_run_commands == ["pnpm run release:preflight"]
    assert playbook.env_required == ["GITHUB_TOKEN"]
    assert playbook.working_dir == "packages/app"
    assert playbook.timeout_seconds == 1200
    assert playbook.automatic is False
