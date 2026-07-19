"""Repository for IMA sync jobs."""

from __future__ import annotations

from typing import List

from sqlalchemy.orm import Session, joinedload

from ..models.ima_sync_job import ImaSyncJob
from .base import CRUDRepository


class ImaSyncJobRepository(CRUDRepository[ImaSyncJob]):
    def __init__(self) -> None:
        super().__init__(ImaSyncJob)

    def list_all(self, db: Session) -> List[ImaSyncJob]:
        return (
            db.query(ImaSyncJob)
            .options(joinedload(ImaSyncJob.ima_account), joinedload(ImaSyncJob.webhook))
            .order_by(ImaSyncJob.created_at.desc(), ImaSyncJob.id.desc())
            .all()
        )

    def list_enabled(self, db: Session) -> List[ImaSyncJob]:
        return (
            db.query(ImaSyncJob)
            .options(joinedload(ImaSyncJob.ima_account), joinedload(ImaSyncJob.webhook))
            .filter(ImaSyncJob.is_enabled.is_(True))
            .order_by(ImaSyncJob.id.asc())
            .all()
        )
