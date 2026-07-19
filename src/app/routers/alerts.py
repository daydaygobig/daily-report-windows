"""Routes for alert management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..services import alert_service
from ..utils.responses import success_response

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=dict)
def list_alerts(limit: int = 100, db: Session = Depends(get_db)):
    alerts = alert_service.list_alerts(db, limit=limit)
    return success_response([alert.model_dump() for alert in alerts])


@router.post("/{alert_id}/ack", response_model=dict)
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db)):
    try:
        alert = alert_service.acknowledge_alert(db, alert_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    return success_response(alert.model_dump(), message="已确认告警")
