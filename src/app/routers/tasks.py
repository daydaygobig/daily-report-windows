"""Routes for tasks and jobs."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.job import JobCreate, JobReorderPayload, JobUpdate
from ..schemas.task import TaskCreate, TaskUpdate
from ..services import execution_service, task_service
from ..scheduler.service import scheduler_service
from ..utils.converters import job_to_dict, task_to_dict
from ..utils.responses import success_response

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/", response_model=dict)
def list_tasks(db: Session = Depends(get_db)):
    tasks = task_service.list_tasks(db)
    return success_response([task.model_dump() for task in tasks])


@router.post("/", response_model=dict)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = task_service.create_task(db, payload)
    db.commit()
    db.refresh(task)
    scheduler_service.trigger_reload()
    data = task_to_dict(task)
    data["jobs"] = [job_to_dict(job) for job in task.jobs]
    return success_response(data, message="任务创建成功")


@router.get("/{task_id}", response_model=dict)
def get_task(task_id: int, db: Session = Depends(get_db)):
    try:
        task = task_service.get_task(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    return success_response(task.model_dump())


@router.put("/{task_id}", response_model=dict)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    try:
        task = task_service.update_task(db, task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    db.commit()
    db.refresh(task)
    scheduler_service.trigger_reload()
    data = task_to_dict(task)
    data["jobs"] = [job_to_dict(job) for job in task.jobs]
    return success_response(data, message="任务更新成功")


@router.delete("/{task_id}", response_model=dict)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    try:
        task_service.delete_task(db, task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    scheduler_service.trigger_reload()
    return success_response(message="任务已删除")


@router.post("/{task_id}/jobs", response_model=dict)
def create_job(task_id: int, payload: JobCreate, db: Session = Depends(get_db)):
    try:
        job = task_service.create_job(db, task_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    db.commit()
    db.refresh(job)
    scheduler_service.trigger_reload()
    return success_response(job_to_dict(job), message="作业创建成功")


@router.put("/jobs/{job_id}", response_model=dict)
def update_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)):
    try:
        job = task_service.update_job(db, job_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    logger.info(
        "Job {job_id} updated via API. execution_time={execution_time} start={start} end={end} schedule={schedule}",
        job_id=job.id,
        execution_time=job.execution_time,
        start=job.start_time,
        end=job.end_time,
        schedule=job.schedule_type,
    )
    db.commit()
    db.refresh(job)
    scheduler_service.trigger_reload()
    return success_response(job_to_dict(job), message="作业更新成功")


@router.delete("/jobs/{job_id}", response_model=dict)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    try:
        task_service.delete_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    scheduler_service.trigger_reload()
    return success_response(message="作业已删除")


@router.post("/{task_id}/jobs/reorder", response_model=dict)
def reorder_jobs(task_id: int, payload: JobReorderPayload, db: Session = Depends(get_db)):
    try:
        jobs = task_service.reorder_jobs(db, task_id, payload.job_ids)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 400, "message": str(exc)}) from exc
    db.commit()
    data = [job_to_dict(job) for job in jobs]
    return success_response(data, message="作业排序已更新")


@router.post("/jobs/{job_id}/run", response_model=dict)
async def run_job(job_id: int, payload: Optional[dict] = None, db: Session = Depends(get_db)):
    selected_topic = None
    if isinstance(payload, dict):
        raw_topic = payload.get("selected_topic")
        if isinstance(raw_topic, str) and raw_topic.strip():
            selected_topic = raw_topic.strip()
    execution_id = await scheduler_service.run_job_immediately(job_id, selected_topic=selected_topic)
    if execution_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "作业不存在或未启用"})
    execution = execution_service.get_execution(db, execution_id)
    payload = execution.model_dump() if execution else {"id": execution_id}
    return success_response(payload, message="作业执行完成")
