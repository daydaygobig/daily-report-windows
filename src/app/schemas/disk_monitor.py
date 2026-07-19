"""Schemas for disk IO monitoring."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .base import ORMBase


class DiskIoRecordOut(ORMBase):
    execution_id: Optional[int]
    task_id: Optional[int]
    job_id: Optional[int]
    task_name: Optional[str]
    job_name: Optional[str]
    task_type: str
    is_manual: bool
    provider: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    backend_read_bytes: Optional[int]
    backend_write_bytes: Optional[int]
    weflow_read_bytes: Optional[int]
    weflow_write_bytes: Optional[int]
    weflow_captured: bool
    weflow_process: Optional[str]
    exported_file_bytes: int
    chatlog_decrypt_write_bytes: int = 0
    chatlog_decrypt_status: Optional[str] = None
    chatlog_work_dir: Optional[str] = None
    disk_write_bytes: int = 0
    total_read_bytes: int
    total_write_bytes: int
    media_enabled: bool
    is_warning: bool
    warning_reason: Optional[str]
    job_alert_threshold_bytes: int = 0
    job_alert_triggered: bool = False
    job_alert_sent: bool = False
    job_alert_error: Optional[str] = None
    raw_snapshot: Optional[Dict[str, Any]] = None


class DiskIoRecordPage(BaseModel):
    items: List[DiskIoRecordOut]
    total: int
    page: int
    page_size: int


class DiskIoSummary(BaseModel):
    label: str
    hours: Optional[int] = None
    start_time: datetime
    end_time: datetime
    total_write_bytes: int = 0
    total_read_bytes: int = 0
    max_single_write_bytes: int = 0
    warning_count: int = 0
    record_count: int = 0
    chatlog_decrypt_count: int = 0
    weflow_media_count: int = 0


class DiskIoAggregateSummary(BaseModel):
    disk_write_bytes: int = 0
    max_single_disk_write_bytes: int = 0
    record_count: int = 0
    warning_count: int = 0


class DiskIoMonthlyTrendItem(BaseModel):
    month: str
    disk_write_bytes: int = 0
    record_count: int = 0


class DiskIoTaskRankingItem(BaseModel):
    task_name: Optional[str] = None
    job_name: Optional[str] = None
    record_count: int = 0
    disk_write_bytes: int = 0
    avg_disk_write_bytes: int = 0


class DiskIoAggregateOut(BaseModel):
    summary: DiskIoAggregateSummary
    monthly_trend: List[DiskIoMonthlyTrendItem]
    task_ranking: List[DiskIoTaskRankingItem]


class DiskInspectionJobBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    is_enabled: bool = True
    schedule_type: str = "daily"
    schedule_time: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    schedule_weekday: Optional[int] = Field(default=None, ge=0, le=6)
    schedule_month_day: Optional[int] = Field(default=None, ge=1, le=31)
    cron_expression: Optional[str] = None
    interval_enabled: bool = False
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    window_start: str = Field(default="00:00", pattern=r"^\d{2}:\d{2}$")
    window_end: str = Field(default="24:00", pattern=r"^\d{2}:\d{2}$")
    window_hours: int = Field(default=24, ge=1)
    threshold_bytes: int = Field(default=104857600, ge=1)
    webhook_ids: List[int] = Field(default_factory=list)
    cooldown_hours: int = Field(default=6, ge=0)
    weflow_process_names: Optional[str] = None

    @model_validator(mode="after")
    def validate_schedule(cls, values: "DiskInspectionJobBase"):
        if _time_to_minutes(values.window_end) <= _time_to_minutes(values.window_start):
            raise ValueError("生效范围的结束时间必须晚于开始时间")
        if values.interval_enabled:
            if values.schedule_type in {"manual", "custom_cron"}:
                raise ValueError("手动巡检和自定义 Cron 不支持按间隔执行")
            if not values.interval_minutes or values.interval_minutes <= 0:
                raise ValueError("按间隔执行需要设置间隔频率（分钟）")
        return values


class DiskInspectionJobCreate(DiskInspectionJobBase):
    pass


class DiskInspectionJobUpdate(DiskInspectionJobBase):
    pass


class DiskInspectionJobOut(DiskInspectionJobBase, ORMBase):
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_alert_at: Optional[datetime] = None


class DiskInspectionRunOut(ORMBase):
    inspection_job_id: Optional[int]
    inspection_job_name: Optional[str]
    status: str
    inspected_at: datetime
    window_start: datetime
    window_end: datetime
    window_hours: int
    threshold_bytes: int
    total_write_bytes: int
    total_read_bytes: int
    max_single_write_bytes: int
    warning_count: int
    record_count: int
    chatlog_decrypt_count: int
    weflow_media_count: int
    alert_sent: bool
    alert_error: Optional[str] = None
    webhook_ids: Optional[List[int]] = None
    summary: Optional[str] = None


class DiskInspectionRunPage(BaseModel):
    items: List[DiskInspectionRunOut]
    total: int
    page: int
    page_size: int


def _time_to_minutes(value: str) -> int:
    hour_str, minute_str = value.split(":")
    hour = int(hour_str)
    minute = int(minute_str)
    if hour == 24 and minute == 0:
        return 24 * 60
    if 0 <= hour < 24 and 0 <= minute < 60:
        return hour * 60 + minute
    raise ValueError("时间格式需为 HH:MM 且合法")
