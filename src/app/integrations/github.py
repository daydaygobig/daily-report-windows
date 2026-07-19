"""Lightweight GitHub REST helpers for Pages deployments."""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional

import httpx
from loguru import logger


API_BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


class GithubAPIError(RuntimeError):
    """Raised when GitHub API returns an error response."""


async def list_accessible_repos(token: str, *, owner_hint: Optional[str], per_page: int = 50) -> dict:
    """Return the authenticated identity and a simplified repo list."""

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        identity = await _request_json(client, token, "GET", "/user") or {}
        repos = await _request_json(
            client,
            token,
            "GET",
            "/user/repos",
            params={"per_page": per_page, "sort": "updated"},
        ) or []

        repo_map: Dict[str, Dict[str, Any]] = {repo["full_name"]: repo for repo in repos if isinstance(repo, dict)}
        owner_hint = (owner_hint or "").strip()
        login = str(identity.get("login") or "")
        if owner_hint and owner_hint.lower() != login.lower():
            try:
                org_repos = await _request_json(
                    client,
                    token,
                    "GET",
                    f"/orgs/{owner_hint}/repos",
                    params={"per_page": per_page, "sort": "updated"},
                )
                if org_repos:
                    for repo in org_repos:
                        if isinstance(repo, dict) and repo.get("full_name"):
                            repo_map[repo["full_name"]] = repo
            except GithubAPIError as exc:
                logger.warning("无法读取组织 %s 的仓库列表：%s", owner_hint, exc)

        simplified = []
        for repo in repo_map.values():
            owner = (repo.get("owner") or {}).get("login")
            name = repo.get("name")
            full_name = repo.get("full_name")
            if not owner or not name or not full_name:
                continue
            simplified.append(
                {
                    "owner": owner,
                    "repo": name,
                    "full_name": full_name,
                    "default_branch": repo.get("default_branch") or "main",
                    "private": bool(repo.get("private")),
                    "pages_base_url": _build_pages_base_url(owner, name),
                }
            )
        return {"login": login, "repos": simplified}


async def upload_html_file(
    token: str,
    *,
    owner: str,
    repo: str,
    branch: str,
    path: str,
    content: str,
    commit_message: str,
    ) -> Dict[str, Any]:
    """Create or update an HTML file via the contents API."""

    normalized_path = path.lstrip("/")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        existing = await _request_json(
            client,
            token,
            "GET",
            f"/repos/{owner}/{repo}/contents/{normalized_path}",
            params={"ref": branch},
            allow_404=True,
        )
        sha = None
        if isinstance(existing, dict):
            sha = existing.get("sha")

        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        response = await _request_json(
            client,
            token,
            "PUT",
            f"/repos/{owner}/{repo}/contents/{normalized_path}",
            json=payload,
        )
        return response or {}


async def upload_text_file(
    token: str,
    *,
    owner: str,
    repo: str,
    branch: str,
    path: str,
    content: str,
    commit_message: str,
) -> Dict[str, Any]:
    """Create or update a text-based file via the contents API."""

    normalized_path = path.lstrip("/")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        existing = await _request_json(
            client,
            token,
            "GET",
            f"/repos/{owner}/{repo}/contents/{normalized_path}",
            params={"ref": branch},
            allow_404=True,
        )
        sha = None
        if isinstance(existing, dict):
            sha = existing.get("sha")

        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        response = await _request_json(
            client,
            token,
            "PUT",
            f"/repos/{owner}/{repo}/contents/{normalized_path}",
            json=payload,
        )
        return response or {}


def _build_pages_base_url(owner: str, repo: str) -> str:
    base = f"https://{owner}.github.io/{repo}/"
    return base


async def _request_json(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    allow_404: bool = False,
) -> Any:
    response = await client.request(
        method,
        f"{API_BASE_URL}{path}",
        params=params,
        json=json,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "TraeScheduler/1.0",
        },
    )
    if allow_404 and response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise GithubAPIError(f"{response.status_code} {response.text.strip()}")
    if response.status_code == 204:
        return {}
    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover - GitHub always returns JSON
        raise GithubAPIError("GitHub 返回了非 JSON 响应") from exc
