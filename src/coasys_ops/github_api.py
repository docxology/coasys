from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import RepoMetadata


class GitHubClient:
    def __init__(self, token: str | None = None, base_url: str = "https://api.github.com") -> None:
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.base_url = base_url.rstrip("/")

    def _request_json(self, path: str, query: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "coasys-ops-dashboard",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers)
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed GitHub API URL.
            return json.loads(response.read().decode("utf-8"))

    def list_org_repos(self, org: str, limit: int | None = None) -> list[RepoMetadata]:
        repos: list[RepoMetadata] = []
        page = 1
        while True:
            payload = self._request_json(
                f"/orgs/{org}/repos",
                {
                    "type": "public",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 100,
                    "page": page,
                },
            )
            if not payload:
                break
            repos.extend(RepoMetadata.from_github(item) for item in payload)
            if limit is not None and len(repos) >= limit:
                return repos[:limit]
            if len(payload) < 100:
                break
            page += 1
            time.sleep(0.1)
        return repos

    def latest_workflow_run(
        self, full_name: str, branch: str | None = None
    ) -> dict[str, Any] | None:
        query: dict[str, Any] = {"per_page": 1}
        if branch:
            query["branch"] = branch
        try:
            payload = self._request_json(f"/repos/{full_name}/actions/runs", query)
        except HTTPError as exc:
            if exc.code in {403, 404, 409}:
                return None
            raise
        runs = payload.get("workflow_runs") or []
        return runs[0] if runs else None
