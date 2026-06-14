from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from .api import create_app
from .ops import CoasysOps
from .weave.cli import app as weave_app

app = typer.Typer(no_args_is_help=True, help="Coasys repository operations dashboard.")
app.add_typer(weave_app, name="weave")


def _ops() -> CoasysOps:
    return CoasysOps(root=Path.cwd())


@app.command()
def sync(
    org: str | None = typer.Option(None, "--org", help="GitHub organization to sync."),
    no_clone: bool = typer.Option(False, "--no-clone", help="Record inventory without cloning."),
    limit: int | None = typer.Option(None, "--limit", help="Limit repositories for a quick pass."),
) -> None:
    """Fetch organization inventory and clone or update managed checkouts."""
    ops = _ops()
    repos = ops.sync(org=org, clone=not no_clone, limit=limit)
    typer.echo(f"synced {len(repos)} repositories")
    for repo in repos:
        typer.echo(f"{repo['name']}: {repo['tier']} {repo.get('validation_status') or ''}".rstrip())


@app.command()
def validate(
    all_repos: bool = typer.Option(False, "--all", help="Validate every synced repository."),
    tier: str | None = typer.Option(None, "--tier", help="Validate a single tier."),
    repo: str | None = typer.Option(None, "--repo", help="Validate one repository."),
    execute_detected: bool = typer.Option(
        False,
        "--execute-detected",
        help="Run detected package/build/test commands in addition to automatic checks.",
    ),
) -> None:
    """Run progressive validation checks against synced repositories."""
    ops = _ops()
    repos = ops.validate_many(
        all_repos=all_repos,
        tier=tier,
        repo_name=repo,
        execute_detected=execute_detected,
    )
    typer.echo(f"validated {len(repos)} repositories")
    for item in repos:
        typer.echo(f"{item['name']}: {item.get('validation_status') or 'unknown'}")


@app.command()
def status() -> None:
    """Print a compact local state summary."""
    summary = _ops().summary()
    typer.echo(f"repositories: {summary['repo_count']}")
    typer.echo(f"cloned: {summary['cloned_count']}")
    typer.echo(f"dirty: {summary['dirty_count']}")
    typer.echo(f"behind: {summary['behind_count']}")
    typer.echo("tiers:")
    for name, count in summary["tiers"].items():
        typer.echo(f"  {name}: {count}")
    typer.echo("statuses:")
    for name, count in summary["statuses"].items():
        typer.echo(f"  {name}: {count}")


@app.command()
def report(
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Optional Markdown report path.",
        ),
    ] = None,
) -> None:
    """Print or write a Markdown operations report."""
    markdown = _ops().report_markdown()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")
        typer.echo(str(output))
        return
    typer.echo(markdown)


@app.command()
def operate(
    org: str | None = typer.Option(None, "--org", help="GitHub organization to operate."),
    clone: bool = typer.Option(True, "--clone/--no-clone", help="Clone or fetch repositories."),
    validate: bool = typer.Option(True, "--validate/--no-validate", help="Run validation checks."),
    deploy: bool = typer.Option(
        False,
        "--deploy",
        help="Evaluate deployment profiles. Does not execute unless --execute-deploy is set.",
    ),
    execute_deploy: bool = typer.Option(
        False,
        "--execute-deploy",
        help="Run explicit deploy profiles. Use only with configured repositories.",
    ),
    execute_configured: bool = typer.Option(
        False,
        "--execute-configured",
        help="Run configured dry-run playbooks for build/start profiles.",
    ),
    tier: str | None = typer.Option(None, "--tier", help="Operate a single tier."),
    limit: int | None = typer.Option(None, "--limit", help="Limit repositories for a quick pass."),
    execute_detected: bool = typer.Option(
        False,
        "--execute-detected",
        help="Run detected validation commands in addition to automatic checks.",
    ),
) -> None:
    """Sync, clone/fetch, validate, and deployment-check the repository fleet."""
    result = _ops().operate_fleet(
        org=org,
        clone=clone,
        validate=validate,
        deploy=deploy,
        execute_deploy=execute_deploy,
        execute_configured=execute_configured,
        tier=tier,
        limit=limit,
        execute_detected=execute_detected,
    )
    typer.echo(f"operated repositories: {result['repo_count']}")
    typer.echo(f"synced: {result['synced_count']}")
    typer.echo(f"validated: {result['validated_count']}")
    typer.echo(f"configured dry runs: {result['configured_dry_run_count']}")
    typer.echo(f"deployed: {result['deployed_count']}")
    typer.echo(f"deploy blocked: {result['deploy_blocked_count']}")
    typer.echo(f"deploy skipped: {result['deploy_skipped_count']}")


@app.command("run")
def run_profile(
    repo: str,
    profile: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Run profile readiness commands."),
    execute: bool = typer.Option(False, "--execute", help="Execute the configured profile."),
) -> None:
    """Run a configured or explicitly supported profile for one repository."""
    ops = _ops()
    run = ops.run_profile(repo, profile, dry_run=dry_run, execute=execute)
    typer.echo(f"run {run['id']} {run['repo_name']}:{run['profile']} {run['status']}")
    if run.get("log_path"):
        typer.echo(f"log: {run['log_path']}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(5050, "--port", help="Bind port."),
) -> None:
    """Serve the local dashboard."""
    uvicorn.run(create_app(Path.cwd()), host=host, port=port)
