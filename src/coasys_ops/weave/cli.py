"""``coasys weave`` — the command-line surface of the Weave language.

Mounted onto the main Typer app as a sub-command group. Every command operates
on the fleet document discovered from the current directory
(``coasys.weave.yml`` preferred, else ``coasys.yml``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .deploy import deploy_readiness
from .export import json_schema, operation_plan, to_coasys_yml
from .graph import build_graph, to_dot, to_mermaid
from .loader import load_document
from .seed import render_seed_json
from .validate import has_errors, validate_document
from .writer import resolve_target_path, save_document

app = typer.Typer(no_args_is_help=True, help="The Weave configuration/design/deployment language.")

PathOpt = Annotated[Path | None, typer.Option("--path", help="Document or directory.")]
OutOpt = Annotated[Path | None, typer.Option("--output", "-o", help="Write output here.")]


def _doc(path: Path | None):
    return load_document(path or Path.cwd())


@app.command()
def lint(
    path: PathOpt = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit non-zero on warnings too.")
    ] = False,
) -> None:
    """Validate a Weave document (structure + semantics)."""
    document = _doc(path)
    issues = validate_document(document)
    if not issues:
        typer.echo("ok: no issues")
        return
    errors = warnings = 0
    for issue in issues:
        if issue.level == "error":
            errors += 1
        elif issue.level == "warning":
            warnings += 1
        location = f" [{issue.path}]" if issue.path else ""
        typer.echo(f"{issue.level.upper():7} {issue.code}: {issue.message}{location}")
    typer.echo(f"\n{errors} error(s), {warnings} warning(s)")
    if errors or (strict and warnings):
        raise typer.Exit(code=1)


@app.command()
def targets(path: PathOpt = None) -> None:
    """List priority operation targets (most important repos first)."""
    document = _doc(path)
    for name in document.targets():
        repo = document.repos[name]
        typer.echo(f"{name}\t{repo.tier or '-'}\tpriority={repo.priority}")


@app.command()
def graph(
    path: PathOpt = None,
    format: Annotated[str, typer.Option("--format", "-f", help="json | mermaid | dot")] = "json",
) -> None:
    """Emit the fleet graph (the visual language's backbone)."""
    document = _doc(path)
    if format == "mermaid":
        typer.echo(to_mermaid(document))
    elif format == "dot":
        typer.echo(to_dot(document))
    else:
        typer.echo(json.dumps(build_graph(document).to_dict(), indent=2))


@app.command()
def plan(
    profile: Annotated[str, typer.Argument(help="build | deploy | validate | start")] = "build",
    path: PathOpt = None,
) -> None:
    """Print an ordered, wave-by-wave execution plan for a profile."""
    document = _doc(path)
    result = operation_plan(document, profile)
    typer.echo(f"profile: {result['profile']}")
    if result["cycles"]:
        typer.echo(f"WARNING cycles: {result['cycles']}")
    for wave in result["waves"]:
        repos = ", ".join(step["repo"] for step in wave["steps"])
        typer.echo(f"  wave {wave['wave']}: {repos}")


@app.command()
def seed(
    name: Annotated[str, typer.Argument(help="Seed name to compile.")],
    path: PathOpt = None,
    output: OutOpt = None,
) -> None:
    """Compile a seed into a real WE ``we-seed.json``."""
    document = _doc(path)
    payload = render_seed_json(document, name)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(payload)


@app.command("export-yml")
def export_yml(path: PathOpt = None, output: OutOpt = None) -> None:
    """Compile the Weave document down to a legacy ``coasys.yml``."""
    document = _doc(path)
    text = to_coasys_yml(document)
    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(text)


@app.command("deploy-check")
def deploy_check(
    environment: Annotated[
        str | None, typer.Option("--environment", "-e", help="Filter to one environment.")
    ] = None,
    path: PathOpt = None,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit non-zero if anything is blocked.")
    ] = False,
) -> None:
    """Report deployment readiness and the rollout order for the fleet."""
    document = _doc(path)
    report = deploy_readiness(document, environment=environment)
    counts = report["counts"]
    typer.echo(
        f"ready={counts.get('ready', 0)} "
        f"needs-approval={counts.get('needs-approval', 0)} "
        f"blocked={counts.get('blocked', 0)}"
    )
    for status in report["statuses"]:
        line = f"  {status['repo']:<18} {status['state']:<14} env={status['environment'] or '-'}"
        if status["reasons"]:
            line += "  :: " + "; ".join(status["reasons"])
        typer.echo(line)
    if report["rollout"]:
        typer.echo("rollout:")
        for wave in report["rollout"]:
            typer.echo(f"  wave {wave['wave']}: " + ", ".join(m["repo"] for m in wave["repos"]))
    if strict and counts.get("blocked", 0):
        raise typer.Exit(code=1)


@app.command()
def fmt(
    path: PathOpt = None,
    check: Annotated[
        bool, typer.Option("--check", help="Exit non-zero if the file is not canonical.")
    ] = False,
) -> None:
    """Rewrite the document in canonical form (validate-gated)."""
    document = _doc(path)
    issues = validate_document(document)
    if has_errors(issues):
        for issue in issues:
            if issue.level == "error":
                typer.echo(f"ERROR {issue.code}: {issue.message}")
        raise typer.Exit(code=1)
    base = path or Path.cwd()
    target = resolve_target_path(base if base.is_dir() else base.parent)
    from .writer import document_to_weave_yaml

    new_text = document_to_weave_yaml(document)
    if check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != new_text:
            typer.echo(f"not canonical: {target}")
            raise typer.Exit(code=1)
        typer.echo("ok: canonical")
        return
    written = save_document(document, root=base if base.is_dir() else base.parent, target=target)
    typer.echo(str(written))


@app.command()
def schema(output: OutOpt = None) -> None:
    """Emit the JSON Schema for a Weave document (drives the schema forms)."""
    text = json.dumps(json_schema(), indent=2)
    if output:
        output.write_text(text + "\n", encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(text)
