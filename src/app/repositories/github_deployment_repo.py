"""Repository for GitHub deployment records."""

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from ..models.github_deployment import GithubDeployment
from ..models.job import Job
from .base import CRUDRepository


class GithubDeploymentRepository(CRUDRepository[GithubDeployment]):
    def __init__(self) -> None:
        super().__init__(GithubDeployment)

    def list_paginated(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        task_id: Optional[int] = None,
        job_id: Optional[int] = None,
        config_id: Optional[int] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        record_id: Optional[int] = None,
    ) -> Tuple[int, List[GithubDeployment]]:
        query = db.query(GithubDeployment)
        if record_id:
            query = query.filter(GithubDeployment.id == record_id)
        if task_id:
            query = query.filter(GithubDeployment.task_id == task_id)
        if job_id:
            query = query.filter(GithubDeployment.job_id == job_id)
        if config_id:
            query = query.filter(GithubDeployment.github_config_id == config_id)
        if status:
            query = query.filter(GithubDeployment.status == status)
        if start_time:
            query = query.filter(GithubDeployment.started_at >= start_time)
        if end_time:
            query = query.filter(GithubDeployment.started_at <= end_time)

        total = query.count()
        items = (
            query.options(
                joinedload(GithubDeployment.github_config),
                joinedload(GithubDeployment.job).joinedload(Job.task),
                joinedload(GithubDeployment.task),
            )
            .order_by(GithubDeployment.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return total, items
