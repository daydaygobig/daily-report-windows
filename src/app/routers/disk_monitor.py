"""Routes for disk IO monitoring."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.disk_monitor import DiskInspectionJobCreate, DiskInspectionJobUpdate
from ..services import disk_monitor_service
from ..utils.responses import success_response

router = APIRouter(prefix="/disk-monitor", tags=["disk-monitor"])

_TIME_FMT = "%Y-%m-%d %H:%M"
_PAGE_SIZE_CHOICES = {10, 20, 50, 100}


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.strptime(value, _TIME_FMT)


def _trigger_scheduler_reload() -> None:
    from ..scheduler.service import scheduler_service

    scheduler_service.trigger_reload()


@router.get("/records", response_model=dict)
def list_io_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
    execution_id: Optional[int] = Query(None, ge=1),
    task_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    provider: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    is_warning: Optional[bool] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
):
    if page_size not in _PAGE_SIZE_CHOICES:
        page_size = 50
    try:
        data = disk_monitor_service.list_io_records(
            db,
            page=page,
            page_size=page_size,
            execution_id=execution_id,
            task_id=task_id,
            job_id=job_id,
            provider=provider,
            task_type=task_type,
            is_warning=is_warning,
            start_time=_parse_time(start_time),
            end_time=_parse_time(end_time),
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(data)


@router.get("/records/summary", response_model=dict)
def get_summaries(db: Session = Depends(get_db)):
    return success_response([item.model_dump() for item in disk_monitor_service.get_summary_cards(db)])


@router.get("/records/aggregate", response_model=dict)
def get_aggregate(
    start_time: str = Query(...),
    end_time: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        data = disk_monitor_service.get_aggregate(db, start_time=_parse_time(start_time), end_time=_parse_time(end_time))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(data.model_dump())


@router.get("/records/by-execution/{execution_id}", response_model=dict)
def get_record_by_execution(execution_id: int, db: Session = Depends(get_db)):
    record = disk_monitor_service.get_io_record_by_execution(db, execution_id)
    return success_response(record.model_dump() if record else None)


@router.get("/records/{record_id}", response_model=dict)
def get_io_record(record_id: int, db: Session = Depends(get_db)):
    record = disk_monitor_service.get_io_record(db, record_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "磁盘日志不存在"})
    return success_response(record.model_dump())


@router.get("/inspection-jobs", response_model=dict)
def list_inspection_jobs(db: Session = Depends(get_db)):
    return success_response([item.model_dump() for item in disk_monitor_service.list_inspection_jobs(db)])


@router.post("/inspection-jobs", response_model=dict)
def create_inspection_job(payload: DiskInspectionJobCreate, db: Session = Depends(get_db)):
    try:
        item = disk_monitor_service.create_inspection_job(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    db.commit()
    _trigger_scheduler_reload()
    return success_response(item.model_dump())


@router.put("/inspection-jobs/{job_id}", response_model=dict)
def update_inspection_job(job_id: int, payload: DiskInspectionJobUpdate, db: Session = Depends(get_db)):
    try:
        item = disk_monitor_service.update_inspection_job(db, job_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    db.commit()
    _trigger_scheduler_reload()
    return success_response(item.model_dump())


@router.delete("/inspection-jobs/{job_id}", response_model=dict)
def delete_inspection_job(job_id: int, db: Session = Depends(get_db)):
    try:
        disk_monitor_service.delete_inspection_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    db.commit()
    _trigger_scheduler_reload()
    return success_response(None)


@router.post("/inspection-jobs/{job_id}/run", response_model=dict)
async def run_inspection_job(job_id: int, db: Session = Depends(get_db)):
    try:
        run = await disk_monitor_service.run_inspection_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    return success_response(run.model_dump())


@router.get("/inspection-runs", response_model=dict)
def list_inspection_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
    inspection_job_id: Optional[int] = Query(None),
    status_value: Optional[str] = Query(None, alias="status"),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if page_size not in _PAGE_SIZE_CHOICES:
        page_size = 50
    try:
        data = disk_monitor_service.list_inspection_runs(
            db,
            page=page,
            page_size=page_size,
            inspection_job_id=inspection_job_id,
            status=status_value,
            start_time=_parse_time(start_time),
            end_time=_parse_time(end_time),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    return success_response(data)


@router.get("/inspection-runs/{run_id}", response_model=dict)
def get_inspection_run(run_id: int, db: Session = Depends(get_db)):
    run = disk_monitor_service.get_inspection_run(db, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "巡检日志不存在"})
    return success_response(run.model_dump())
