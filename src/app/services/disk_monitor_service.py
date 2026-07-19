"""Disk IO monitoring service."""

from __future__ import annotations

import csv
import ctypes
import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..config import get_settings
from ..integrations import feishu
from ..models.chat_record_setting import ChatRecordSetting
from ..models.disk_monitor import DiskInspectionJob, DiskInspectionRun, DiskIoRecord
from ..models.execution import Execution
from ..models.job import Job
from ..models.task import Task
from ..repositories.webhook_repo import WebhookRepository
from ..schemas.disk_monitor import (
    DiskIoAggregateOut,
    DiskIoAggregateSummary,
    DiskIoMonthlyTrendItem,
    DiskIoTaskRankingItem,
    DiskInspectionJobCreate,
    DiskInspectionJobOut,
    DiskInspectionJobUpdate,
    DiskInspectionRunOut,
    DiskIoRecordOut,
    DiskIoSummary,
)
from ..utils.interval_schedule import compute_next_interval_plan

DEFAULT_WARNING_BYTES = 100 * 1024 * 1024
CHATLOG_DECRYPT_REFERENCE_BYTES = 1024 * 1024 * 1024
DEFAULT_WEFLOW_PROCESS_NAMES = ["weflow.exe", "WeFlow.exe"]
webhook_repo = WebhookRepository()
settings = get_settings()
SERVICE_TZ = ZoneInfo(settings.timezone)


@dataclass
class IoSnapshot:
    read_bytes: int
    write_bytes: int


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


def start_execution_io(db: Session, *, execution: Execution, task: Task, job: Job) -> dict:
    provider = _current_provider(db)
    backend = _snapshot_pid(os.getpid())
    weflow_pids = _resolve_weflow_pids(db) if provider == "weflow" else []
    weflow = _sum_snapshots(weflow_pids)
    sampled_at = datetime.now()
    return {
        "provider": provider,
        "backend": backend.__dict__ if backend else None,
        "weflow": weflow.__dict__ if weflow else None,
        "weflow_pids": weflow_pids,
        "weflow_process": ",".join(str(pid) for pid in weflow_pids) if weflow_pids else None,
        "io_started_at": sampled_at.isoformat(sep=" "),
        "started_at": execution.started_at.isoformat(sep=" ") if execution.started_at else None,
        "task_id": task.id,
        "job_id": job.id,
    }


def finish_execution_io(
    db: Session,
    *,
    context: Optional[dict],
    execution: Execution,
    task: Task,
    job: Job,
    exported_files: Iterable[dict[str, Any]],
    chat_record_telemetry: Optional[dict] = None,
) -> DiskIoRecord:
    context = context or {}
    chat_record_telemetry = chat_record_telemetry or {}
    provider = context.get("provider") or _current_provider(db)
    backend_end = _snapshot_pid(os.getpid())
    backend_start = _snapshot_from_dict(context.get("backend"))
    weflow_pids = context.get("weflow_pids") or []
    weflow_end = _sum_snapshots([int(pid) for pid in weflow_pids]) if weflow_pids else None
    weflow_start = _snapshot_from_dict(context.get("weflow"))

    backend_read, backend_write = _delta(backend_start, backend_end)
    weflow_read, weflow_write = _delta(weflow_start, weflow_end)
    exported_bytes = _sum_exported_file_bytes(exported_files)
    chatlog_write, chatlog_meta = _estimate_chatlog_decrypt_write_bytes(
        db,
        provider=provider,
        telemetry=chat_record_telemetry,
        since=_parse_context_time(context.get("io_started_at") or context.get("started_at")),
    )
    chatlog_status = chatlog_meta.get("status")
    chatlog_work_dir = chatlog_meta.get("work_dir")
    disk_write_bytes = exported_bytes + chatlog_write
    total_read = max(backend_read or 0, 0) + max(weflow_read or 0, 0)
    total_write = max(backend_write or 0, 0) + max(weflow_write or 0, 0)
    warning_threshold, warning_threshold_source = _disk_warning_threshold_for_job(job)
    is_warning = disk_write_bytes >= warning_threshold
    warning_reason = None
    if is_warning:
        warning_reason = "磁盘写入超过作业告警阈值" if warning_threshold_source == "job" else "磁盘写入超过默认阈值"
    raw_snapshot = {
        "backend_start": context.get("backend"),
        "backend_end": backend_end.__dict__ if backend_end else None,
        "weflow_start": context.get("weflow"),
        "weflow_end": weflow_end.__dict__ if weflow_end else None,
        "weflow_pids": weflow_pids,
        "chatlog_decrypt": chatlog_meta,
    }
    record = DiskIoRecord(
        execution_id=execution.id,
        task_id=task.id,
        job_id=job.id,
        task_name=task.name,
        job_name=job.name,
        task_type=getattr(task, "task_type", "report") or "report",
        is_manual=bool(execution.is_manual),
        provider=provider,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
        duration_ms=execution.duration_ms,
        backend_read_bytes=backend_read,
        backend_write_bytes=backend_write,
        weflow_read_bytes=weflow_read,
        weflow_write_bytes=weflow_write,
        weflow_captured=bool(weflow_start and weflow_end),
        weflow_process=context.get("weflow_process"),
        exported_file_bytes=exported_bytes,
        chatlog_decrypt_write_bytes=chatlog_write,
        chatlog_decrypt_status=chatlog_status,
        chatlog_work_dir=chatlog_work_dir,
        disk_write_bytes=disk_write_bytes,
        total_read_bytes=total_read,
        total_write_bytes=total_write,
        media_enabled=False,
        is_warning=is_warning,
        warning_reason=warning_reason,
        job_alert_threshold_bytes=0,
        job_alert_triggered=False,
        job_alert_sent=False,
        job_alert_error=None,
        raw_snapshot=json.dumps(raw_snapshot, ensure_ascii=False),
    )
    db.add(record)
    db.flush()
    return record


def list_io_records(
    db: Session,
    *,
    page: int,
    page_size: int,
    execution_id: Optional[int] = None,
    task_id: Optional[int] = None,
    job_id: Optional[int] = None,
    provider: Optional[str] = None,
    task_type: Optional[str] = None,
    is_warning: Optional[bool] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
) -> dict:
    query = db.query(DiskIoRecord)
    if execution_id:
        query = query.filter(DiskIoRecord.execution_id == execution_id)
    if task_id:
        query = query.filter(DiskIoRecord.task_id == task_id)
    if job_id:
        query = query.filter(DiskIoRecord.job_id == job_id)
    if provider:
        query = query.filter(DiskIoRecord.provider == provider)
    if task_type:
        query = query.filter(DiskIoRecord.task_type == task_type)
    if is_warning is not None:
        query = query.filter(DiskIoRecord.is_warning == is_warning)
    if start_time:
        query = query.filter(DiskIoRecord.finished_at >= start_time)
    if end_time:
        query = query.filter(DiskIoRecord.finished_at <= end_time)
    total = query.count()
    if sort_by in {"disk_write_bytes", "exported_file_bytes"}:
        order_col = DiskIoRecord.disk_write_bytes.asc() if sort_order == "asc" else DiskIoRecord.disk_write_bytes.desc()
        query = query.order_by(order_col, DiskIoRecord.finished_at.desc().nullslast(), DiskIoRecord.id.desc())
    else:
        query = query.order_by(DiskIoRecord.finished_at.desc().nullslast(), DiskIoRecord.id.desc())
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_record_to_schema(item) for item in items], "total": total, "page": page, "page_size": page_size}


def get_io_record(db: Session, record_id: int) -> Optional[DiskIoRecordOut]:
    record = db.query(DiskIoRecord).filter(DiskIoRecord.id == record_id).first()
    return _record_to_schema(record) if record else None


def get_io_record_by_execution(db: Session, execution_id: int) -> Optional[DiskIoRecordOut]:
    record = (
        db.query(DiskIoRecord)
        .filter(DiskIoRecord.execution_id == execution_id)
        .order_by(DiskIoRecord.id.desc())
        .first()
    )
    return _record_to_schema(record) if record else None


def list_inspection_jobs(db: Session) -> List[DiskInspectionJobOut]:
    return [_job_to_schema(job) for job in db.query(DiskInspectionJob).order_by(DiskInspectionJob.id.desc()).all()]


def list_enabled_inspection_jobs(db: Session) -> List[DiskInspectionJob]:
    return (
        db.query(DiskInspectionJob)
        .filter(DiskInspectionJob.is_enabled.is_(True), DiskInspectionJob.schedule_type != "manual")
        .all()
    )


def create_inspection_job(db: Session, payload: DiskInspectionJobCreate) -> DiskInspectionJobOut:
    job = DiskInspectionJob(**_job_payload(payload))
    db.add(job)
    db.flush()
    return _job_to_schema(job)


def update_inspection_job(db: Session, job_id: int, payload: DiskInspectionJobUpdate) -> DiskInspectionJobOut:
    job = db.query(DiskInspectionJob).filter(DiskInspectionJob.id == job_id).first()
    if not job:
        raise ValueError("巡检任务不存在")
    for key, value in _job_payload(payload).items():
        setattr(job, key, value)
    db.add(job)
    db.flush()
    return _job_to_schema(job)


def delete_inspection_job(db: Session, job_id: int) -> None:
    job = db.query(DiskInspectionJob).filter(DiskInspectionJob.id == job_id).first()
    if not job:
        raise ValueError("巡检任务不存在")
    db.delete(job)


async def run_inspection_job(db: Session, job_id: int) -> DiskInspectionRunOut:
    job = db.query(DiskInspectionJob).filter(DiskInspectionJob.id == job_id).first()
    if not job:
        raise ValueError("巡检任务不存在")
    run = await _run_inspection(db, job)
    return _run_to_schema(run)


async def run_scheduled_inspection(job_id: int) -> None:
    from ..db import session_scope

    with session_scope() as db:
        job = db.query(DiskInspectionJob).filter(DiskInspectionJob.id == job_id, DiskInspectionJob.is_enabled.is_(True)).first()
        if not job:
            return
        await _run_inspection(db, job)


def list_inspection_runs(
    db: Session,
    *,
    page: int,
    page_size: int,
    inspection_job_id: Optional[int] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    query = db.query(DiskInspectionRun)
    if inspection_job_id:
        query = query.filter(DiskInspectionRun.inspection_job_id == inspection_job_id)
    if status:
        query = query.filter(DiskInspectionRun.status == status)
    if start_time:
        query = query.filter(DiskInspectionRun.inspected_at >= start_time)
    if end_time:
        query = query.filter(DiskInspectionRun.inspected_at <= end_time)
    total = query.count()
    items = (
        query.order_by(DiskInspectionRun.inspected_at.desc(), DiskInspectionRun.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": [_run_to_schema(item) for item in items], "total": total, "page": page, "page_size": page_size}


def get_inspection_run(db: Session, run_id: int) -> Optional[DiskInspectionRunOut]:
    run = db.query(DiskInspectionRun).filter(DiskInspectionRun.id == run_id).first()
    return _run_to_schema(run) if run else None


def build_trigger(job: DiskInspectionJob) -> Optional[CronTrigger]:
    if job.schedule_type == "manual" or bool(getattr(job, "interval_enabled", False)):
        return None
    hour, minute = [int(part) for part in (job.schedule_time or "09:00").split(":")]
    if job.schedule_type == "daily":
        return CronTrigger(hour=hour, minute=minute)
    if job.schedule_type == "weekly":
        weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        weekday = int(job.schedule_weekday or 0)
        return CronTrigger(day_of_week=weekdays[max(0, min(6, weekday))], hour=hour, minute=minute)
    if job.schedule_type == "monthly":
        day = max(1, min(31, int(job.schedule_month_day or 1)))
        return CronTrigger(day=day, hour=hour, minute=minute)
    if job.schedule_type == "custom_cron" and job.cron_expression:
        return CronTrigger.from_crontab(job.cron_expression)
    return None


def get_next_run_at(job: DiskInspectionJob, *, now: Optional[datetime] = None) -> Optional[datetime]:
    if not getattr(job, "is_enabled", False) or job.schedule_type == "manual":
        return None
    if not bool(getattr(job, "interval_enabled", False)):
        return None
    interval_minutes = int(getattr(job, "interval_minutes", 0) or 0)
    if interval_minutes <= 0:
        return None
    search_start = now.astimezone(SERVICE_TZ) if now and now.tzinfo else (now.replace(tzinfo=SERVICE_TZ) if now else datetime.now(tz=SERVICE_TZ))
    plan = compute_next_interval_plan(
        search_start=search_start,
        interval_minutes=interval_minutes,
        window_start_minutes=_time_to_minutes(getattr(job, "window_start", None) or "00:00"),
        window_end_minutes=_time_to_minutes(getattr(job, "window_end", None) or "24:00"),
        tz=SERVICE_TZ,
        date_allowed=lambda day: _is_inspection_date_allowed(job, day),
        first_fire_minutes=_time_to_minutes(getattr(job, "window_start", None) or "00:00"),
        max_days=60,
    )
    return plan.fire_time if plan else None


def update_next_run(db: Session, job_id: int, next_run_at: Optional[datetime]) -> None:
    job = db.query(DiskInspectionJob).filter(DiskInspectionJob.id == job_id).first()
    if job:
        job.next_run_at = next_run_at.replace(tzinfo=None) if next_run_at else None
        db.add(job)
        db.flush()


async def _run_inspection(db: Session, job: DiskInspectionJob) -> DiskInspectionRun:
    now = datetime.now()
    window_end = now
    window_start = now - timedelta(hours=max(1, int(job.window_hours or 24)))
    summary = _build_summary(db, label=job.name, start=window_start, end=window_end, hours=job.window_hours)
    status = "warning" if summary.total_write_bytes >= job.threshold_bytes else "success"
    webhook_ids = _load_int_list(job.webhook_ids)
    run = DiskInspectionRun(
        inspection_job_id=job.id,
        inspection_job_name=job.name,
        status=status,
        inspected_at=now,
        window_start=window_start,
        window_end=window_end,
        window_hours=job.window_hours,
        threshold_bytes=job.threshold_bytes,
        total_write_bytes=summary.total_write_bytes,
        total_read_bytes=summary.total_read_bytes,
        max_single_write_bytes=summary.max_single_write_bytes,
        warning_count=summary.warning_count,
        record_count=summary.record_count,
        chatlog_decrypt_count=summary.chatlog_decrypt_count,
        weflow_media_count=summary.weflow_media_count,
        webhook_ids=json.dumps(webhook_ids, ensure_ascii=False),
        summary=_inspection_summary_text(summary, threshold=job.threshold_bytes),
    )
    db.add(run)
    job.last_run_at = now
    db.add(job)
    db.flush()
    if status == "warning" and webhook_ids and _can_alert(job, now):
        try:
            webhooks = webhook_repo.get_by_ids(db, webhook_ids)
            await feishu.broadcast_markdown(
                webhooks,
                title="磁盘写入巡检告警",
                content=_inspection_alert_content(job, run),
                template="red",
            )
            run.alert_sent = True
            job.last_alert_at = now
        except Exception as exc:  # pragma: no cover - external webhook failures
            logger.exception("磁盘巡检告警推送失败 job_id={}", job.id)
            run.alert_error = str(exc)
    db.add(job)
    db.add(run)
    db.flush()
    return run


def _build_summary(db: Session, *, label: str, start: datetime, end: datetime, hours: Optional[int]) -> DiskIoSummary:
    query = db.query(DiskIoRecord).filter(DiskIoRecord.finished_at >= start, DiskIoRecord.finished_at <= end)
    row = query.with_entities(
        func.coalesce(func.sum(DiskIoRecord.disk_write_bytes), 0),
        func.coalesce(func.sum(DiskIoRecord.total_read_bytes), 0),
        func.coalesce(func.max(DiskIoRecord.disk_write_bytes), 0),
        func.coalesce(func.sum(case((DiskIoRecord.is_warning.is_(True), 1), else_=0)), 0),
        func.count(DiskIoRecord.id),
        func.coalesce(func.sum(case((DiskIoRecord.media_enabled.is_(True), 1), else_=0)), 0),
    ).first()
    chatlog_decrypt_count = query.filter(DiskIoRecord.provider == "chatlog", DiskIoRecord.chatlog_decrypt_write_bytes > 0).count()
    return DiskIoSummary(
        label=label,
        hours=hours,
        start_time=start,
        end_time=end,
        total_write_bytes=int(row[0] or 0),
        total_read_bytes=int(row[1] or 0),
        max_single_write_bytes=int(row[2] or 0),
        warning_count=int(row[3] or 0),
        record_count=int(row[4] or 0),
        chatlog_decrypt_count=chatlog_decrypt_count,
        weflow_media_count=int(row[5] or 0),
    )


def get_summary_cards(db: Session) -> List[DiskIoSummary]:
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    year_start = datetime(now.year, 1, 1)
    previous_month_end = month_start
    previous_month_start = (
        datetime(previous_month_end.year - 1, 12, 1)
        if previous_month_end.month == 1
        else datetime(previous_month_end.year, previous_month_end.month - 1, 1)
    )
    ranges = [
        ("最近 24 小时", now - timedelta(hours=24), now, 24),
        ("最近 7 天", now - timedelta(days=7), now, 168),
        ("本月", month_start, now, None),
        ("上月", previous_month_start, previous_month_end, None),
        ("本年度", year_start, now, None),
    ]
    return [_build_summary(db, label=label, start=start, end=end, hours=hours) for label, start, end, hours in ranges]


def get_aggregate(db: Session, *, start_time: datetime, end_time: datetime) -> DiskIoAggregateOut:
    query = db.query(DiskIoRecord).filter(DiskIoRecord.finished_at >= start_time, DiskIoRecord.finished_at <= end_time)
    summary_row = query.with_entities(
        func.coalesce(func.sum(DiskIoRecord.disk_write_bytes), 0),
        func.coalesce(func.max(DiskIoRecord.disk_write_bytes), 0),
        func.count(DiskIoRecord.id),
        func.coalesce(func.sum(case((DiskIoRecord.is_warning.is_(True), 1), else_=0)), 0),
    ).first()
    monthly_rows = (
        query.with_entities(
            func.strftime("%Y-%m", DiskIoRecord.finished_at).label("month"),
            func.coalesce(func.sum(DiskIoRecord.disk_write_bytes), 0),
            func.count(DiskIoRecord.id),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )
    ranking_rows = (
        query.with_entities(
            DiskIoRecord.task_name,
            DiskIoRecord.job_name,
            func.count(DiskIoRecord.id),
            func.coalesce(func.sum(DiskIoRecord.disk_write_bytes), 0),
        )
        .group_by(DiskIoRecord.task_name, DiskIoRecord.job_name)
        .order_by(func.coalesce(func.sum(DiskIoRecord.disk_write_bytes), 0).desc())
        .limit(20)
        .all()
    )
    return DiskIoAggregateOut(
        summary=DiskIoAggregateSummary(
            disk_write_bytes=int(summary_row[0] or 0),
            max_single_disk_write_bytes=int(summary_row[1] or 0),
            record_count=int(summary_row[2] or 0),
            warning_count=int(summary_row[3] or 0),
        ),
        monthly_trend=[
            DiskIoMonthlyTrendItem(
                month=str(row[0]),
                disk_write_bytes=int(row[1] or 0),
                record_count=int(row[2] or 0),
            )
            for row in monthly_rows
            if row[0]
        ],
        task_ranking=[
            DiskIoTaskRankingItem(
                task_name=row[0],
                job_name=row[1],
                record_count=int(row[2] or 0),
                disk_write_bytes=int(row[3] or 0),
                avg_disk_write_bytes=int((row[3] or 0) / (row[2] or 1)),
            )
            for row in ranking_rows
        ],
    )


def _snapshot_pid(pid: int) -> Optional[IoSnapshot]:
    if platform.system().lower() != "windows":
        return None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    counters = _IO_COUNTERS()
    try:
        ok = kernel32.GetProcessIoCounters(handle, ctypes.byref(counters))
        if not ok:
            return None
        return IoSnapshot(read_bytes=int(counters.ReadTransferCount), write_bytes=int(counters.WriteTransferCount))
    finally:
        kernel32.CloseHandle(handle)


def _sum_snapshots(pids: Iterable[int]) -> Optional[IoSnapshot]:
    total_read = 0
    total_write = 0
    found = False
    for pid in pids:
        snapshot = _snapshot_pid(pid)
        if snapshot:
            found = True
            total_read += snapshot.read_bytes
            total_write += snapshot.write_bytes
    return IoSnapshot(total_read, total_write) if found else None


def _resolve_weflow_pids(db: Session) -> List[int]:
    pids: set[int] = set()
    port = _weflow_port(db)
    if port:
        pids.update(_pids_by_port(port))
    for name in _weflow_process_names(db):
        pids.update(_pids_by_image_name(name))
    return sorted(pid for pid in pids if pid > 0)


def _weflow_port(db: Session) -> Optional[int]:
    entity = db.query(ChatRecordSetting).order_by(ChatRecordSetting.id.asc()).first()
    raw = entity.weflow_base_url if entity else "http://127.0.0.1:5031"
    try:
        parsed = urlparse(raw)
        return parsed.port
    except Exception:
        return None


def _weflow_process_names(db: Session) -> List[str]:
    raw = (
        db.query(DiskInspectionJob.weflow_process_names)
        .filter(DiskInspectionJob.weflow_process_names.isnot(None))
        .order_by(DiskInspectionJob.id.asc())
        .first()
    )
    values = _split_csv(raw[0] if raw else None)
    return values or DEFAULT_WEFLOW_PROCESS_NAMES


def _pids_by_port(port: int) -> List[int]:
    try:
        result = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return []
    pids: set[int] = set()
    marker = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper().startswith("TCP") and marker in parts[1] and parts[3].upper() == "LISTENING":
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                pass
    return sorted(pids)


def _pids_by_image_name(name: str) -> List[int]:
    if not name.lower().endswith(".exe"):
        name = f"{name}.exe"
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return []
    pids: set[int] = set()
    for row in csv.reader(line for line in result.stdout.splitlines() if line.startswith('"')):
        if len(row) >= 2:
            try:
                pids.add(int(row[1]))
            except ValueError:
                pass
    return sorted(pids)


def _current_provider(db: Session) -> str:
    entity = db.query(ChatRecordSetting).order_by(ChatRecordSetting.id.asc()).first()
    return entity.provider if entity else "chatlog"


def _snapshot_from_dict(value: Optional[dict]) -> Optional[IoSnapshot]:
    if not isinstance(value, dict):
        return None
    try:
        return IoSnapshot(read_bytes=int(value.get("read_bytes") or 0), write_bytes=int(value.get("write_bytes") or 0))
    except (TypeError, ValueError):
        return None


def _delta(start: Optional[IoSnapshot], end: Optional[IoSnapshot]) -> tuple[Optional[int], Optional[int]]:
    if not start or not end:
        return None, None
    return max(end.read_bytes - start.read_bytes, 0), max(end.write_bytes - start.write_bytes, 0)


def _sum_exported_file_bytes(exported_files: Iterable[dict[str, Any]]) -> int:
    total = 0
    for item in exported_files or []:
        path = item.get("path") if isinstance(item, dict) else None
        if not path:
            continue
        try:
            file_path = Path(path)
            if file_path.exists() and file_path.is_file():
                total += file_path.stat().st_size
        except OSError:
            continue
    return total


def _estimate_chatlog_decrypt_write_bytes(
    db: Session,
    *,
    provider: str,
    telemetry: dict,
    since: Optional[datetime],
) -> tuple[int, dict[str, Any]]:
    if provider != "chatlog":
        return 0, {"status": None, "reason": "not_chatlog"}
    decrypt_result = telemetry.get("chatlog_decrypt") if isinstance(telemetry, dict) else None
    status = decrypt_result.get("status") if isinstance(decrypt_result, dict) else "unknown"
    work_dir = (
        telemetry.get("chatlog_work_dir")
        or (decrypt_result.get("work_dir") if isinstance(decrypt_result, dict) else None)
        or _chatlog_work_dir(db)
    )
    meta: dict[str, Any] = {"status": status, "work_dir": work_dir}
    if status != "decrypted":
        return 0, meta
    total, scan_meta = _sum_recent_chatlog_db_storage(work_dir, since)
    meta.update(scan_meta)
    return total, meta


def _chatlog_work_dir(db: Session) -> str:
    entity = db.query(ChatRecordSetting).order_by(ChatRecordSetting.id.asc()).first()
    return entity.chatlog_work_dir if entity and entity.chatlog_work_dir else r"C:\Users\Limmer\Documents\chatlog"


def _parse_context_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _sum_recent_chatlog_db_storage(work_dir: Optional[str], since: Optional[datetime]) -> tuple[int, dict[str, Any]]:
    if not work_dir:
        return 0, {"scan_status": "missing_work_dir"}
    root = Path(work_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return 0, {"scan_status": "work_dir_unavailable"}
    since_ts = (since.timestamp() - 5) if since else 0
    total = 0
    file_count = 0
    db_storage_count = 0
    try:
        db_storage_dirs = [path for path in root.rglob("db_storage") if path.is_dir()]
    except OSError as exc:
        return 0, {"scan_status": "scan_failed", "error": str(exc)}
    for db_storage in db_storage_dirs:
        db_storage_count += 1
        try:
            files = db_storage.rglob("*")
            for file_path in files:
                try:
                    if file_path.is_symlink() or not file_path.is_file():
                        continue
                    stat = file_path.stat()
                except OSError:
                    continue
                if stat.st_mtime >= since_ts:
                    total += stat.st_size
                    file_count += 1
        except OSError:
            continue
    return total, {
        "scan_status": "ok",
        "db_storage_count": db_storage_count,
        "recent_file_count": file_count,
        "since": since.isoformat(sep=" ") if since else None,
    }


def _record_to_schema(record: DiskIoRecord) -> DiskIoRecordOut:
    raw_snapshot = None
    if record.raw_snapshot:
        try:
            raw_snapshot = json.loads(record.raw_snapshot)
        except json.JSONDecodeError:
            raw_snapshot = {"raw": record.raw_snapshot}
    return DiskIoRecordOut.model_validate(
        {
            **record.__dict__,
            "raw_snapshot": raw_snapshot,
        }
    )


def _job_to_schema(job: DiskInspectionJob) -> DiskInspectionJobOut:
    return DiskInspectionJobOut.model_validate(
        {
            **job.__dict__,
            "webhook_ids": _load_int_list(job.webhook_ids),
        }
    )


def _run_to_schema(run: DiskInspectionRun) -> DiskInspectionRunOut:
    return DiskInspectionRunOut.model_validate(
        {
            **run.__dict__,
            "webhook_ids": _load_int_list(run.webhook_ids),
        }
    )


def _job_payload(payload: DiskInspectionJobCreate | DiskInspectionJobUpdate) -> dict:
    data = payload.model_dump()
    if data.get("interval_enabled"):
        data["schedule_time"] = data.get("window_start") or "00:00"
    else:
        data["interval_minutes"] = None
    if data.get("schedule_type") != "weekly":
        data["schedule_weekday"] = None
    if data.get("schedule_type") != "monthly":
        data["schedule_month_day"] = None
    if data.get("schedule_type") != "custom_cron":
        data["cron_expression"] = None
    data["webhook_ids"] = json.dumps(data.get("webhook_ids") or [], ensure_ascii=False)
    return data


def _load_int_list(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    values: List[int] = []
    for item in data:
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values


def _split_csv(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in re.split(r"[,，\s]+", raw) if item.strip()]


def _can_alert(job: DiskInspectionJob, now: datetime) -> bool:
    if not job.last_alert_at:
        return True
    return now - job.last_alert_at >= timedelta(hours=max(0, int(job.cooldown_hours or 0)))


def _disk_warning_threshold_for_job(job: Job) -> tuple[int, str]:
    if getattr(job, "disk_alert_enabled", False):
        threshold = int(getattr(job, "disk_alert_threshold_bytes", 0) or 0)
        return (threshold if threshold > 0 else DEFAULT_WARNING_BYTES), "job"
    return DEFAULT_WARNING_BYTES, "default"


def _time_to_minutes(value: str) -> int:
    text = (value or "00:00").strip()
    hour_str, minute_str = text.split(":")
    hour = int(hour_str)
    minute = int(minute_str)
    return hour * 60 + minute


def _is_inspection_date_allowed(job: DiskInspectionJob, candidate) -> bool:
    weekday = candidate.weekday()
    if job.schedule_type == "daily":
        return True
    if job.schedule_type == "weekly":
        return weekday == max(0, min(6, int(job.schedule_weekday or 0)))
    if job.schedule_type == "monthly":
        return candidate.day == max(1, min(31, int(job.schedule_month_day or 1)))
    return False


def _inspection_summary_text(summary: DiskIoSummary, *, threshold: int) -> str:
    return (
        f"检查窗口内共 {summary.record_count} 条执行记录，"
        f"总写入 {_format_bytes(summary.total_write_bytes)}，"
        f"最大单次写入 {_format_bytes(summary.max_single_write_bytes)}，"
        f"阈值 {_format_bytes(threshold)}。"
    )


def _inspection_alert_content(job: DiskInspectionJob, run: DiskInspectionRun) -> str:
    return (
        f"**巡检任务**：{job.name}\n\n"
        f"**检查窗口**：{run.window_start:%Y-%m-%d %H:%M} ~ {run.window_end:%Y-%m-%d %H:%M}\n\n"
        f"**总写入量**：{_format_bytes(run.total_write_bytes)}\n\n"
        f"**最大单次写入**：{_format_bytes(run.max_single_write_bytes)}\n\n"
        f"**异常执行数量**：{run.warning_count}\n\n"
        f"**阈值**：{_format_bytes(run.threshold_bytes)}\n\n"
        "请打开系统左侧「日志 > 磁盘日志」查看详情。"
    )


def _format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value or 0)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
