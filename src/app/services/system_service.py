"""System-level service helpers."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from ..config import get_settings
from ..db import session_scope
from ..models.execution import Execution
from ..models.job import Job
from ..models.task import Task
from ..scheduler.service import scheduler_service
from ..services import chat_record_service

settings = get_settings()


async def get_system_status() -> dict:
    with session_scope() as db:
        tasks_count = db.query(func.count(Task.id)).scalar() or 0
        jobs_count = db.query(func.count(Job.id)).scalar() or 0
        executions_today = (
            db.query(func.count(Execution.id))
            .filter(Execution.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
            .scalar()
            or 0
        )
        chat_record_status = await chat_record_service.get_status(db)

    next_run = _get_next_run_time()

    return {
        "app_name": settings.app_name,
        "tasks": tasks_count,
        "jobs": jobs_count,
        "chatlog_status": chat_record_status.status,
        "chat_record_provider": chat_record_status.provider,
        "chat_record_status": chat_record_status.status,
        "chat_record_status_message": chat_record_status.message,
        "html_card_engine_enabled": bool(settings.html_card_engine_enabled),
        "html_card_relation_engine": settings.html_card_relation_engine or "svg",
        "next_execution": next_run.isoformat() if next_run else None,
        "executions_today": executions_today,
        "server_time": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
    }


def _get_next_run_time() -> Optional[datetime]:
    jobs = scheduler_service.scheduler.get_jobs() if scheduler_service.scheduler.running else []
    if not jobs:
        return None
    next_times = [job.next_run_time for job in jobs if job.next_run_time]
    return min(next_times) if next_times else None
