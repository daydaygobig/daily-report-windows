"""Alert management service."""

import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.alert import Alert
from ..repositories.alert_repo import AlertRepository
from ..schemas.alert import AlertOut

alert_repo = AlertRepository()


def _alert_to_dict(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "task_id": alert.task_id,
        "job_id": alert.job_id,
        "execution_id": getattr(alert, "execution_id", None),
        "level": alert.level,
        "category": alert.category,
        "message": alert.message,
        "payload": json.loads(alert.payload) if alert.payload else None,
        "acknowledged": alert.acknowledged,
        "acknowledged_at": alert.acknowledged_at,
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
    }


def list_alerts(db: Session, limit: int = 100) -> List[AlertOut]:
    alerts = alert_repo.list_unacknowledged(db, limit=limit)
    return [AlertOut.model_validate(_alert_to_dict(alert)) for alert in alerts]


def acknowledge_alert(db: Session, alert_id: int) -> AlertOut:
    alert = alert_repo.get(db, alert_id)
    if not alert:
        raise ValueError("告警不存在")
    alert.acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    db.add(alert)
    db.flush()
    return AlertOut.model_validate(_alert_to_dict(alert))


def create_alert(
    db: Session,
    *,
    task_id: Optional[int],
    job_id: Optional[int],
    execution_id: Optional[int] = None,
    category: str,
    message: str,
    level: str = "error",
    payload: Optional[Dict] = None,
) -> Alert:
    alert = Alert(
        task_id=task_id,
        job_id=job_id,
        execution_id=execution_id,
        category=category,
        message=message,
        level=level,
        payload=None if payload is None else json.dumps(payload, ensure_ascii=False),
    )
    db.add(alert)
    db.flush()
    return alert
