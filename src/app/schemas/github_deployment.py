"""Schemas for GitHub deployment records."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .base import ORMBase


class GithubDeploymentOut(ORMBase):
    execution_id: Optional[int]
    job_id: Optional[int]
    task_id: Optional[int]
    github_config_id: Optional[int]
    job_name: Optional[str]
    task_name: Optional[str]
    config_name: Optional[str]
    artifact_type: Optional[str]
    artifact_label: Optional[str]
    repo_full_name: Optional[str]
    branch: Optional[str]
    repo_path: Optional[str]
    github_file_url: Optional[str]
    status: str
    pages_url: Optional[str]
    error_msg: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class GithubDeploymentQuery(BaseModel):
    page: int = 1
    page_size: int = 50
    task_id: Optional[int] = None
    job_id: Optional[int] = None
    config_id: Optional[int] = None
    status: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
