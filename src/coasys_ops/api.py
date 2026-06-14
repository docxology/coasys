from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .ops import CoasysOps
from .weave.deploy import deploy_readiness as weave_deploy_readiness
from .weave.export import json_schema as weave_json_schema
from .weave.export import operation_plan as weave_operation_plan
from .weave.graph import build_graph as weave_build_graph
from .weave.graph import to_mermaid as weave_to_mermaid
from .weave.loader import document_to_mapping, load_document, parse_document
from .weave.seed import render_seed as weave_render_seed
from .weave.validate import validate_document as weave_validate
from .weave.writer import save_document as weave_save_document

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

    # ----------------------------------------------------------------- Weave
    weave_root = root or Path.cwd()

    @app.get("/api/weave/document")
    def weave_document() -> dict[str, object]:
        document = load_document(weave_root)
        issues = weave_validate(document)
        return {
            "document": document_to_mapping(document),
            "issues": [issue.to_dict() for issue in issues],
            "targets": document.targets(),
        }

    @app.post("/api/weave/document")
    def weave_save(payload: Annotated[dict, Body()] = None) -> dict[str, object]:
        """Validate-gated save-back. Writes only when there are no errors."""
        payload = payload or {}
        try:
            document = parse_document(payload)
        except Exception as exc:  # noqa: BLE001 - surface parse errors to the editor
            return {"ok": False, "saved": False, "parse_error": str(exc), "issues": []}
        issues = weave_validate(document)
        issue_dicts = [issue.to_dict() for issue in issues]
        if any(i.level == "error" for i in issues):
            return {"ok": False, "saved": False, "issues": issue_dicts}
        path = weave_save_document(document, root=weave_root)
        return {"ok": True, "saved": True, "issues": issue_dicts, "path": str(path)}

    @app.get("/api/weave/schema")
    def weave_schema() -> dict[str, object]:
        return weave_json_schema()

    @app.get("/api/weave/graph")
    def weave_graph() -> dict[str, object]:
        return weave_build_graph(load_document(weave_root)).to_dict()

    @app.get("/api/weave/graph.mmd")
    def weave_graph_mermaid() -> PlainTextResponse:
        return PlainTextResponse(weave_to_mermaid(load_document(weave_root)))

    @app.get("/api/weave/plan")
    def weave_plan(profile: str = "build") -> dict[str, object]:
        return weave_operation_plan(load_document(weave_root), profile)

    @app.get("/api/weave/deploy-check")
    def weave_deploy_check(environment: str | None = None) -> dict[str, object]:
        return weave_deploy_readiness(load_document(weave_root), environment=environment)

    @app.get("/api/weave/seed/{name}")
    def weave_seed(name: str) -> dict[str, object]:
        try:
            return weave_render_seed(load_document(weave_root), name)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/weave/validate")
    def weave_validate_payload(payload: Annotated[dict, Body()] = None) -> dict[str, object]:
        payload = payload or {}
        try:
            document = parse_document(payload)
        except Exception as exc:  # noqa: BLE001 - surface parse errors to the editor
            return {"ok": False, "parse_error": str(exc), "issues": []}
        issues = weave_validate(document)
        return {
            "ok": not any(i.level == "error" for i in issues),
            "issues": [issue.to_dict() for issue in issues],
        }

    return app
