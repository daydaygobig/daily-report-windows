"""Routes for execution history."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..services import execution_service
from ..utils.responses import success_response

router = APIRouter(prefix="/executions", tags=["executions"])

_TIME_FMT = "%Y-%m-%d %H:%M"
_PAGE_SIZE_CHOICES = {10, 20, 50, 100}


@router.get("/", response_model=dict)
def list_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
    execution_id: Optional[int] = Query(None, ge=1),
    task_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None, description="YYYY-MM-DD HH:MM"),
    end_time: Optional[str] = Query(None, description="YYYY-MM-DD HH:MM"),
    db: Session = Depends(get_db),
):
    if page_size not in _PAGE_SIZE_CHOICES:
        page_size = 50

    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None

    try:
        if start_time:
            start_dt = datetime.strptime(start_time, _TIME_FMT)
        if end_time:
            end_dt = datetime.strptime(end_time, _TIME_FMT)
    except ValueError as exc:  # pragma: no cover - invalid user input
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "时间格式需为 YYYY-MM-DD HH:MM"}) from exc

    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "开始时间不能晚于结束时间"})

    data = execution_service.list_executions_paginated(
        db,
        page=page,
        page_size=page_size,
        execution_id=execution_id,
        task_id=task_id,
        job_id=job_id,
        status=status,
        start_time=start_dt,
        end_time=end_dt,
    )
    return success_response(data)


@router.get("/{execution_id}", response_model=dict)
def get_execution_detail(execution_id: int, db: Session = Depends(get_db)):
    execution = execution_service.get_execution(db, execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "执行记录不存在"})
    return success_response(execution.model_dump())
