"""Repository for executions."""

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models.execution import Execution
from ..models.job import Job
from .base import CRUDRepository


class ExecutionRepository(CRUDRepository[Execution]):
    def __init__(self) -> None:
        super().__init__(Execution)

    def list_recent(self, db: Session, *, limit: int = 50) -> List[Execution]:
        return (
            db.query(Execution)
            .options(joinedload(Execution.job).joinedload(Job.task))
            .order_by(Execution.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_paginated(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        execution_id: Optional[int] = None,
        task_id: Optional[int] = None,
        job_id: Optional[int] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[int, List[Execution]]:
        base_query = db.query(Execution)

        if execution_id is not None:
            base_query = base_query.filter(Execution.id == execution_id)
        if task_id is not None:
            job_ids_for_task = db.query(Job.id).filter(Job.task_id == task_id)
            base_query = base_query.filter(
                or_(
                    Execution.task_id == task_id,
                    Execution.job_id.in_(job_ids_for_task),
                )
            )
        if job_id is not None:
            base_query = base_query.filter(Execution.job_id == job_id)
        if status:
            base_query = base_query.filter(Execution.status == status)
        if start_time is not None:
            base_query = base_query.filter(Execution.started_at >= start_time)
        if end_time is not None:
            base_query = base_query.filter(Execution.started_at <= end_time)

        total = base_query.count()

        items = (
            base_query.options(joinedload(Execution.job).joinedload(Job.task))
            .order_by(Execution.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return total, items
