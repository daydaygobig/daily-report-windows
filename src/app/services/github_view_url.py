"""Build public view URLs for GitHub-deployed HTML reports."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import unquote


def build_view_url(record, *, fallback_url: Optional[str] = None) -> Optional[str]:
    """Return the user-facing report URL for a GitHub deployment record."""

    artifact_type = getattr(record, "artifact_type", None) or ("html_report" if getattr(record, "pages_url", None) else None)
    if artifact_type != "html_report":
        return getattr(record, "pages_url", None) or fallback_url

    config = getattr(record, "github_config", None)
    job = getattr(record, "job", None)
    if not config:
        return fallback_url or getattr(record, "pages_url", None)

    mode = getattr(config, "view_url_mode", None) or "github_pages"
    if mode != "custom_template":
        return getattr(record, "pages_url", None) or fallback_url

    template = (getattr(config, "view_url_template", None) or "").strip()
    if not template or not job:
        return getattr(record, "pages_url", None) or fallback_url

    return _ensure_scheme(_render_template(template, record=record, job=job))


def _render_template(template: str, *, record, job) -> str:
    execution = getattr(record, "execution", None)
    task = getattr(record, "task", None) or getattr(job, "task", None)
    repo_path = getattr(record, "repo_path", None) or _infer_repo_path_from_pages_url(record)
    filename = _filename_from_repo_path(repo_path)
    target_dt = _target_datetime(record, job, execution)
    replacements = {
        "{YYYY-MM-DD HH:MM}": target_dt.strftime("%Y-%m-%d %H:%M"),
        "{YYYY-MM-DD}": target_dt.strftime("%Y-%m-%d"),
        "{YYYYMMDD_HHmmss}": target_dt.strftime("%Y%m%d_%H%M%S"),
        "{YYYYMMDD}": target_dt.strftime("%Y%m%d"),
        "{filename}": filename or "",
        "{repo_path}": repo_path or "",
        "{job_id}": str(getattr(job, "id", "") or ""),
        "{task_id}": str(getattr(record, "task_id", None) or getattr(job, "task_id", "") or ""),
        "{execution_id}": str(getattr(record, "execution_id", "") or ""),
        "{job_name}": getattr(job, "name", "") or getattr(record, "job_name", "") or "",
        "{task_name}": getattr(task, "name", "") if task else (getattr(record, "task_name", "") or ""),
    }
    result = template
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)
    return result.strip()


def _target_datetime(record, job, execution) -> datetime:
    base = None
    if execution:
        base = (
            getattr(execution, "finished_at", None)
            or getattr(execution, "started_at", None)
            or getattr(execution, "created_at", None)
        )
    base = base or getattr(record, "finished_at", None) or getattr(record, "started_at", None) or datetime.now()
    if _is_weekly_report(job):
        return base
    return base + timedelta(days=int(getattr(job, "days_offset", 0) or 0))


def _is_weekly_report(job) -> bool:
    return getattr(job, "schedule_type", None) == "weekly_report"


def _filename_from_repo_path(repo_path: Optional[str]) -> Optional[str]:
    if not repo_path:
        return None
    return unquote(PurePosixPath(repo_path).name)


def _infer_repo_path_from_pages_url(record) -> Optional[str]:
    pages_url = getattr(record, "pages_url", None)
    if not pages_url:
        return None
    from urllib.parse import urlparse

    config = getattr(record, "github_config", None)
    if config:
        base = (getattr(config, "pages_base_url", None) or f"https://{config.owner}.github.io/{config.repo}/").strip()
        if not base.endswith("/"):
            base += "/"
        if pages_url.startswith(base):
            return unquote(pages_url[len(base) :].lstrip("/"))
    parsed = urlparse(pages_url)
    fallback_path = parsed.path.lstrip("/")
    if config and getattr(config, "repo", None) and fallback_path.startswith(f"{config.repo}/"):
        fallback_path = fallback_path[len(config.repo) + 1 :]
    return unquote(fallback_path) or None


def _ensure_scheme(url: str) -> str:
    if not url:
        return url
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url.lstrip('/')}"
