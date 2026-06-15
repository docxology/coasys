from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from coasys_ops.weave import (
    build_graph,
    load_document,
    parse_document,
    validate_document,
)
from coasys_ops.weave.deploy import deploy_readiness
from coasys_ops.weave.export import operation_plan, to_coasys_yml_mapping
from coasys_ops.weave.loader import parse_text
from coasys_ops.weave.seed import render_seed
from coasys_ops.weave.validate import has_errors

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "coasys.weave.yml"


def _example():
    with EXAMPLE.open() as handle:
        return parse_text(handle.read())


# --------------------------------------------------------------------------- #
# Loading: native + legacy
# --------------------------------------------------------------------------- #


def test_example_loads_and_is_valid():
    doc = _example()
    assert doc.version == 1
    assert doc.weave.org == "coasys"
    assert "ad4m" in doc.repos
    issues = validate_document(doc)
    assert not has_errors(issues), [i.to_dict() for i in issues if i.level == "error"]


def test_legacy_coasys_yml_loads_as_superset():
    legacy = {
        "org": "coasys",
        "defaults": {"timeout_seconds": 900, "clone_depth": 1, "partial_clone": True},
        "repos": {
            "ad4m": {
                "tier": "core",
                "timeout_seconds": 1200,
                "playbooks": {
                    "validate": {
                        "commands": ["pnpm run lint"],
                        "dry_run_commands": ["test -f package.json"],
                        "automatic": False,
                    },
                    "deploy": {
                        "commands": ["pnpm run publish"],
                        "env_required": ["NPM_TOKEN"],
                    },
                },
            }
        },
    }
    doc = parse_document(legacy)
    assert doc.weave.org == "coasys"
    repo = doc.repos["ad4m"]
    assert repo.tier == "core"
    assert repo.timeout_seconds == 1200
    assert repo.playbooks["validate"].run == ["pnpm run lint"]
    assert repo.playbooks["validate"].check == ["test -f package.json"]
    assert repo.playbooks["deploy"].env == ["NPM_TOKEN"]
    assert doc.defaults.clone.depth == 1


def test_legacy_coasys_yml_preserves_starters():
    # Regression: the legacy hybrid pass-through once dropped `starters`, which
    # silently broke the dashboard Onboard tab against the real coasys.yml.
    legacy = {
        "org": "coasys",
        "repos": {"ad4m": {"tier": "core"}},
        "starters": {
            "ad4m": {
                "command": "npx create-ad4m-app",
                "repo": "create-ad4m-app",
                "templates": {"solid": {"framework": "solidjs", "default": True}},
            }
        },
    }
    doc = parse_document(legacy)
    assert "ad4m" in doc.starters
    assert doc.starters["ad4m"].templates["solid"].framework == "solidjs"


def test_real_coasys_yml_roundtrips_if_present():
    root = Path(__file__).resolve().parents[1]
    doc = load_document(root)
    # The repo ships a coasys.yml; loading the project root must succeed.
    assert doc.repos, "expected repos loaded from coasys.yml or coasys.weave.yml"
    # The shipped coasys.yml defines the ad4m starter; the Onboard tab needs it.
    assert "ad4m" in doc.starters


# --------------------------------------------------------------------------- #
# Targets / priority
# --------------------------------------------------------------------------- #


def test_targets_ordered_by_priority():
    doc = _example()
    targets = doc.targets()
    assert targets[0] == "ad4m"  # priority 100
    # all core repos are targets even without explicit target flag
    assert "perspect3ve" in targets


# --------------------------------------------------------------------------- #
# Graph + waves
# --------------------------------------------------------------------------- #


def test_graph_build_waves_respect_dependencies():
    doc = _example()
    graph = build_graph(doc)
    assert not graph.cycles
    # ad4m has no needs → wave 0; dependents come later.
    wave_of = {repo: i for i, wave in enumerate(graph.build_waves) for repo in wave}
    assert wave_of["ad4m"] == 0
    assert wave_of["flux"] > wave_of["ad4m"]
    assert wave_of["we"] > wave_of["ad4m"]


def test_graph_has_design_and_deploy_edges():
    doc = _example()
    graph = build_graph(doc)
    kinds = {edge.kind for edge in graph.edges}
    assert "needs" in kinds
    assert "uses" in kinds       # seeds embed repo WE apps
    assert "deploy-to" in kinds  # flux deploys to production


def test_cycle_detection():
    doc = parse_document(
        {
            "version": 1,
            "repos": {
                "a": {"needs": ["b"]},
                "b": {"needs": ["a"]},
            },
        }
    )
    graph = build_graph(doc)
    assert graph.cycles
    issues = validate_document(doc)
    assert any(i.code == "dependency-cycle" for i in issues)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_dangling_dependency_is_error():
    doc = parse_document({"version": 1, "repos": {"a": {"needs": ["ghost"]}}})
    issues = validate_document(doc)
    assert any(i.code == "dangling-need" and i.level == "error" for i in issues)


def test_unknown_environment_is_error():
    deploy_pb = {"run": ["x"], "check": ["y"], "environment": "nope"}
    doc = parse_document(
        {"version": 1, "repos": {"a": {"playbooks": {"deploy": deploy_pb}}}}
    )
    issues = validate_document(doc)
    assert any(i.code == "unknown-environment" for i in issues)


def test_duplicate_route_in_seed_is_error():
    doc = parse_document(
        {
            "version": 1,
            "repos": {
                "a": {"we": {"app": {"id": "a", "name": "A", "route": "/x"}}},
                "b": {"we": {"app": {"id": "b", "name": "B", "route": "/x"}}},
            },
            "seeds": {
                "s": {
                    "project": {"name": "S"},
                    "apps": [{"use": "a"}, {"use": "b"}],
                }
            },
        }
    )
    issues = validate_document(doc)
    assert any(i.code == "duplicate-route" for i in issues)


def test_unknown_capability_rejected():
    with pytest.raises(ValidationError):
        parse_document(
            {
                "version": 1,
                "repos": {
                    "a": {"we": {"app": {"id": "a", "name": "A", "capabilities": ["telepathy"]}}}
                },
            }
        )


# --------------------------------------------------------------------------- #
# Seed compilation → real we-seed.json
# --------------------------------------------------------------------------- #


def test_single_app_seed_routes_at_root_when_unset():
    doc = parse_document(
        {
            "version": 1,
            "repos": {"flux": {"we": {"app": {"id": "flux", "name": "Flux"}}}},
            "seeds": {"l": {"project": {"name": "L"}, "apps": [{"use": "flux"}]}},
        }
    )
    seed = render_seed(doc, "l")
    assert seed["apps"][0]["route"] == "/"
    assert seed["project"]["name"] == "L"


def test_multi_app_seed_preserves_routes():
    doc = _example()
    seed = render_seed(doc, "coasys-workspace")
    routes = {app["route"] for app in seed["apps"]}
    assert routes == {"/flux", "/we"}
    flux = next(a for a in seed["apps"] if a["id"] == "flux")
    assert flux["paths"]["devServer"]["port"] == 3030
    assert flux["commands"]["dev"] == "yarn dev"
    assert flux["capabilities"] == ["perspectives", "languages", "agents"]


# --------------------------------------------------------------------------- #
# Export / round-trip
# --------------------------------------------------------------------------- #


def test_export_to_coasys_yml_mapping():
    doc = _example()
    mapping = to_coasys_yml_mapping(doc)
    assert mapping["org"] == "coasys"
    assert mapping["repos"]["ad4m"]["tier"] == "core"
    # legacy key names restored
    assert mapping["repos"]["ad4m"]["playbooks"]["validate"]["commands"] == ["pnpm run lint"]
    assert "dry_run_commands" in mapping["repos"]["ad4m"]["playbooks"]["validate"]


def test_export_roundtrip_is_stable():
    doc = _example()
    mapping = to_coasys_yml_mapping(doc)
    reloaded = parse_document(mapping)
    assert reloaded.repos["ad4m"].playbooks["validate"].run == ["pnpm run lint"]


def test_setup_is_first_class_lifecycle():
    from coasys_ops.weave.model import LIFECYCLE_PROFILES

    assert LIFECYCLE_PROFILES[0] == "setup"
    doc = _example()
    assert "setup" in doc.repos["ad4m"].playbooks
    assert doc.repos["ad4m"].playbooks["setup"].run == ["pnpm install"]


def test_setup_plan_orders_by_build_waves():
    doc = _example()
    plan = operation_plan(doc, "setup")
    assert plan["profile"] == "setup"
    waves = plan["waves"]
    # ad4m (wave 0) sets up before flux/we (which need ad4m).
    repo_wave = {step["repo"]: w["wave"] for w in waves for step in w["steps"]}
    assert repo_wave["ad4m"] == 0
    assert repo_wave["flux"] > repo_wave["ad4m"]


def test_operation_plan_deploy_orders_waves():
    doc = _example()
    plan = operation_plan(doc, "deploy")
    assert plan["profile"] == "deploy"
    # flux deploy needs ad4m + we; in a deploy plan, only deployables appear.
    deployed = {step["repo"] for wave in plan["waves"] for step in wave["steps"]}
    assert "flux" in deployed


# --------------------------------------------------------------------------- #
# Deployment readiness
# --------------------------------------------------------------------------- #


def test_deploy_readiness_blocks_on_missing_env():
    doc = _example()
    # With no env vars present, production deploys are blocked on secrets.
    report = deploy_readiness(doc, provided_env=set())
    by_repo = {s["repo"]: s for s in report["statuses"]}
    assert "flux" in by_repo
    assert by_repo["flux"]["state"] == "blocked"
    assert "NPM_TOKEN" in by_repo["flux"]["missing_env"]
    assert report["counts"]["blocked"] >= 1
    assert report["ready_to_roll"] is False


def test_deploy_readiness_needs_approval_when_secrets_present():
    doc = _example()
    report = deploy_readiness(doc, provided_env={"NPM_TOKEN", "GITHUB_TOKEN"})
    by_repo = {s["repo"]: s for s in report["statuses"]}
    # Secrets satisfied, but production is protected → needs operator approval.
    assert by_repo["flux"]["state"] == "needs-approval"
    assert by_repo["flux"]["protected"] is True


def test_deploy_readiness_filter_by_environment():
    doc = _example()
    report = deploy_readiness(doc, environment="production", provided_env=set())
    assert all(s["environment"] == "production" for s in report["statuses"])


def test_deploy_readiness_rollout_waves_present():
    doc = _example()
    report = deploy_readiness(doc, provided_env={"NPM_TOKEN", "GITHUB_TOKEN"})
    assert report["rollout"]
    rolled = {m["repo"] for wave in report["rollout"] for m in wave["repos"]}
    assert "flux" in rolled


def test_deploy_check_endpoint_unmet_needs_only_dangling():
    doc = parse_document(
        {
            "version": 1,
            "environments": {"prod": {}},
            "repos": {
                "a": {"playbooks": {"deploy": {"run": ["x"], "check": ["y"], "environment": "prod",
                                               "needs": ["ghost"]}}},
            },
        }
    )
    report = deploy_readiness(doc, provided_env=set())
    status = report["statuses"][0]
    assert status["unmet_needs"] == ["ghost"]


# --------------------------------------------------------------------------- #
# Writer / save-back
# --------------------------------------------------------------------------- #


def test_writer_roundtrip_is_canonical_and_stable():
    from coasys_ops.weave.writer import document_to_weave_yaml

    doc = _example()
    text = document_to_weave_yaml(doc)
    assert text.startswith("# Coasys fleet")
    reloaded = parse_text(text)
    # Re-serialising the reloaded document is byte-stable (idempotent).
    assert document_to_weave_yaml(reloaded) == text
    # Semantic content preserved.
    assert reloaded.repos["flux"].needs == ["ad4m"]
    assert reloaded.targets()[0] == "ad4m"


def test_save_document_atomic_and_roundtrips(tmp_path):
    from coasys_ops.weave.writer import save_document

    doc = _example()
    written = save_document(doc, root=tmp_path)
    assert written.name == "coasys.weave.yml"
    assert written.parent == tmp_path
    reloaded = load_document(tmp_path)
    assert set(reloaded.repos) == set(doc.repos)
    assert not has_errors(validate_document(reloaded))


def test_save_document_refuses_path_traversal(tmp_path):
    from coasys_ops.weave.writer import save_document

    outside = tmp_path.parent / "escape.weave.yml"
    with pytest.raises(ValueError):
        save_document(_example(), root=tmp_path, target=outside)


def test_save_prefers_existing_weave_file(tmp_path):
    from coasys_ops.weave.writer import resolve_target_path

    (tmp_path / "coasys.weave.yml").write_text("version: 1\n", encoding="utf-8")
    assert resolve_target_path(tmp_path).name == "coasys.weave.yml"


def test_deploy_without_gate_is_blocked():
    doc = parse_document(
        {
            "version": 1,
            "environments": {"prod": {}},
            "repos": {
                "a": {"playbooks": {"deploy": {"run": ["ship"], "environment": "prod"}}},
            },
        }
    )
    report = deploy_readiness(doc, provided_env=set())
    status = report["statuses"][0]
    assert status["state"] == "blocked"
    assert any("dry-run" in reason for reason in status["reasons"])


# --------------------------------------------------------------------------- #
# Scaffolding — create-ad4m-app integration
# --------------------------------------------------------------------------- #


def test_starters_present_in_example():
    doc = _example()
    assert "ad4m" in doc.starters
    starter = doc.starters["ad4m"]
    assert starter.command == "npx create-ad4m-app"
    assert starter.default_template == "solid"
    assert set(starter.templates) == {"solid", "react", "vue", "r3f"}
    assert doc.starters["ad4m"].repo == "create-ad4m-app"


def test_create_ad4m_app_is_a_target_repo():
    doc = _example()
    assert "create-ad4m-app" in doc.repos
    assert "create-ad4m-app" in doc.targets()
    assert "setup" in doc.repos["create-ad4m-app"].playbooks


def test_scaffold_command_includes_template():
    from coasys_ops.weave.scaffold import scaffold_command

    doc = _example()
    ad4m = doc.starters["ad4m"]
    assert scaffold_command(ad4m, "notes", None) == "npx create-ad4m-app notes --template solid"
    assert scaffold_command(ad4m, "notes", "react") == "npx create-ad4m-app notes --template react"


def test_register_app_adds_full_fleet_member():
    from coasys_ops.weave.scaffold import register_app

    doc = _example()
    new_doc, cmd = register_app(doc, "my-notes", template="react")
    assert "my-notes" not in doc.repos  # original untouched (pure)
    repo = new_doc.repos["my-notes"]
    assert repo.tier == "active"
    assert repo.stack == ["react"]
    assert repo.needs == ["ad4m"]
    assert repo.scaffold.starter == "ad4m" and repo.scaffold.template == "react"
    assert repo.we.app.route == "/my-notes"
    assert sorted(repo.playbooks) == ["build", "setup", "start", "validate"]
    assert "--template react" in cmd
    assert not has_errors(validate_document(new_doc))


def test_register_app_unique_dev_ports():
    from coasys_ops.weave.scaffold import register_app

    doc = _example()
    d1, _ = register_app(doc, "app-one")
    d2, _ = register_app(d1, "app-two")
    ports = [
        r.we.app.paths.dev_server.port
        for r in d2.repos.values()
        if r.we and r.we.app and r.we.app.paths and r.we.app.paths.dev_server
    ]
    assert len(ports) == len(set(ports))  # no collisions


def test_register_app_rejects_duplicate_and_unknown_template():
    from coasys_ops.weave.scaffold import register_app

    doc = _example()
    with pytest.raises(ValueError):
        register_app(doc, "flux")  # already exists
    with pytest.raises(ValueError):
        register_app(doc, "x", template="svelte")  # unknown template


def test_registered_app_appears_in_graph_and_roundtrips():
    from coasys_ops.weave.scaffold import register_app
    from coasys_ops.weave.writer import document_to_weave_yaml

    doc = _example()
    new_doc, _ = register_app(doc, "my-notes")
    graph = build_graph(new_doc)
    labels = {n.label for n in graph.nodes}
    assert "my-notes" in labels
    # Survives canonical serialisation (scaffold provenance preserved).
    reloaded = parse_text(document_to_weave_yaml(new_doc))
    assert reloaded.repos["my-notes"].scaffold.starter == "ad4m"
