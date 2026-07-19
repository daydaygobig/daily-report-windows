"""Routes for GitHub deployment records."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..services import github_deployment_service
from ..utils.responses import success_response

router = APIRouter(prefix="/github-deployments", tags=["github"])

_PAGE_SIZES = {10, 20, 50, 100}
_TIME_FMT = "%Y-%m-%d %H:%M"


@router.get("/", response_model=dict)
def list_deployments(
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
    task_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    config_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None, description="YYYY-MM-DD HH:MM"),
    end_time: Optional[str] = Query(None, description="YYYY-MM-DD HH:MM"),
    record_id: Optional[int] = Query(None, description="部署记录 ID"),
    db: Session = Depends(get_db),
):
    if page_size not in _PAGE_SIZES:
        page_size = 50
    start_dt = _parse_time(start_time)
    end_dt = _parse_time(end_time)
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "开始时间不能晚于结束时间"})
    data = github_deployment_service.list_records(
        db,
        page=page,
        page_size=page_size,
        task_id=task_id,
        job_id=job_id,
        config_id=config_id,
        status=status,
        start_time=start_dt,
        end_time=end_dt,
        record_id=record_id,
    )
    return success_response(data)


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, _TIME_FMT)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 1, "message": "时间格式需为 YYYY-MM-DD HH:MM"},
        ) from None
