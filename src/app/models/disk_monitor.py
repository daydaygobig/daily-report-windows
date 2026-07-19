"""Disk IO monitor entities."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class DiskIoRecord(BaseModel):
    __tablename__ = "disk_io_records"

    execution_id = Column(Integer, ForeignKey("executions.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    task_name = Column(Text, nullable=True)
    job_name = Column(Text, nullable=True)
    task_type = Column(String(20), nullable=False, default="report")
    is_manual = Column(Boolean, nullable=False, default=False)
    provider = Column(String(20), nullable=False, default="unknown")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    backend_read_bytes = Column(Integer, nullable=True)
    backend_write_bytes = Column(Integer, nullable=True)
    weflow_read_bytes = Column(Integer, nullable=True)
    weflow_write_bytes = Column(Integer, nullable=True)
    weflow_captured = Column(Boolean, nullable=False, default=False)
    weflow_process = Column(Text, nullable=True)
    exported_file_bytes = Column(Integer, nullable=False, default=0)
    chatlog_decrypt_write_bytes = Column(Integer, nullable=False, default=0)
    chatlog_decrypt_status = Column(String(20), nullable=True)
    chatlog_work_dir = Column(Text, nullable=True)
    disk_write_bytes = Column(Integer, nullable=False, default=0)
    total_read_bytes = Column(Integer, nullable=False, default=0)
    total_write_bytes = Column(Integer, nullable=False, default=0)
    job_alert_threshold_bytes = Column(Integer, nullable=False, default=0)
    job_alert_triggered = Column(Boolean, nullable=False, default=False)
    job_alert_sent = Column(Boolean, nullable=False, default=False)
    job_alert_error = Column(Text, nullable=True)
    media_enabled = Column(Boolean, nullable=False, default=False)
    is_warning = Column(Boolean, nullable=False, default=False)
    warning_reason = Column(Text, nullable=True)
    raw_snapshot = Column(Text, nullable=True)

    execution = relationship("Execution")


class DiskInspectionJob(BaseModel):
    __tablename__ = "disk_inspection_jobs"

    name = Column(String(120), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    schedule_type = Column(String(30), nullable=False, default="daily")
    schedule_time = Column(String(5), nullable=False, default="09:00")
    schedule_weekday = Column(Integer, nullable=True)
    schedule_month_day = Column(Integer, nullable=True)
    cron_expression = Column(String(120), nullable=True)
    interval_enabled = Column(Boolean, nullable=False, default=False)
    interval_minutes = Column(Integer, nullable=True)
    window_start = Column(String(5), nullable=False, default="00:00")
    window_end = Column(String(5), nullable=False, default="24:00")
    window_hours = Column(Integer, nullable=False, default=24)
    threshold_bytes = Column(Integer, nullable=False, default=104857600)
    webhook_ids = Column(Text, nullable=False, default="[]")
    cooldown_hours = Column(Integer, nullable=False, default=6)
    weflow_process_names = Column(Text, nullable=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    last_alert_at = Column(DateTime, nullable=True)


class DiskInspectionRun(BaseModel):
    __tablename__ = "disk_inspection_runs"

    inspection_job_id = Column(Integer, ForeignKey("disk_inspection_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    inspection_job_name = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="success")
    inspected_at = Column(DateTime, nullable=False)
    window_start = Column(DateTime, nullable=False)
    window_end = Column(DateTime, nullable=False)
    window_hours = Column(Integer, nullable=False, default=24)
    threshold_bytes = Column(Integer, nullable=False, default=104857600)
    total_write_bytes = Column(Integer, nullable=False, default=0)
    total_read_bytes = Column(Integer, nullable=False, default=0)
    max_single_write_bytes = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    record_count = Column(Integer, nullable=False, default=0)
    chatlog_decrypt_count = Column(Integer, nullable=False, default=0)
    weflow_media_count = Column(Integer, nullable=False, default=0)
    alert_sent = Column(Boolean, nullable=False, default=False)
    alert_error = Column(Text, nullable=True)
    webhook_ids = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    inspection_job = relationship("DiskInspectionJob")
