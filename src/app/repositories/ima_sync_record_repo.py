"""Repository for IMA sync records."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models.ima_sync_record import ImaSyncRecord
from .base import CRUDRepository


class ImaSyncRecordRepository(CRUDRepository[ImaSyncRecord]):
    def __init__(self) -> None:
        super().__init__(ImaSyncRecord)

    def _apply_filters(
        self,
        base_query,
        *,
        ima_account_id: Optional[int] = None,
        task_id: Optional[int] = None,
        job_id: Optional[int] = None,
        sync_job_id: Optional[int] = None,
        sync_scope: Optional[str] = None,
        status: Optional[str] = None,
        trigger_type: Optional[str] = None,
        execution_id: Optional[int] = None,
        batch_id: Optional[str] = None,
        query: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ):
        if ima_account_id is not None:
            base_query = base_query.filter(ImaSyncRecord.ima_account_id == ima_account_id)
        if task_id is not None:
            base_query = base_query.filter(ImaSyncRecord.task_id == task_id)
        if job_id is not None:
            base_query = base_query.filter(ImaSyncRecord.job_id == job_id)
        if sync_job_id is not None:
            base_query = base_query.filter(ImaSyncRecord.sync_job_id == sync_job_id)
        if sync_scope == "ima_sync_job":
            base_query = base_query.filter(ImaSyncRecord.sync_job_id.isnot(None))
        elif sync_scope == "daily_report_job":
            base_query = base_query.filter(ImaSyncRecord.sync_job_id.is_(None))
        if status:
            base_query = base_query.filter(ImaSyncRecord.status == status)
        if trigger_type:
            base_query = base_query.filter(ImaSyncRecord.trigger_type == trigger_type)
        if execution_id is not None:
            base_query = base_query.filter(ImaSyncRecord.execution_id == execution_id)
        if batch_id:
            base_query = base_query.filter(ImaSyncRecord.batch_id == batch_id)
        if start_time is not None:
            base_query = base_query.filter(ImaSyncRecord.created_at >= start_time)
        if end_time is not None:
            base_query = base_query.filter(ImaSyncRecord.created_at <= end_time)
        if query:
            like_query = f"%{query}%"
            base_query = base_query.filter(
                or_(
                    ImaSyncRecord.source_name.like(like_query),
                    ImaSyncRecord.source_path.like(like_query),
                    ImaSyncRecord.ima_account_name.like(like_query),
                    ImaSyncRecord.knowledge_base_name.like(like_query),
                    ImaSyncRecord.note_folder_name.like(like_query),
                    ImaSyncRecord.error_explanation.like(like_query),
                    ImaSyncRecord.error_message.like(like_query),
                )
            )
        return base_query

    def list_paginated(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        ima_account_id: Optional[int] = None,
        task_id: Optional[int] = None,
        job_id: Optional[int] = None,
        sync_job_id: Optional[int] = None,
        sync_scope: Optional[str] = None,
        status: Optional[str] = None,
        trigger_type: Optional[str] = None,
        execution_id: Optional[int] = None,
        batch_id: Optional[str] = None,
        query: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Tuple[int, List[ImaSyncRecord]]:
        base_query = self._apply_filters(
            db.query(ImaSyncRecord),
            ima_account_id=ima_account_id,
            task_id=task_id,
            job_id=job_id,
            sync_job_id=sync_job_id,
            sync_scope=sync_scope,
            status=status,
            trigger_type=trigger_type,
            execution_id=execution_id,
            batch_id=batch_id,
            query=query,
            start_time=start_time,
            end_time=end_time,
        )
        total = base_query.count()
        items = (
            base_query
            .options(
                joinedload(ImaSyncRecord.ima_account),
                joinedload(ImaSyncRecord.sync_job),
                joinedload(ImaSyncRecord.task),
                joinedload(ImaSyncRecord.job),
            )
            .order_by(ImaSyncRecord.created_at.desc(), ImaSyncRecord.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return total, items

    def list_all_filtered(
        self,
        db: Session,
        *,
        ima_account_id: Optional[int] = None,
        task_id: Optional[int] = None,
        job_id: Optional[int] = None,
        sync_job_id: Optional[int] = None,
        sync_scope: Optional[str] = None,
        status: Optional[str] = None,
        trigger_type: Optional[str] = None,
        execution_id: Optional[int] = None,
        batch_id: Optional[str] = None,
        query: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[ImaSyncRecord]:
        return (
            self._apply_filters(
                db.query(ImaSyncRecord),
                ima_account_id=ima_account_id,
                task_id=task_id,
                job_id=job_id,
                sync_job_id=sync_job_id,
                sync_scope=sync_scope,
                status=status,
                trigger_type=trigger_type,
                execution_id=execution_id,
                batch_id=batch_id,
                query=query,
                start_time=start_time,
                end_time=end_time,
            )
            .options(
                joinedload(ImaSyncRecord.ima_account),
                joinedload(ImaSyncRecord.sync_job),
                joinedload(ImaSyncRecord.task),
                joinedload(ImaSyncRecord.job),
            )
            .order_by(ImaSyncRecord.created_at.desc(), ImaSyncRecord.id.desc())
            .all()
        )

    def find_existing_completed(
        self,
        db: Session,
        *,
        source_path: str,
        source_size: Optional[int],
        source_mtime: Optional[datetime],
        target_type: str,
        note_folder_id: Optional[str],
        knowledge_base_id: Optional[str],
        knowledge_folder_id: Optional[str],
    ) -> Optional[ImaSyncRecord]:
        query = (
            db.query(ImaSyncRecord)
            .filter(ImaSyncRecord.source_path == source_path)
            .filter(ImaSyncRecord.target_type == target_type)
            .filter(ImaSyncRecord.status.in_(["success", "skipped"]))
        )
        if source_size is not None:
            query = query.filter(ImaSyncRecord.source_size == source_size)
        if source_mtime is not None:
            query = query.filter(ImaSyncRecord.source_mtime == source_mtime)
        if target_type == "note":
            query = query.filter(ImaSyncRecord.note_folder_id == note_folder_id)
        else:
            query = query.filter(ImaSyncRecord.knowledge_base_id == knowledge_base_id)
            query = query.filter(ImaSyncRecord.knowledge_folder_id == knowledge_folder_id)
        return query.order_by(ImaSyncRecord.id.desc()).first()

    def list_by_batch(self, db: Session, batch_id: str) -> List[ImaSyncRecord]:
        return (
            db.query(ImaSyncRecord)
            .filter(ImaSyncRecord.batch_id == batch_id)
            .options(
                joinedload(ImaSyncRecord.ima_account),
                joinedload(ImaSyncRecord.sync_job),
                joinedload(ImaSyncRecord.task),
                joinedload(ImaSyncRecord.job),
            )
            .order_by(ImaSyncRecord.id.asc())
            .all()
        )
