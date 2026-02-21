"""GitHub API client for fetching releases and tags."""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from shipyard.config.schema import GitHubSettings


@dataclass
class WorkflowRun:
    """A GitHub Actions workflow run."""

    name: str
    status: str  # "in_progress", "queued", "completed"
    conclusion: str | None  # "success", "failure", None if still running
    html_url: str
    created_at: str


@dataclass
class GitHubRelease:
    """A GitHub release."""

    tag_name: str
    name: str
    published_at: str
    prerelease: bool
    draft: bool
    html_url: str
    body: str


class GitHubClient:
    """Async GitHub API client for fetching releases and tags."""

    def __init__(self, settings: GitHubSettings) -> None:
        self._api_base = settings.api_base.rstrip("/")
        token = os.environ.get(settings.token_env, "")
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self._api_base,
            headers=headers,
            timeout=15.0,
        )

    async def get_latest_release(self, repo: str) -> GitHubRelease | None:
        """Get the latest non-draft, non-prerelease release."""
        try:
            resp = await self._client.get(f"/repos/{repo}/releases/latest")
            resp.raise_for_status()
            data = resp.json()
            return GitHubRelease(
                tag_name=data["tag_name"],
                name=data.get("name", data["tag_name"]),
                published_at=data["published_at"],
                prerelease=data["prerelease"],
                draft=data["draft"],
                html_url=data["html_url"],
                body=data.get("body", ""),
            )
        except httpx.HTTPStatusError:
            return None

    async def get_releases(self, repo: str, limit: int = 20) -> list[GitHubRelease]:
        """Get recent releases for a repository."""
        try:
            resp = await self._client.get(
                f"/repos/{repo}/releases",
                params={"per_page": limit},
            )
            resp.raise_for_status()
            return [
                GitHubRelease(
                    tag_name=r["tag_name"],
                    name=r.get("name", r["tag_name"]),
                    published_at=r["published_at"],
                    prerelease=r["prerelease"],
                    draft=r["draft"],
                    html_url=r["html_url"],
                    body=r.get("body", ""),
                )
                for r in resp.json()
            ]
        except httpx.HTTPStatusError:
            return []

    async def get_tags(self, repo: str, limit: int = 20) -> list[str]:
        """Get recent tags for a repository."""
        try:
            resp = await self._client.get(
                f"/repos/{repo}/tags",
                params={"per_page": limit},
            )
            resp.raise_for_status()
            return [t["name"] for t in resp.json()]
        except httpx.HTTPStatusError:
            return []

    async def get_workflow_runs(
        self, repo: str, status: str = "", limit: int = 5
    ) -> list[WorkflowRun]:
        """Fetch recent workflow runs, optionally filtered by status."""
        params: dict[str, str | int] = {"per_page": limit}
        if status:
            params["status"] = status
        try:
            resp = await self._client.get(
                f"/repos/{repo}/actions/runs",
                params=params,
            )
            resp.raise_for_status()
            return [
                WorkflowRun(
                    name=r["name"],
                    status=r["status"],
                    conclusion=r.get("conclusion"),
                    html_url=r["html_url"],
                    created_at=r["created_at"],
                )
                for r in resp.json().get("workflow_runs", [])
            ]
        except httpx.HTTPStatusError:
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
