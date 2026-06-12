from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .ops import CoasysOps

STATIC_DIR = Path(__file__).parent / "static"


def _public_repo(repo: dict[str, object]) -> dict[str, object]:
    public = dict(repo)
    public.pop("raw", None)
    return public


def create_app(root: Path | None = None) -> FastAPI:
    ops = CoasysOps(root=root)
    app = FastAPI(title="Coasys Ops Dashboard", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/repos")
    def list_repos() -> dict[str, object]:
        repos = [_public_repo(repo) for repo in ops.list_repos()]
        return {"count": len(repos), "repos": repos}

    @app.get("/api/summary")
    def summary() -> dict[str, object]:
        return ops.summary()

    @app.get("/api/report")
    def report() -> PlainTextResponse:
        return PlainTextResponse(
            ops.report_markdown(),
            media_type="text/markdown; charset=utf-8",
        )

    @app.post("/api/operate")
    def operate(
        clone: bool = True,
        validate: bool = True,
        deploy: bool = False,
        execute_deploy: bool = False,
        execute_configured: bool = False,
        tier: str | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        return ops.operate_fleet(
            clone=clone,
            validate=validate,
            deploy=deploy,
            execute_deploy=execute_deploy,
            execute_configured=execute_configured,
            tier=tier,
            limit=limit,
        )

    @app.get("/api/repos/{name}")
    def get_repo(name: str) -> dict[str, object]:
        repo = ops.get_repo(name)
        if repo is None:
            raise HTTPException(status_code=404, detail=f"Repository {name!r} not found")
        runs = [run for run in ops.list_runs(limit=200) if run["repo_name"] == name]
        return {"repo": _public_repo(repo), "runs": runs}

    @app.post("/api/repos/{name}/sync")
    def sync_repo(name: str) -> dict[str, object]:
        return {"repo": _public_repo(ops.sync_repo(name))}

    @app.post("/api/repos/{name}/validate")
    def validate_repo(name: str, execute_detected: bool = False) -> dict[str, object]:
        repo = ops.validate_repo(name, execute_detected=execute_detected)
        return {"repo": _public_repo(repo)}

    @app.post("/api/repos/{name}/run/{profile}")
    def run_profile(
        name: str,
        profile: str,
        dry_run: bool = False,
        execute: bool = False,
    ) -> dict[str, object]:
        try:
            return {"run": ops.run_profile(name, profile, dry_run=dry_run, execute=execute)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs")
    def list_runs(limit: int = 100) -> dict[str, object]:
        runs = ops.list_runs(limit=limit)
        return {"count": len(runs), "runs": runs}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int) -> dict[str, object]:
        run = ops.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return {"run": run}

    return app
