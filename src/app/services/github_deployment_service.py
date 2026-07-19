"""Service helpers for GitHub deployment records."""

from datetime import datetime
from typing import Optional
from urllib.parse import quote, unquote, urlparse

from sqlalchemy.orm import Session

from ..models.github_deployment import GithubDeployment
from ..repositories.github_deployment_repo import GithubDeploymentRepository
from ..schemas.github_deployment import GithubDeploymentOut
from .github_view_url import build_view_url

repo = GithubDeploymentRepository()


def create_record(
    db: Session,
    *,
    execution_id: Optional[int],
    job_id: Optional[int],
    task_id: Optional[int],
    github_config_id: Optional[int],
    job_name: Optional[str],
    task_name: Optional[str],
    config_name: Optional[str],
) -> GithubDeployment:
    record = GithubDeployment(
        execution_id=execution_id,
        job_id=job_id,
        task_id=task_id,
        github_config_id=github_config_id,
        job_name=job_name,
        task_name=task_name,
        config_name=config_name,
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(record)
    db.flush()
    return record


def list_records(
    db: Session,
    *,
    page: int,
    page_size: int,
    task_id: Optional[int],
    job_id: Optional[int],
    config_id: Optional[int],
    status: Optional[str],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    record_id: Optional[int],
) -> dict:
    total, items = repo.list_paginated(
        db,
        page=page,
        page_size=page_size,
        task_id=task_id,
        job_id=job_id,
        config_id=config_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
        record_id=record_id,
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_record_to_dict(item) for item in items],
    }


def _record_to_dict(record: GithubDeployment) -> dict:
    repo_path = record.repo_path or _infer_repo_path_from_pages_url(record)
    repo_full_name = record.repo_full_name or _repo_full_name(record)
    branch = record.branch or _branch(record)
    github_file_url = record.github_file_url or _build_github_file_url(repo_full_name, branch, repo_path)
    artifact_type = record.artifact_type or ("html_report" if record.pages_url else None)
    artifact_label = record.artifact_label or ("HTML 日报" if artifact_type == "html_report" else None)
    view_url = build_view_url(record, fallback_url=record.pages_url)
    return GithubDeploymentOut.model_validate(record).model_copy(
        update={
            "artifact_type": artifact_type,
            "artifact_label": artifact_label,
            "repo_full_name": repo_full_name,
            "branch": branch,
            "repo_path": repo_path,
            "github_file_url": github_file_url,
            "pages_url": view_url,
        }
    ).model_dump()


def _repo_full_name(record: GithubDeployment) -> Optional[str]:
    config = record.github_config
    if config and config.owner and config.repo:
        return f"{config.owner}/{config.repo}"
    return None


def _branch(record: GithubDeployment) -> Optional[str]:
    config = record.github_config
    if config and config.branch:
        return config.branch
    return "main" if record.pages_url else None


def _build_github_file_url(repo_full_name: Optional[str], branch: Optional[str], repo_path: Optional[str]) -> Optional[str]:
    if not repo_full_name or not branch or not repo_path:
        return None
    encoded_branch = quote(branch.strip(), safe="")
    encoded_path = quote(repo_path.strip("/"), safe="/")
    return f"https://github.com/{repo_full_name}/blob/{encoded_branch}/{encoded_path}"


def _infer_repo_path_from_pages_url(record: GithubDeployment) -> Optional[str]:
    if not record.pages_url:
        return None
    config = record.github_config
    if config:
        base = (config.pages_base_url or f"https://{config.owner}.github.io/{config.repo}/").strip()
        if not base.endswith("/"):
            base += "/"
        if record.pages_url.startswith(base):
            return unquote(record.pages_url[len(base) :].lstrip("/"))

    parsed = urlparse(record.pages_url)
    fallback_path = parsed.path.lstrip("/")
    if config and config.repo and fallback_path.startswith(f"{config.repo}/"):
        fallback_path = fallback_path[len(config.repo) + 1 :]
    return unquote(fallback_path) or None
