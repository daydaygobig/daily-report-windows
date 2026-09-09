"""磁盘告警与失败通知（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger

from ..models.disk_monitor import DiskIoRecord
from ..models.execution import Execution
from ..models.job import Job
from ..models.task import Task
from ..services import alert_service, disk_monitor_service

from .common import (
    webhook_repo,
)
from .parsing import (
    _parse_int_list,
)

class AlertFlowMixin:
    """作业级磁盘告警与告警 webhook 通知。"""

    async def _handle_job_disk_alert(
        self,
        *,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        disk_record: DiskIoRecord,
    ) -> None:
        threshold = int(getattr(job, "disk_alert_threshold_bytes", 0) or 0) if getattr(job, "disk_alert_enabled", False) else 0
        if getattr(job, "disk_alert_enabled", False) and threshold <= 0:
            threshold = disk_monitor_service.DEFAULT_WARNING_BYTES
        disk_record.job_alert_threshold_bytes = threshold
        if threshold <= 0 or disk_record.disk_write_bytes < threshold:
            disk_record.job_alert_triggered = False
            disk_record.job_alert_sent = False
            disk_record.job_alert_error = None
            db.add(disk_record)
            return

        disk_record.job_alert_triggered = True
        payload = {
            "disk_io_record_id": disk_record.id,
            "provider": disk_record.provider,
            "disk_write_bytes": disk_record.disk_write_bytes,
            "threshold_bytes": threshold,
            "execution_id": execution.id,
        }
        alert_service.create_alert(
            db,
            task_id=task.id,
            job_id=job.id,
            execution_id=execution.id,
            category="disk_io",
            level="warning",
            message=f"作业磁盘写入超过阈值：{self._format_bytes(disk_record.disk_write_bytes)} / {self._format_bytes(threshold)}",
            payload=payload,
        )

        alert_ids = _parse_int_list(getattr(task, "alert_webhook_ids", None))
        if not alert_ids:
            disk_record.job_alert_sent = False
            disk_record.job_alert_error = None
            db.add(disk_record)
            return

        webhooks = webhook_repo.get_by_ids(db, alert_ids)
        if not webhooks:
            disk_record.job_alert_sent = False
            disk_record.job_alert_error = None
            db.add(disk_record)
            return

        try:
            sent = await self._push_feishu(
                webhooks=webhooks,
                task=task,
                job=job,
                summary=self._build_job_disk_alert_summary(task, job, execution, disk_record, threshold),
            )
            disk_record.job_alert_sent = sent
            disk_record.job_alert_error = None if sent else "all webhook deliveries failed"
        except Exception as exc:
            logger.exception("推送作业磁盘告警失败 task={} job={} execution={}", task.id, job.id, execution.id)
            disk_record.job_alert_sent = False
            disk_record.job_alert_error = str(exc)
        db.add(disk_record)

    def _build_job_disk_alert_summary(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        disk_record: DiskIoRecord,
        threshold: int,
    ) -> str:
        provider_label = "WeFlow" if disk_record.provider == "weflow" else "ChatLog"
        timestamp = execution.finished_at or execution.started_at or datetime.now(tz=self._tz).replace(tzinfo=None)
        return (
            f"**任务**：{task.name}\n\n"
            f"**作业**：{job.name}\n\n"
            f"**执行时间**：{timestamp:%Y-%m-%d %H:%M:%S}\n\n"
            f"**数据来源**：{provider_label}\n\n"
            f"**本次磁盘写入**：{self._format_bytes(disk_record.disk_write_bytes)}\n\n"
            f"**告警阈值**：{self._format_bytes(threshold)}\n\n"
            f"**导出文件写入**：{self._format_bytes(disk_record.exported_file_bytes)}\n\n"
            f"**ChatLog 解密写入**：{self._format_bytes(disk_record.chatlog_decrypt_write_bytes)}\n\n"
            f"**执行记录**：#{execution.id}\n\n"
            f"可前往“执行记录 #{execution.id}”或“日志 > 磁盘日志”查看详情。"
        )

    def _format_bytes(self, value: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        amount = float(value or 0)
        for unit in units:
            if amount < 1024 or unit == units[-1]:
                return f"{int(amount)} B" if unit == "B" else f"{amount:.2f} {unit}"
            amount /= 1024
        return f"{value} B"

    async def _notify_alert_webhooks(self, db, task: Task, job: Optional[Job], error_message: str) -> None:
        alert_ids = _parse_int_list(getattr(task, "alert_webhook_ids", None))
        if not alert_ids:
            return
        webhooks = webhook_repo.get_by_ids(db, alert_ids)
        if not webhooks:
            return
        timestamp = datetime.now(tz=self._tz).strftime("%Y-%m-%d %H:%M:%S")
        job_name = job.name if job else None
        summary = (
            f"**任务：** {task.name}\n\n"
            f"**作业：** {job_name or '-'}\n\n"
            f"**状态：** 告警\n\n"
            f"**错误信息：** {error_message}\n\n"
            f"**时间：** {timestamp}"
        )
        try:
            await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=summary)
        except Exception:
            logger.exception("推送告警到飞书失败 task={} job={}", task.id, getattr(job, "id", None))
