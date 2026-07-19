"""Repository for jobs."""
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.job import Job
from ..utils.converters import serialize_list, serialize_weekdays
from .base import CRUDRepository


class JobRepository(CRUDRepository[Job]):
    def __init__(self) -> None:
        super().__init__(Job)

    @staticmethod
    def _payload(obj_in: dict) -> dict:
        payload = obj_in.copy()
        if "weekdays" in payload and payload["weekdays"] is not None:
            payload["weekdays"] = serialize_weekdays(payload["weekdays"])
        if "message_stats_formats" in payload and payload["message_stats_formats"] is not None:
            payload["message_stats_formats"] = serialize_list(payload["message_stats_formats"])
        if "chatlog_backup_formats" in payload and payload["chatlog_backup_formats"] is not None:
            payload["chatlog_backup_formats"] = serialize_list(payload["chatlog_backup_formats"])
        if "model_output_formats" in payload and payload["model_output_formats"] is not None:
            payload["model_output_formats"] = serialize_list(payload["model_output_formats"])
        execution_time = payload.get("execution_time")
        if not execution_time:
            payload["execution_time"] = payload.get("start_time")
        return payload

    def create_job(self, db: Session, *, obj_in: dict) -> Job:
        return super().create(db, obj_in=self._payload(obj_in))

    def update_job(self, db: Session, *, entity: Job, obj_in: dict) -> Job:
        return super().update(db, entity=entity, obj_in=self._payload(obj_in))

    def get_by_id(self, db: Session, job_id: int) -> Optional[Job]:
        return db.query(Job).filter(Job.id == job_id).first()

    def list_by_task(self, db: Session, task_id: int) -> List[Job]:
        return (
            db.query(Job)
            .filter(Job.task_id == task_id)
            .order_by(Job.display_order.asc(), Job.id.asc())
            .all()
        )

    def list_enabled(self, db: Session) -> List[Job]:
        return db.query(Job).filter(Job.is_enabled.is_(True)).all()

    def get_max_display_order(self, db: Session, task_id: int) -> int:
        value = db.query(func.max(Job.display_order)).filter(Job.task_id == task_id).scalar()
        return int(value) if value is not None else -1
