"""APScheduler integration for running jobs."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from bs4 import BeautifulSoup
import httpx
from loguru import logger
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..db import session_scope
from ..integrations import feishu, github, llm
from ..integrations.security import decrypt_value
from ..models.disk_monitor import DiskInspectionJob, DiskIoRecord
from ..models.execution import Execution
from ..models.job import Job
from ..models.github_deployment import GithubDeployment
from ..models.model import Model
from ..models.task import Task
from ..repositories.job_repo import JobRepository
from ..repositories.webhook_repo import WebhookRepository
from ..services import alert_service, chat_record_service, disk_monitor_service
from ..services.github_view_url import build_view_url
from ..services import topic_card_service
from ..schemas.webhook import CARD_COLOR_OPTIONS
from ..utils.interval_schedule import build_daily_interval_plans as build_shared_interval_plans
from ..utils.interval_schedule import compute_next_interval_plan as compute_shared_interval_plan
from ..utils import message_stats as message_stats_utils
from ..utils.prompt_metrics import compute_prompt_usage, count_tokens

settings = get_settings()
job_repo = JobRepository()
webhook_repo = WebhookRepository()

@dataclass
class IntervalPlan:
    fire_time: datetime
    window_start: datetime
    window_end: datetime

    def to_window_payload(self) -> dict:
        return {
            "start": self.window_start,
            "end": self.window_end,
            "time_str": f"{self.window_start.strftime('%Y-%m-%d %H:%M')}~{self.window_end.strftime('%Y-%m-%d %H:%M')}",
        }


@dataclass
class HtmlArtifactPlan:
    filename: str
    target_date: datetime
    generated_at: datetime


@dataclass
class GithubUploadArtifact:
    repo_path: str
    repo_full_name: str
    branch: str
    github_file_url: str
    pages_url: Optional[str] = None


@dataclass
class ModelSequenceItem:
    model: Model
    max_attempts: int


@dataclass
class AiSummaryResult:
    summary: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    model: Model
    prompt_meta: Dict[str, Any]


def _format_exception_message(label: str, exc: BaseException, *, attempts: Optional[int] = None) -> str:
    detail = _exception_detail(exc)
    if detail.startswith(f"{label}失败："):
        return detail
    if label == "执行":
        return detail
    attempt_text = f"，已尝试 {attempts} 次" if attempts and attempts > 1 else ""
    return f"{label}失败：{detail}{attempt_text}"


def _exception_detail(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "请求超时，可能是网络问题"
    if isinstance(exc, httpx.ConnectError):
        return "连接失败，可能是网络问题"
    if isinstance(exc, github.GithubAPIError):
        return _format_github_api_error(str(exc).strip())

    detail = str(exc).strip()
    if detail:
        return detail
    return f"异常类型 {type(exc).__name__}"


def _format_github_api_error(detail: str) -> str:
    status_match = re.match(r"^(\d{3})\b", detail)
    status_code = int(status_match.group(1)) if status_match else None
    if status_code in {401, 403}:
        return "GitHub 认证或权限失败，请检查 Token 是否有效且有仓库写入权限"
    if status_code == 404:
        return "GitHub 仓库、分支或文件路径不存在，请检查 owner/repo/branch 配置"
    if status_code in {429, 500, 502, 503, 504}:
        return f"GitHub 服务暂时不可用或限流（HTTP {status_code}），请稍后重试"
    if status_code:
        return f"GitHub 返回错误（HTTP {status_code}）：{detail}"
    return detail or "GitHub 返回了未知错误"


class AIOutputValidationError(RuntimeError):
    """Model returned text, but the business validator rejected it."""

    def __init__(self, message: str, *, raw_summary: str) -> None:
        super().__init__(message)
        self.raw_summary = raw_summary


EMPTY_CHATLOG_ERROR_MESSAGE = "聊天记录多次拉取为空，疑似指定时间段内无聊天信息"


class SchedulerService:
    """Wrapper around APScheduler with domain-specific execution."""

    def __init__(self) -> None:
        job_defaults = {
            "coalesce": False,
            "max_instances": 1,
            "misfire_grace_time": 300,
        }
        self.scheduler = AsyncIOScheduler(timezone=settings.timezone, job_defaults=job_defaults)
        self._started = False
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tz = ZoneInfo(settings.timezone)
        self._backup_dir = Path(settings.local_backup_dir).expanduser().resolve()
        self._auto_reload_job_id = "scheduler-auto-reload"
        self._ima_auto_sync_job_id = "ima-auto-sync"
        self._ima_sync_job_prefix = "ima-sync-job-"
        self._disk_inspection_job_prefix = "disk-inspection-job-"

    def start(self) -> None:
        if self._started:
            return
        self._loop = asyncio.get_event_loop()
        self.scheduler.start()
        self._started = True
        self._loop.create_task(self.reload_jobs())
        self._add_daily_reload_job()
        logger.info("Scheduler started")

    def _add_daily_reload_job(self) -> None:
        """Ensure scheduler reloads itself periodically to pick up DB changes."""

        def _reload_wrapper():
            if self._loop and self._loop.is_running():
                self._loop.create_task(self.reload_jobs())

        job_id = self._auto_reload_job_id
        existing = self.scheduler.get_job(job_id)
        if existing:
            existing.remove()
        trigger = CronTrigger(hour="*/1", minute=5)
        self.scheduler.add_job(
            _reload_wrapper,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=60,
            max_instances=1,
        )

    async def reload_jobs(self) -> None:
        logger.info("Reloading scheduled jobs")
        async with self._lock:
            self.scheduler.remove_all_jobs()
            with session_scope() as db:
                jobs = job_repo.list_enabled(db)
                for job in jobs:
                    self._schedule_job(job)
            self._add_daily_reload_job()
            await self._schedule_ima_sync_jobs()
            await self._schedule_disk_inspection_jobs()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shutdown")

    def trigger_reload(self) -> None:
        if not self._loop or not self._loop.is_running():
            return
        self._loop.call_soon_threadsafe(lambda: self._loop.create_task(self.reload_jobs()))

    def get_ima_auto_sync_next_run(self) -> Optional[datetime]:
        sched_job = self.scheduler.get_job(self._ima_auto_sync_job_id)
        return sched_job.next_run_time if sched_job else None

    def get_ima_sync_job_next_run(self, sync_job_id: int) -> Optional[datetime]:
        sched_job = self.scheduler.get_job(f"{self._ima_sync_job_prefix}{sync_job_id}")
        return sched_job.next_run_time if sched_job else None

    def get_disk_inspection_next_run(self, job_id: int) -> Optional[datetime]:
        sched_job = self.scheduler.get_job(f"{self._disk_inspection_job_prefix}{job_id}")
        return sched_job.next_run_time if sched_job else None

    async def _schedule_disk_inspection_jobs(self) -> None:
        try:
            with session_scope() as db:
                inspection_jobs = disk_monitor_service.list_enabled_inspection_jobs(db)
            for sched_job in list(self.scheduler.get_jobs()):
                if sched_job.id.startswith(self._disk_inspection_job_prefix):
                    sched_job.remove()
            with session_scope() as db:
                for inspection_job in inspection_jobs:
                    next_run = self._schedule_disk_inspection_job(inspection_job)
                    disk_monitor_service.update_next_run(db, inspection_job.id, next_run)
        except Exception:
            logger.exception("配置磁盘巡检任务失败")

    def _schedule_disk_inspection_job(self, inspection_job) -> Optional[datetime]:
        job_id = f"{self._disk_inspection_job_prefix}{inspection_job.id}"
        if bool(getattr(inspection_job, "interval_enabled", False)):
            next_run = disk_monitor_service.get_next_run_at(inspection_job)
            if not next_run:
                return None
            self.scheduler.add_job(
                self._run_scheduled_disk_inspection_job,
                trigger=DateTrigger(run_date=next_run, timezone=self._tz),
                id=job_id,
                args=[inspection_job.id],
                replace_existing=True,
                coalesce=False,
                misfire_grace_time=600,
                max_instances=1,
            )
            return next_run
        trigger = disk_monitor_service.build_trigger(inspection_job)
        if not trigger:
            return None
        sched_job = self.scheduler.add_job(
            self._run_scheduled_disk_inspection_job,
            trigger=trigger,
            id=job_id,
            args=[inspection_job.id],
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=600,
            max_instances=1,
        )
        return sched_job.next_run_time

    async def _run_scheduled_disk_inspection_job(self, inspection_job_id: int) -> None:
        try:
            await disk_monitor_service.run_scheduled_inspection(inspection_job_id)
        except Exception:
            logger.exception("执行磁盘巡检任务失败 inspection_job_id=%s", inspection_job_id)
        finally:
            with session_scope() as db:
                inspection_job = (
                    db.query(DiskInspectionJob)
                    .filter(DiskInspectionJob.id == inspection_job_id)
                    .first()
                )
                if not inspection_job or not inspection_job.is_enabled:
                    disk_monitor_service.update_next_run(db, inspection_job_id, None)
                    return
                next_run = self._schedule_disk_inspection_job(inspection_job)
                disk_monitor_service.update_next_run(db, inspection_job_id, next_run)

    async def _schedule_ima_sync_jobs(self) -> None:
        try:
            from ..services import ima_sync_service

            with session_scope() as db:
                sync_jobs = ima_sync_service.list_enabled_sync_jobs(db)
            for sched_job in list(self.scheduler.get_jobs()):
                if sched_job.id.startswith(self._ima_sync_job_prefix):
                    sched_job.remove()
            for sync_job in sync_jobs:
                hour, minute = [int(part) for part in (sync_job.schedule_time or "08:00").split(":")]
                kwargs = {"hour": hour, "minute": minute}
                if (sync_job.schedule_frequency or "daily") == "weekly":
                    weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    weekday = int(sync_job.schedule_weekday or 0)
                    kwargs["day_of_week"] = weekdays[max(0, min(6, weekday))]
                self.scheduler.add_job(
                    self._run_ima_sync_job,
                    trigger=CronTrigger(**kwargs),
                    id=f"{self._ima_sync_job_prefix}{sync_job.id}",
                    args=[sync_job.id],
                    replace_existing=True,
                    coalesce=True,
                    misfire_grace_time=600,
                    max_instances=1,
                )
        except Exception:
            logger.exception("配置 IMA 同步作业失败")

    async def _run_ima_auto_sync(self) -> None:
        try:
            from ..services import ima_sync_service

            with session_scope() as db:
                await ima_sync_service.run_auto_directory_sync(db)
        except Exception:
            logger.exception("执行 IMA 自动同步失败")

    async def _run_ima_sync_job(self, sync_job_id: int) -> None:
        try:
            from ..services import ima_sync_service

            with session_scope() as db:
                await ima_sync_service.run_auto_sync_job(db, sync_job_id)
        except Exception:
            logger.exception("执行 IMA 同步作业失败 sync_job_id=%s", sync_job_id)

    def _schedule_job(self, job: Job) -> Optional[datetime]:
        existing = self.scheduler.get_job(f"job-{job.id}")
        if existing:
            existing.remove()
        if not job.is_enabled or not self._is_within_active_range(job):
            logger.info("Job %s (%s) is outside active range or disabled", job.id, job.name)
            job.next_run_at = None
            return None

        if job.interval_enabled:
            plan = self._compute_next_interval_plan(job)
            if not plan:
                logger.info("Job %s has no available interval execution plan", job.id)
                job.next_run_at = None
                return None
            misfire_window = self._calculate_misfire_window(job)
            self.scheduler.add_job(
                self._run_job,
                trigger=DateTrigger(run_date=plan.fire_time, timezone=self._tz),
                id=f"job-{job.id}",
                args=[job.id],
                kwargs={"window_override": plan.to_window_payload()},
                replace_existing=True,
                coalesce=False,
                misfire_grace_time=misfire_window,
                max_instances=1,
            )
            next_local = plan.fire_time.astimezone(self._tz).replace(tzinfo=None)
            job.next_run_at = next_local
            logger.info("Scheduled interval job %s next run at %s", job.id, next_local)
            return next_local

        trigger = self._build_trigger(job)
        if not trigger:
            logger.warning("Job %s has invalid schedule", job.id)
            job.next_run_at = None
            return None
        misfire_window = self._calculate_misfire_window(job)
        aps_job = self.scheduler.add_job(
            self._run_job,
            trigger=trigger,
            id=f"job-{job.id}",
            args=[job.id],
            replace_existing=True,
            coalesce=False,
            misfire_grace_time=misfire_window,
            max_instances=1,
        )
        execution_time_str = job.execution_time or job.start_time
        logger.info("Scheduled job %s (%s) execution_time=%s", job.id, job.name, execution_time_str)
        next_run = aps_job.next_run_time
        if next_run:
            next_local = next_run.astimezone(self._tz).replace(tzinfo=None)
            job.next_run_at = next_local
            logger.info("Job %s next run at %s (local time)", job.id, next_local)
        else:
            job.next_run_at = None
        return job.next_run_at

    def _build_trigger(self, job: Job) -> Optional[CronTrigger]:
        if job.schedule_type == "manual":
            return None
        execution_time = job.execution_time or job.start_time
        total_minutes = _time_str_to_minutes(execution_time)
        if total_minutes >= 24 * 60:
            hour = 0
            minute = 0
        else:
            hour = total_minutes // 60
            minute = total_minutes % 60
        kwargs = {"hour": hour, "minute": minute}
        if job.schedule_type == "daily":
            return CronTrigger(**kwargs)
        if job.schedule_type == "weekday":
            return CronTrigger(day_of_week="mon-fri", **kwargs)
        if job.schedule_type == "weekend":
            return CronTrigger(day_of_week="sat,sun", **kwargs)
        if job.schedule_type == "weekly":
            weekdays = _parse_int_list(job.weekdays)
            if not weekdays:
                weekdays = list(range(0, 7))
            mapping = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            day_of_week = ",".join(mapping[idx] for idx in weekdays if 0 <= idx < 7)
            return CronTrigger(day_of_week=day_of_week or "mon-sun", **kwargs)
        if job.schedule_type == "weekly_report":
            weekdays = _parse_int_list(job.weekdays)
            mapping = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            index = weekdays[0] if weekdays else 0
            day_of_week = mapping[index] if 0 <= index < len(mapping) else "mon"
            return CronTrigger(day_of_week=day_of_week, **kwargs)
        if job.schedule_type == "custom_cron" and job.cron_expression:
            return CronTrigger.from_crontab(job.cron_expression)
        return None

    def _calculate_misfire_window(self, job: Job) -> int:
        try:
            max_retry = max(int(job.max_retry or 0), 0)
        except (TypeError, ValueError):
            max_retry = 0
        try:
            interval = max(int(job.retry_interval_sec or 60), 1)
        except (TypeError, ValueError):
            interval = 60
        if max_retry > 0:
            return max_retry * interval + interval
        return max(interval * 2, 300)

    async def run_job_immediately(self, job_id: int) -> Optional[int]:
        """Trigger a job execution and wait for completion."""
        return await self._run_job(job_id, is_manual=True)

    async def _run_job(self, job_id: int, is_manual: bool = False, window_override: Optional[dict] = None) -> Optional[int]:
        logger.info("Running job %s", job_id)
        execution_id: Optional[int] = None
        with session_scope() as db:
            job = job_repo.get_by_id(db, job_id)
            if not job or not job.is_enabled:
                logger.warning("Job %s not found or disabled", job_id)
                return None
            if not self._is_within_active_range(job):
                logger.info("Job %s is outside active range, skipping execution", job_id)
                return None
            task = job.task
            if not task or not task.is_active:
                logger.warning("Task for job %s is inactive", job_id)
                return None
            talkers = _parse_str_list(task.talkers)
            stored_names = _parse_str_list(getattr(task, "talker_names", None))
            if not talkers:
                logger.error("Task %s has no talkers configured", task.id)
                alert_service.create_alert(
                    db,
                    task_id=task.id,
                    job_id=job.id,
                    category="configuration",
                    message="任务未配置群聊",
                )
                await self._notify_alert_webhooks(
                    db,
                    task,
                    job,
                    "任务未配置群聊（请在任务设置中选择至少一个群聊）",
                )
                return
            talker_names = stored_names if stored_names and len(stored_names) == len(talkers) else talkers

            exported_files: List[dict[str, Any]] = []
            execution = Execution(
                task_id=task.id,
                job_id=job.id,
                status="running",
                scheduled_at=datetime.now(tz=self._tz).replace(tzinfo=None),
                started_at=datetime.now(tz=self._tz).replace(tzinfo=None),
                is_manual=is_manual,
            )
            db.add(execution)
            db.flush()
            execution_id = execution.id
            db.commit()
            db.refresh(execution)
            db.refresh(job)

            max_retry = max(int(job.max_retry or 0), 0)
            attempts = max_retry + 1
            retry_interval = max(int(job.retry_interval_sec or 0), 1)
            attempt = 0
            chatlog_path: Optional[str] = None
            deployment_record: Optional[GithubDeployment] = None
            stats_exported = False
            try:
                disk_io_context = disk_monitor_service.start_execution_io(db, execution=execution, task=task, job=job)
            except Exception:
                logger.exception("磁盘 IO 开始采样失败 execution_id=%s", execution.id)
                disk_io_context = None
            chat_record_telemetry: dict[str, Any] = {}
            try:
                while attempt < attempts:
                    attempt += 1
                    allow_outer_retry = True
                    chatlog_path = None
                    time_window = None
                    summary_snapshot: Optional[str] = None
                    message_stats_result: Optional[message_stats_utils.MessageStats] = None
                    execution.error_msg = None
                    try:
                        time_window = self._calculate_time_window(job, window_override=window_override, is_manual=is_manual)
                        chatlog_text = await self._collect_chatlog(talkers, time_window, telemetry=chat_record_telemetry)
                        if not chatlog_text.strip():
                            raise RuntimeError(EMPTY_CHATLOG_ERROR_MESSAGE)

                        chatlog_artifacts = self._store_chatlog_backup(task, job, execution, chatlog_text, time_window)
                        if chatlog_artifacts:
                            primary = chatlog_artifacts[0].get("path")
                            if primary:
                                execution.chatlog_path = primary
                            exported_files.extend(chatlog_artifacts)
                        stats_needed = self._should_compute_message_stats(task, job)
                        message_stats_result = (
                            message_stats_utils.compute_message_stats(chatlog_text) if stats_needed else None
                        )
                        if not stats_exported:
                            message_stats_artifacts = self._export_message_stats_files(
                                task,
                                job,
                                execution,
                                time_window,
                                message_stats_result,
                            )
                            if message_stats_artifacts:
                                exported_files.extend(message_stats_artifacts)
                                stats_exported = True
                        prompt_meta: Dict[str, Any] = {
                            "task_name": task.name,
                            "chatlog_range": time_window["time_str"],
                            "chatlog_label": f"{', '.join(talker_names)} 路 {time_window['time_str']}",
                            "talkers": talker_names,
                            "task_prompt": task.prompt,
                        }
                        if message_stats_result:
                            prompt_meta["message_count"] = message_stats_result.total_messages
                        if getattr(task, "task_type", "report") == "export":
                            message_stats_github_artifact = await self._sync_message_stats_to_github(
                                db=db,
                                task=task,
                                job=job,
                                execution=execution,
                                time_window=time_window,
                                stats=message_stats_result,
                            )
                            if message_stats_github_artifact:
                                exported_files.append(message_stats_github_artifact)
                            execution.raw_request = json.dumps(
                                {
                                    **prompt_meta,
                                    "task_type": "export",
                                    "llm_skipped": True,
                                },
                                ensure_ascii=False,
                            )
                            execution.status = "success"
                            execution.summary_md = "数据导出完成，未调用 LLM。"
                            execution.summary_path = None
                            execution.prompt_usage = json.dumps(
                                {"chars": {"total": 0}, "tokens": {"total": 0}},
                                ensure_ascii=False,
                            )
                            execution.prompt_chars = 0
                            execution.prompt_tokens = 0
                            execution.completion_tokens = 0
                            execution.llm_model_name = None
                            execution.deploy_status = "none"
                            execution.deploy_url = None
                            execution.deploy_error = None
                            execution.github_config_id = None
                            if attempt > 1:
                                logger.info("Job %s 在第 %s 次重试后成功", job.id, attempt)
                            break
                        system_instruction_for_usage: Optional[str] = None
                        system_instruction_text = self._build_system_instruction(
                            task,
                            talker_names,
                            time_window,
                            message_stats_result,
                        )
                        system_instruction_for_usage = system_instruction_text
                        html_required = self._job_requires_html_output(job)
                        allow_outer_retry = False
                        ai_result = await self._generate_summary_with_model_sequence(
                            db=db,
                            task=task,
                            job=job,
                            talker_names=talker_names,
                            time_window=time_window,
                            chatlog_text=chatlog_text,
                            system_instruction_text=system_instruction_text,
                            message_stats_result=message_stats_result,
                            html_required=html_required,
                            max_ai_requests=attempts,
                        )
                        summary = ai_result.summary
                        prompt_tokens = ai_result.prompt_tokens
                        completion_tokens = ai_result.completion_tokens
                        prompt_meta.update(ai_result.prompt_meta)
                        usage_stats = compute_prompt_usage(task.prompt, system_instruction_for_usage or "", chatlog_text)
                        execution.raw_request = json.dumps(prompt_meta, ensure_ascii=False)
                        execution.status = "success"
                        execution.summary_md = summary
                        summary_snapshot = summary
                        execution.summary_path = None
                        model_output_artifacts = self._store_model_output_backups(
                            task,
                            job,
                            execution,
                            summary_snapshot or "",
                            time_window,
                        )
                        model_output_paths = [item.get("path") for item in model_output_artifacts if item.get("path")]
                        if model_output_artifacts:
                            exported_files.extend(model_output_artifacts)
                        await self._sync_execution_outputs_to_ima(
                            db,
                            task=task,
                            job=job,
                            execution=execution,
                            file_paths=model_output_paths,
                        )
                        execution.prompt_usage = json.dumps(usage_stats, ensure_ascii=False)
                        execution.prompt_chars = usage_stats["chars"]["total"]
                        execution.prompt_tokens = prompt_tokens
                        final_completion_tokens = completion_tokens
                        if final_completion_tokens is None and summary_snapshot:
                            final_completion_tokens = count_tokens(summary_snapshot)
                        execution.completion_tokens = final_completion_tokens
                        execution.llm_model_name = ai_result.model.provider if ai_result.model else None
                        if getattr(task, "task_type", "report") == "topic_card":
                            summary = await self._handle_topic_card_result(
                                db=db,
                                task=task,
                                job=job,
                                execution=execution,
                                raw_response=summary_snapshot or "",
                            )
                            summary_snapshot = summary
                            execution.summary_md = summary
                            execution.summary_path = None
                            execution.html_backup_path = None
                            execution.deploy_status = "none"
                            execution.deploy_url = None
                            execution.deploy_error = None
                            execution.github_config_id = None
                            message_stats_github_artifact = await self._sync_message_stats_to_github(
                                db=db,
                                task=task,
                                job=job,
                                execution=execution,
                                time_window=time_window,
                                stats=message_stats_result,
                            )
                            if message_stats_github_artifact:
                                exported_files.append(message_stats_github_artifact)
                            if attempt > 1:
                                logger.info("Job %s 在第 %s 次重试后成功", job.id, attempt)
                            break
                        html_plan: Optional[HtmlArtifactPlan] = None
                        html_content: Optional[str] = None
                        if html_required:
                            html_plan = self._render_html_plan(job, execution, datetime.now(tz=self._tz), time_window)
                            html_content = self._extract_html_document(summary)

                        if job.html_backup_enabled and html_content and html_plan:
                            execution.html_backup_path = self._store_html_report(
                                task,
                                job,
                                execution,
                                html_content,
                                time_window,
                                html_plan,
                            )
                            if execution.html_backup_path:
                                exported_files.append(
                                    {
                                        "type": "html_backup",
                                        "label": "HTML 备份",
                                        "path": execution.html_backup_path,
                                    }
                                )
                        else:
                            execution.html_backup_path = None

                        if job.github_deploy_enabled:
                            if deployment_record is None:
                                deployment_record = GithubDeployment(
                                    execution_id=execution.id,
                                    job_id=job.id,
                                    task_id=task.id,
                                    github_config_id=job.github_config_id,
                                    job_name=job.name,
                                    task_name=task.name,
                                    config_name=job.github_config.name if job.github_config else None,
                                    artifact_type="html_report",
                                    artifact_label="HTML 日报",
                                    repo_full_name=(
                                        f"{job.github_config.owner}/{job.github_config.repo}"
                                        if job.github_config
                                        else None
                                    ),
                                    branch=(
                                        (job.github_config.branch or "main").strip() or "main"
                                        if job.github_config
                                        else None
                                    ),
                                    status="running",
                                    started_at=datetime.now(tz=self._tz).replace(tzinfo=None),
                                )
                                db.add(deployment_record)
                                db.flush()
                            if not html_content or not html_plan:
                                raise RuntimeError("GitHub 部署要求模型返回完整 HTML")
                            try:
                                deploy_artifact = await self._retry_async(
                                    lambda: self._deploy_html_to_github(
                                        job=job,
                                        execution=execution,
                                        html_content=html_content,
                                        plan=html_plan,
                                    ),
                                    retries=max_retry,
                                    retry_interval=retry_interval,
                                    label="GitHub HTML 日报上传",
                                )
                                if deployment_record:
                                    deployment_record.status = "success"
                                    deployment_record.pages_url = deploy_artifact.pages_url
                                    deployment_record.repo_path = deploy_artifact.repo_path
                                    deployment_record.repo_full_name = deploy_artifact.repo_full_name
                                    deployment_record.branch = deploy_artifact.branch
                                    deployment_record.github_file_url = deploy_artifact.github_file_url
                                    deployment_record.error_msg = None
                                    deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                                view_url = (
                                    build_view_url(deployment_record, fallback_url=deploy_artifact.pages_url)
                                    if deployment_record
                                    else deploy_artifact.pages_url
                                )
                                execution.deploy_status = "success"
                                execution.deploy_url = view_url
                                execution.deploy_error = None
                                execution.github_config_id = job.github_config_id
                                exported_files.append(
                                    {
                                        "type": "github",
                                        "label": "GitHub 页面",
                                        "url": view_url,
                                        "path": deploy_artifact.repo_path,
                                        "repo_path": deploy_artifact.repo_path,
                                        "repo": deploy_artifact.repo_full_name,
                                        "branch": deploy_artifact.branch,
                                        "github_file_url": deploy_artifact.github_file_url,
                                        "deployment_record_id": deployment_record.id if deployment_record else None,
                                        "deployment_status": "success",
                                    }
                                )
                            except Exception as deploy_exc:
                                deploy_error = _format_exception_message("GitHub HTML 日报上传", deploy_exc)
                                execution.deploy_status = "failed"
                                execution.deploy_error = deploy_error
                                execution.github_config_id = job.github_config_id
                                if deployment_record:
                                    deployment_record.status = "failed"
                                    deployment_record.error_msg = deploy_error
                                    deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                                raise
                        else:
                            execution.deploy_status = "none"
                            execution.deploy_url = None
                            execution.deploy_error = None
                            execution.github_config_id = None

                        message_stats_github_artifact = await self._sync_message_stats_to_github(
                            db=db,
                            task=task,
                            job=job,
                            execution=execution,
                            time_window=time_window,
                            stats=message_stats_result,
                        )
                        if message_stats_github_artifact:
                            exported_files.append(message_stats_github_artifact)

                        push_webhook_ids = _parse_int_list(task.push_webhook_ids)
                        if push_webhook_ids:
                            webhooks = webhook_repo.get_by_ids(db, push_webhook_ids)
                            logger.info("准备推送飞书 job_id={} job_name={}", job.id, job.name)
                            await self._retry_async(
                                lambda: self._push_feishu(
                                    webhooks=webhooks,
                                    task=task,
                                    job=job,
                                    summary=summary,
                                    raise_on_failure=True,
                                ),
                                retries=max_retry,
                                retry_interval=retry_interval,
                                label="飞书推送",
                            )
                        if attempt > 1:
                            logger.info("Job %s 在第 %s 次重试后成功", job.id, attempt)
                        break
                    except asyncio.CancelledError as exc:
                        db.rollback()
                        if summary_snapshot:
                            execution.summary_md = summary_snapshot
                        execution.chatlog_path = execution.chatlog_path or chatlog_path
                        execution.status = "failed"
                        if not execution.error_msg:
                            reason = str(exc).strip()
                            if reason:
                                execution.error_msg = f"执行被取消：{reason}"
                            else:
                                execution.error_msg = "执行被取消：可能由于服务重启或进程退出"
                        if deployment_record and execution.deploy_status != "success":
                            deployment_record.status = "failed"
                            if execution.deploy_error:
                                deployment_record.error_msg = execution.deploy_error
                            deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                        if not execution.raw_request and time_window:
                            fallback_meta = {
                                "task_name": task.name,
                                "chatlog_range": time_window.get("time_str"),
                                "chatlog_label": f"{', '.join(talker_names)} · {time_window.get('time_str')}",
                                "talkers": talker_names,
                                "task_prompt": task.prompt,
                            }
                            if message_stats_result:
                                fallback_meta["message_count"] = message_stats_result.total_messages
                            execution.raw_request = json.dumps(fallback_meta, ensure_ascii=False)
                        logger.warning("Job %s 执行被取消: %s", job.id, exc)
                        raise
                    except Exception as exc:  # pragma: no cover - protect scheduler
                        db.rollback()
                        raw_summary = getattr(exc, "raw_summary", None)
                        if raw_summary and not summary_snapshot:
                            summary_snapshot = raw_summary
                        if summary_snapshot:
                            execution.summary_md = summary_snapshot
                        execution.error_msg = _format_exception_message("执行", exc)
                        execution.chatlog_path = execution.chatlog_path or chatlog_path
                        if allow_outer_retry and attempt <= max_retry:
                            logger.warning(
                                "Job %s 第 %s/%s 次执行失败，将在 %s 秒后重试: %s",
                                job.id,
                                attempt,
                                attempts,
                                retry_interval,
                                execution.error_msg,
                            )
                            await asyncio.sleep(retry_interval)
                            db.refresh(execution)
                            db.refresh(job)
                            continue

                        execution.status = "failed"
                        if deployment_record and execution.deploy_status != "success":
                            deployment_record.status = "failed"
                            if execution.deploy_error:
                                deployment_record.error_msg = execution.deploy_error
                            deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                        if not execution.raw_request and time_window:
                            fallback_meta = {
                                "task_name": task.name,
                                "chatlog_range": time_window.get("time_str"),
                                "chatlog_label": f"{', '.join(talker_names)} 路 {time_window.get('time_str')}",
                                "talkers": talker_names,
                                "task_prompt": task.prompt,
                            }
                            if message_stats_result:
                                fallback_meta["message_count"] = message_stats_result.total_messages
                            execution.raw_request = json.dumps(fallback_meta, ensure_ascii=False)
                        alert_service.create_alert(
                            db,
                            task_id=task.id,
                            job_id=job.id,
                            execution_id=execution.id,
                            category="execution",
                            message=execution.error_msg,
                            payload={"job_id": job.id},
                        )
                        await self._notify_alert_webhooks(db, task, job, execution.error_msg)
                        logger.exception("Job %s failed finally", job.id)
                        break
            finally:
                execution.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
                execution.duration_ms = int(
                    (execution.finished_at - (execution.started_at or execution.finished_at)).total_seconds() * 1000
                )
                execution.exported_files = (
                    json.dumps(exported_files, ensure_ascii=False) if exported_files else None
                )
                disk_record: Optional[DiskIoRecord] = None
                try:
                    disk_record = disk_monitor_service.finish_execution_io(
                        db,
                        context=disk_io_context,
                        execution=execution,
                        task=task,
                        job=job,
                        exported_files=exported_files,
                        chat_record_telemetry=chat_record_telemetry,
                    )
                except Exception:
                    logger.exception("记录磁盘 IO 失败 execution_id=%s", execution.id)
                if disk_record:
                    await self._handle_job_disk_alert(
                        db=db,
                        task=task,
                        job=job,
                        execution=execution,
                        disk_record=disk_record,
                    )
                db.add(execution)
                job.last_run_at = execution.finished_at
                if job.interval_enabled:
                    next_run = self._schedule_job(job)
                    job.next_run_at = next_run
                else:
                    job.next_run_at = self._calculate_next_run(job)
                db.add(job)
                db.commit()
        return execution_id

    def _calculate_time_window(self, job: Job, window_override: Optional[dict] = None, is_manual: bool = False) -> dict:
        if window_override:
            start = window_override["start"]
            end = window_override["end"]
            start, end = self._apply_offset(start, end, job.offset_minutes)
            return self._build_window_payload(start, end)

        custom_range = self._extract_custom_time_range(job)
        if custom_range:
            return custom_range

        if job.schedule_type == "weekly_report":
            start, end = self._calculate_weekly_report_window(job)
            start, end = self._apply_offset(start, end, job.offset_minutes)
            return self._build_window_payload(start, end)

        if job.interval_enabled:
            start, end = self._calculate_manual_interval_window(job)
        elif is_manual and _time_str_to_minutes(job.execution_time or job.start_time) >= 24 * 60:
            start, end = self._calculate_manual_fixed_window(job)
        else:
            start, end = self._calculate_fixed_window(job)

        start, end = self._apply_offset(start, end, job.offset_minutes)
        return self._build_window_payload(start, end)

    def _build_window_payload(self, start: datetime, end: datetime) -> dict:
        return {
            "start": start,
            "end": end,
            "time_str": f"{start.strftime('%Y-%m-%d %H:%M')}~{end.strftime('%Y-%m-%d %H:%M')}",
        }

    def _apply_offset(self, start: datetime, end: datetime, offset_minutes: int) -> Tuple[datetime, datetime]:
        if not offset_minutes:
            return start, end
        delta = timedelta(minutes=offset_minutes)
        return start + delta, end + delta

    def _calculate_fixed_window(self, job: Job) -> Tuple[datetime, datetime]:
        now = datetime.now(tz=self._tz)
        execution_day = self._determine_execution_day(now, job)
        return self._calculate_fixed_window_for_execution_day(job, execution_day)

    def _calculate_fixed_window_for_execution_day(self, job: Job, execution_day: date) -> Tuple[datetime, datetime]:
        start_minutes = _time_str_to_minutes(job.start_time)
        end_minutes = _time_str_to_minutes(job.end_time)

        start_day = execution_day
        end_day = execution_day
        if job.date_baseline == "previous_day":
            start_day = execution_day - timedelta(days=1)
        elif job.date_baseline == "current_day" and start_minutes > end_minutes:
            start_day = execution_day - timedelta(days=1)

        start_dt = _combine_date_minutes(start_day, start_minutes, self._tz)
        end_dt = _combine_date_minutes(end_day, end_minutes, self._tz)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return start_dt, end_dt

    def _calculate_manual_fixed_window(self, job: Job, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
        current = now or datetime.now(tz=self._tz)
        if current.tzinfo is None:
            current = current.replace(tzinfo=self._tz)
        candidate_day = current.date()
        for _ in range(3):
            start_dt, end_dt = self._calculate_fixed_window_for_execution_day(job, candidate_day)
            if end_dt <= current:
                return start_dt, end_dt
            candidate_day -= timedelta(days=1)
        return self._calculate_fixed_window_for_execution_day(job, candidate_day)

    def _determine_execution_day(self, now: datetime, job: Job) -> date:
        exec_minutes = _time_str_to_minutes(job.execution_time or job.start_time)
        if exec_minutes >= 24 * 60:
            return (now - timedelta(days=1)).date()
        return now.date()

    def _calculate_manual_interval_window(self, job: Job) -> Tuple[datetime, datetime]:
        interval_minutes = int(job.interval_minutes or 0)
        if interval_minutes <= 0:
            raise RuntimeError("按间隔执行配置缺少间隔频率")
        now = datetime.now(tz=self._tz)
        window_start_minutes = _time_str_to_minutes(job.window_start or "00:00")
        window_end_minutes = _time_str_to_minutes(job.window_end or "24:00")
        if window_end_minutes <= window_start_minutes:
            raise RuntimeError("生效范围的结束时间必须晚于开始时间")
        day_start = now.date()
        range_start = _combine_date_minutes(day_start, window_start_minutes, self._tz)
        range_end = _combine_date_minutes(day_start, window_end_minutes, self._tz)

        window_end = now
        if window_end < range_start:
            window_end = range_start
        if window_end > range_end:
            window_end = range_end

        window_start = window_end - timedelta(minutes=interval_minutes)
        if window_start < range_start:
            window_start = range_start
        return window_start, window_end

    def _calculate_weekly_report_window(self, job: Job) -> Tuple[datetime, datetime]:
        now = datetime.now(tz=self._tz)
        execution_day = self._determine_execution_day(now, job)
        base_week_start = execution_day - timedelta(days=execution_day.weekday())
        period = (getattr(job, "weekly_period", None) or "previous_week").lower()
        if period != "current_week":
            base_week_start -= timedelta(days=7)
        start_day_idx = int(getattr(job, "weekly_start_day", 0) or 0)
        end_day_idx = int(getattr(job, "weekly_end_day", 6) or 6)
        start_minutes = _time_str_to_minutes(getattr(job, "weekly_start_time", None) or "00:00")
        end_minutes = _time_str_to_minutes(getattr(job, "weekly_end_time", None) or "24:00")
        start_date = base_week_start + timedelta(days=max(0, min(6, start_day_idx)))
        end_date = base_week_start + timedelta(days=max(0, min(6, end_day_idx)))
        start_dt = _combine_date_minutes(start_date, start_minutes, self._tz)
        end_dt = _combine_date_minutes(end_date, end_minutes, self._tz)
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(days=7)
        return start_dt, end_dt

    def _compute_next_interval_plan(self, job: Job) -> Optional[IntervalPlan]:
        if not job.interval_minutes or job.interval_minutes <= 0:
            return None
        search_start = datetime.now(tz=self._tz)
        shared_plan = compute_shared_interval_plan(
            search_start=search_start,
            interval_minutes=int(job.interval_minutes),
            window_start_minutes=_time_str_to_minutes(job.window_start or "00:00"),
            window_end_minutes=_time_str_to_minutes(job.window_end or "24:00"),
            tz=self._tz,
            date_allowed=lambda day: self._is_date_allowed(job, day),
            first_fire_minutes=_time_str_to_minutes(job.execution_time or job.start_time),
            max_days=60,
        )
        if not shared_plan:
            return None
        return IntervalPlan(
            fire_time=shared_plan.fire_time,
            window_start=shared_plan.window_start,
            window_end=shared_plan.window_end,
        )

    def _build_daily_interval_plans(self, job: Job, day: date) -> List[IntervalPlan]:
        interval_minutes = int(job.interval_minutes or 0)
        if interval_minutes <= 0:
            return []
        shared_plans = build_shared_interval_plans(
            day=day,
            interval_minutes=interval_minutes,
            window_start_minutes=_time_str_to_minutes(job.window_start or "00:00"),
            window_end_minutes=_time_str_to_minutes(job.window_end or "24:00"),
            tz=self._tz,
            first_fire_minutes=_time_str_to_minutes(job.execution_time or job.start_time),
        )
        return [
            IntervalPlan(
                fire_time=plan.fire_time,
                window_start=plan.window_start,
                window_end=plan.window_end,
            )
            for plan in shared_plans
        ]

    def _is_date_allowed(self, job: Job, candidate: date) -> bool:
        if not self._is_date_within_active_range(job, candidate):
            return False
        weekday = candidate.weekday()
        if job.schedule_type == "daily":
            return True
        if job.schedule_type == "weekday":
            return weekday < 5
        if job.schedule_type == "weekend":
            return weekday >= 5
        if job.schedule_type == "weekly":
            weekdays = _load_weekdays(job.weekdays)
            return weekday in weekdays if weekdays else True
        if job.schedule_type == "weekly_report":
            weekdays = _load_weekdays(job.weekdays)
            return weekday in weekdays if weekdays else True
        if job.schedule_type == "custom_cron":
            logger.warning("作业 %s 使用自定义 Cron，跳过按间隔执行", job.id)
            return False
        return True

    def _is_date_within_active_range(self, job: Job, candidate: date) -> bool:
        parsed = self._parse_active_range(job)
        if not parsed:
            return True
        start, end = parsed
        return start.date() <= candidate <= end.date()

    def _extract_custom_time_range(self, job: Job) -> Optional[dict]:
        description = job.description or ""
        time_range: Optional[str] = None
        if description:
            try:
                data = json.loads(description)
            except json.JSONDecodeError:
                match = re.search(
                    r"(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)\s*(?:~|—|–|-)\s*(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2})?)",
                    description,
                )
                if match:
                    time_range = f"{match.group(1)}~{match.group(2)}"
            else:
                if isinstance(data, dict):
                    if data.get("time_range"):
                        time_range = str(data["time_range"])
                    else:
                        window_config = data.get("relative_window") or data.get("window")
                        if isinstance(window_config, dict):
                            relative = self._calculate_relative_time_window(window_config)
                            if relative:
                                return relative

        if not time_range:
            return None

        parsed = self._parse_time_range(time_range)
        if not parsed:
            logger.warning("Job %s time_range parse failed: %s", job.id, time_range)
            return None
        return parsed

    def _parse_time_range(self, time_range: str) -> Optional[dict]:
        if "~" not in time_range:
            return None
        start_raw, end_raw = [part.strip() for part in time_range.split("~", 1)]

        def _parse(part: str) -> Optional[datetime]:
            formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
            for fmt in formats:
                try:
                    dt = datetime.strptime(part, fmt)
                    return dt
                except ValueError:
                    continue
            return None

        start_dt = _parse(start_raw)
        end_dt = _parse(end_raw)
        if not start_dt or not end_dt:
            return None

        start_dt = start_dt.replace(tzinfo=self._tz).astimezone(self._tz).replace(tzinfo=None)
        end_dt = end_dt.replace(tzinfo=self._tz).astimezone(self._tz).replace(tzinfo=None)
        if end_dt <= start_dt:
            logger.warning("Invalid time range %s <= %s", end_dt, start_dt)
            return None
        return {
            "start": start_dt,
            "end": end_dt,
            "time_str": f"{start_raw}~{end_raw}",
        }

    def _calculate_relative_time_window(self, config: dict) -> Optional[dict]:
        try:
            end_offset = int(config.get("end_offset_minutes", 0))
        except (TypeError, ValueError):
            return None
        start_offset = config.get("start_offset_minutes")
        duration = config.get("duration_minutes")
        if start_offset is None:
            if duration is None:
                return None
            try:
                duration_minutes = int(duration)
            except (TypeError, ValueError):
                return None
            start_offset_minutes = end_offset - duration_minutes
        else:
            try:
                start_offset_minutes = int(start_offset)
            except (TypeError, ValueError):
                return None
        now = datetime.now(tz=self._tz)
        start_dt = (now + timedelta(minutes=start_offset_minutes)).replace(second=0, microsecond=0)
        end_dt = (now + timedelta(minutes=end_offset)).replace(second=0, microsecond=0)
        if end_dt <= start_dt:
            return None
        start_local = start_dt.astimezone(self._tz).replace(tzinfo=None)
        end_local = end_dt.astimezone(self._tz).replace(tzinfo=None)
        return {
            "start": start_local,
            "end": end_local,
            "time_str": f"{start_local.strftime('%Y-%m-%d %H:%M')}~{end_local.strftime('%Y-%m-%d %H:%M')}",
        }

    def _parse_active_range(self, job: Job) -> Optional[tuple[datetime, datetime]]:
        description = job.description or ""
        if not description:
            return None
        try:
            data = json.loads(description)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        active_range = data.get("active_range")
        if not isinstance(active_range, str) or "~" not in active_range:
            return None
        start_raw, end_raw = [part.strip() for part in active_range.split("~", 1)]
        formats = ["%Y-%m-%d"]
        start = None
        end = None
        for fmt in formats:
            try:
                start = datetime.strptime(start_raw, fmt)
                break
            except ValueError:
                continue
        for fmt in formats:
            try:
                end = datetime.strptime(end_raw, fmt)
                break
            except ValueError:
                continue
        if not start or not end:
            return None
        start = datetime(start.year, start.month, start.day, tzinfo=self._tz)
        end = datetime(end.year, end.month, end.day, 23, 59, 59, 999999, tzinfo=self._tz)
        start = start.astimezone(self._tz).replace(tzinfo=None)
        end = end.astimezone(self._tz).replace(tzinfo=None)
        return start, end

    def _is_within_active_range(self, job: Job) -> bool:
        parsed = self._parse_active_range(job)
        if not parsed:
            return True
        start, end = parsed
        now = datetime.now(tz=self._tz).replace(tzinfo=None)
        # Inclusive range
        return start <= now <= end

    async def _collect_chatlog(self, talkers: List[str], time_window: dict, telemetry: Optional[dict] = None) -> str:
        return await chat_record_service.collect_messages(talkers, time_window, telemetry=telemetry)

    def _compose_prompt(self, prompt_template: str, system_instruction: str, chatlog_text: str) -> str:
        return f"聊天记录:\n{chatlog_text}\n\n{system_instruction}\n\n{prompt_template}"

    def _job_requires_html_output(self, job: Job) -> bool:
        return bool(getattr(job, "github_deploy_enabled", False) or getattr(job, "html_backup_enabled", False))

    def _resolve_model_sequence(self, db, task: Task) -> List[ModelSequenceItem]:
        raw_sequence = getattr(task, "model_sequence", None)
        items: list[dict[str, Any]] = []
        if raw_sequence:
            try:
                parsed = json.loads(raw_sequence) if isinstance(raw_sequence, str) else raw_sequence
                if isinstance(parsed, list):
                    items = [item for item in parsed if isinstance(item, dict)]
            except json.JSONDecodeError:
                items = []
        if not items and getattr(task, "model_id", None):
            items = [{"model_id": task.model_id, "max_attempts": 2}]
        sequence: List[ModelSequenceItem] = []
        for item in items:
            model_id = int(item.get("model_id") or 0)
            if model_id <= 0:
                continue
            model = db.query(Model).filter(Model.id == model_id).first()
            if not model:
                raise RuntimeError(f"模型不存在：{model_id}")
            max_attempts = max(int(item.get("max_attempts") or 2), 1)
            sequence.append(ModelSequenceItem(model=model, max_attempts=max_attempts))
        if not sequence:
            raise RuntimeError("任务未绑定模型")
        return sequence

    async def _generate_summary_with_model_sequence(
        self,
        *,
        db,
        task: Task,
        job: Job,
        talker_names: List[str],
        time_window: dict,
        chatlog_text: str,
        system_instruction_text: str,
        message_stats_result: Optional[message_stats_utils.MessageStats],
        html_required: bool,
        max_ai_requests: int,
    ) -> AiSummaryResult:
        sequence = self._resolve_model_sequence(db, task)
        attempt_meta: list[dict[str, Any]] = []
        requests_used = 0
        last_error: Optional[Exception] = None
        for entry in sequence:
            model_attempts = 0
            while model_attempts < entry.max_attempts and requests_used < max_ai_requests:
                model_attempts += 1
                requests_used += 1
                model = entry.model
                try:
                    prompt = self._compose_prompt(task.prompt, system_instruction_text, chatlog_text)
                    summary, prompt_tokens, completion_tokens = await self._invoke_llm(model, prompt)
                    prompt_meta = {
                        "chunked": False,
                        "system_instruction": system_instruction_text,
                    }
                    try:
                        self._validate_ai_output(
                            task=task,
                            job=job,
                            summary=summary,
                            html_required=html_required,
                        )
                    except Exception as exc:
                        raise AIOutputValidationError(str(exc), raw_summary=summary) from exc
                    attempt_meta.append(
                        {
                            "model_id": model.id,
                            "model_name": model.provider,
                            "attempt": model_attempts,
                            "status": "success",
                        }
                    )
                    prompt_meta["model_attempts"] = attempt_meta
                    prompt_meta["selected_model_id"] = model.id
                    prompt_meta["selected_model_name"] = model.provider
                    return AiSummaryResult(
                        summary=summary,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        model=model,
                        prompt_meta=prompt_meta,
                    )
                except Exception as exc:
                    last_error = exc
                    attempt_meta.append(
                        {
                            "model_id": getattr(entry.model, "id", None),
                            "model_name": getattr(entry.model, "provider", None),
                            "attempt": model_attempts,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                    logger.warning(
                        "Job %s 模型 %s 第 %s 次 AI 请求失败（总请求 %s/%s）：%s",
                        job.id,
                        getattr(entry.model, "provider", None),
                        model_attempts,
                        requests_used,
                        max_ai_requests,
                        exc,
                    )
                    if requests_used >= max_ai_requests:
                        break
            if requests_used >= max_ai_requests:
                break
        if isinstance(last_error, AIOutputValidationError):
            raise AIOutputValidationError(
                f"AI 请求全部失败：{last_error}",
                raw_summary=last_error.raw_summary,
            ) from last_error
        raise RuntimeError(f"AI 请求全部失败：{last_error}") from last_error

    def _validate_ai_output(self, *, task: Task, job: Job, summary: str, html_required: bool) -> None:
        if getattr(task, "task_type", "report") == "topic_card":
            style_config = topic_card_service.normalize_topic_style_config(getattr(task, "topic_style_config", None))
            topic_card_service.parse_topic_cards(summary, style_config=style_config)
            return
        if html_required:
            self._extract_html_document(summary)

    def _build_system_instruction(
        self,
        task: Task,
        talkers: List[str],
        time_window: dict,
        message_stats: Optional[message_stats_utils.MessageStats],
    ) -> str:
        default_prompt = (
            "请基于聊天记录，根据提示词完成任务。\n"
            f"时间范围: {time_window['time_str']}\n"
            f"群聊: {', '.join(talkers)}\n"
        )
        if not getattr(task, "system_prompt_custom_enabled", False):
            return default_prompt
        template = (getattr(task, "system_prompt_template", "") or "").strip()
        if not template:
            return default_prompt
        replacements = {
            "${time_range}": time_window.get("time_str", ""),
            "${chatroom_name}": ", ".join(talkers),
            "${message_count}": "",
        }
        if getattr(task, "system_prompt_include_message_count", False) and message_stats:
            replacements["${message_count}"] = str(message_stats.total_messages)
        result = template
        for token, value in replacements.items():
            result = result.replace(token, value)
        return result or default_prompt

    async def _invoke_llm(self, model, prompt: str) -> tuple[str, Optional[int], Optional[int]]:
        if not model:
            raise RuntimeError("任务未绑定模型")
        extra_payload = json.loads(model.extra) if model.extra else None
        result_chunks: List[str] = []
        prompt_tokens = None
        completion_tokens = None
        async for chunk in llm.stream_completion(model, prompt=prompt, extra_payload=extra_payload):
            text, prompt_tokens, completion_tokens = _parse_llm_chunk(
                chunk, prompt_tokens, completion_tokens
            )
            if text:
                result_chunks.append(text)

        summary = "".join(result_chunks).strip()
        if not summary:
            raise RuntimeError("模型返回为空")
        return summary, prompt_tokens, completion_tokens

    def _resolve_card_header(self, webhook, task: Task, job: Optional[Job]) -> tuple[str, str, str]:
        mode = (getattr(webhook, "card_mode", "markdown") or "markdown").lower()
        color = getattr(webhook, "card_header_color", None)
        template = color if color in CARD_COLOR_OPTIONS else "blue"
        default_title = (job.name if job and job.name else None) or task.name
        replacements = {
            "{task_name}": task.name or "",
            "{job_name}": job.name if job else "",
        }

        def apply_template(template_text: Optional[str], fallback: str) -> str:
            if not template_text:
                return fallback
            result = template_text
            for token, value in replacements.items():
                result = result.replace(token, value)
            result = result.strip()
            return result or fallback

        if mode != "markdown":
            return default_title, "", template

        if not bool(getattr(webhook, "card_header_enabled", False)):
            return default_title, "", template

        title = apply_template(getattr(webhook, "card_header_title", None), default_title)
        subtitle = apply_template(getattr(webhook, "card_header_subtitle", None), "")
        return title, subtitle, template

    async def _push_feishu(self, webhooks, task: Task, job: Optional[Job], summary: str, *, raise_on_failure: bool = False) -> bool:
        if not webhooks:
            return False
        succeeded = False
        failures: List[str] = []
        for webhook in webhooks:
            title, subtitle, template = self._resolve_card_header(webhook, task, job)
            try:
                await feishu.send_markdown(
                    webhook=webhook,
                    title=title,
                    subtitle=subtitle,
                    template=template,
                    content=summary,
                )
                succeeded = True
            except Exception as exc:
                failures.append(str(exc))
                logger.exception(
                    "推送飞书失败 webhook_id=%s task=%s job=%s",
                    getattr(webhook, "id", None),
                    task.id,
                    getattr(job, "id", None),
                )
        if raise_on_failure and failures:
            raise RuntimeError("飞书推送失败：" + "；".join(failures))
        return succeeded

    async def _retry_async(self, operation, *, retries: int, retry_interval: int, label: str):
        attempt = 0
        total = retries + 1
        while True:
            attempt += 1
            try:
                return await operation()
            except Exception as exc:
                if attempt >= total:
                    raise RuntimeError(_format_exception_message(label, exc, attempts=total)) from exc
                logger.warning(
                    "%s 第 %s/%s 次失败，将在 %s 秒后重试：%s",
                    label,
                    attempt,
                    total,
                    retry_interval,
                    _exception_detail(exc),
                )
                await asyncio.sleep(retry_interval)

    async def _deliver_topic_card_image(
        self,
        *,
        webhook,
        app_id: str,
        app_secret: str,
        image: topic_card_service.RenderedImage,
        retries: int,
        retry_interval: int,
    ) -> Dict[str, Any]:
        async def operation() -> str:
            image_bytes = image.path.read_bytes()
            image_key = await feishu.upload_image(
                app_id=app_id,
                app_secret=app_secret,
                image_bytes=image_bytes,
                filename=image.path.name,
            )
            await feishu.send_image(webhook, image_key=image_key, max_retries=1)
            return image_key

        image_key = await self._retry_async(
            operation,
            retries=retries,
            retry_interval=retry_interval,
            label="话题卡片图片推送",
        )
        return {
            "image_key": image_key,
            "width": image.width,
            "height": image.height,
            "size_bytes": image.size_bytes,
            "engine": image.engine,
            "layout": image.layout,
        }

    def _build_topic_card_image_failure_message(self, failures: List[Dict[str, Any]]) -> str:
        if not failures:
            return "话题卡片图片推送失败"
        if len(failures) == 1:
            return str(failures[0].get("error") or "话题卡片图片推送失败")
        details = []
        for item in failures:
            name = item.get("webhook_name") or f"Webhook {item.get('webhook_id') or '-'}"
            error = item.get("error") or "未知错误"
            details.append(f"{name}：{error}")
        return "话题卡片图片推送失败：" + "；".join(details)

    async def _handle_topic_card_result(
        self,
        *,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        raw_response: str,
    ) -> str:
        push_webhook_ids = _parse_int_list(task.push_webhook_ids)
        webhooks = webhook_repo.get_by_ids(db, push_webhook_ids) if push_webhook_ids else []
        meta: Dict[str, Any] = {
            "type": "topic_card",
            "text_layout": getattr(job, "topic_text_layout", "per_topic") or "per_topic",
            "image_enabled": bool(getattr(job, "topic_image_enabled", False)),
            "image_layout": getattr(job, "topic_image_layout", "single") or "single",
            "deliveries": [],
        }
        style_config = topic_card_service.normalize_topic_style_config(getattr(task, "topic_style_config", None))
        meta["style_config"] = style_config
        try:
            cards = topic_card_service.parse_topic_cards(raw_response, style_config=style_config)
        except Exception as exc:
            logger.exception("话题卡片 JSON 解析失败 task={} job={}", task.id, job.id)
            meta["parse_error"] = str(exc)
            execution.raw_response = json.dumps(meta, ensure_ascii=False)
            raise RuntimeError(f"话题卡片 JSON 解析失败：{exc}") from exc

        meta["cards"] = cards
        if not cards:
            summary = "本时段无职场话题讨论"
            meta["skipped"] = "empty_cards"
            execution.raw_response = json.dumps(meta, ensure_ascii=False)
            if webhooks:
                await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=summary)
            return summary

        text_messages = topic_card_service.build_text_messages(
            cards,
            layout=getattr(job, "topic_text_layout", "per_topic") or "per_topic",
            threshold=int(getattr(job, "topic_text_merge_threshold", 3) or 3),
        )
        summary = "\n\n---\n\n".join(text_messages)

        if webhooks and text_messages:
            if len(text_messages) == 1:
                await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=text_messages[0])
            else:
                for message in text_messages:
                    await self._push_feishu(webhooks=webhooks, task=task, job=job, summary=message)

        rendered_by_engine: dict[str, list[topic_card_service.RenderedImage]] = {}
        image_failures: List[Dict[str, Any]] = []
        if bool(getattr(job, "topic_image_enabled", False)) and webhooks:
            image_layout = topic_card_service.resolve_image_layout(
                getattr(job, "topic_image_layout", "single") or "single",
                len(cards),
                int(getattr(job, "topic_image_merge_threshold", 3) or 3),
            )
            max_retry = max(int(getattr(job, "max_retry", 0) or 0), 0)
            retry_interval = max(int(getattr(job, "retry_interval_sec", 0) or 0), 1)
            try:
                for webhook in webhooks:
                    delivery: Dict[str, Any] = {
                        "webhook_id": getattr(webhook, "id", None),
                        "webhook_name": getattr(webhook, "name", None),
                        "status": "pending",
                    }
                    try:
                        app_id = (getattr(webhook, "feishu_app_id", None) or "").strip()
                        secret_cipher = getattr(webhook, "feishu_app_secret_cipher", None)
                        if not app_id or not secret_cipher:
                            raise RuntimeError("Webhook 未配置飞书应用 App ID / App Secret，无法上传图片")
                        app_secret = decrypt_value(secret_cipher)
                        engine = getattr(webhook, "image_render_engine", "satori") or "satori"
                        cache_key = f"{engine}:{image_layout}"
                        if cache_key not in rendered_by_engine:
                            rendered_by_engine[cache_key] = await topic_card_service.render_images(
                                cards,
                                engine=engine,
                                layout=image_layout,
                            )
                        image_items = []
                        for image in rendered_by_engine[cache_key]:
                            image_items.append(
                                await self._deliver_topic_card_image(
                                    webhook=webhook,
                                    app_id=app_id,
                                    app_secret=app_secret,
                                    image=image,
                                    retries=max_retry,
                                    retry_interval=retry_interval,
                                )
                            )
                        delivery["status"] = "success"
                        delivery["images"] = image_items
                    except Exception as exc:
                        error_message = _format_exception_message("话题卡片图片推送", exc)
                        logger.exception(
                            "话题卡片图片推送失败 webhook={} task={} job={}",
                            getattr(webhook, "id", None),
                            task.id,
                            job.id,
                        )
                        delivery["status"] = "failed"
                        delivery["error"] = error_message
                        image_failures.append(
                            {
                                "webhook_id": getattr(webhook, "id", None),
                                "webhook_name": getattr(webhook, "name", None),
                                "error": error_message,
                            }
                        )
                    meta["deliveries"].append(delivery)
            finally:
                for images in rendered_by_engine.values():
                    topic_card_service.cleanup_images(images)

        if image_failures:
            error_message = self._build_topic_card_image_failure_message(image_failures)
            execution.status = "failed"
            execution.error_msg = error_message
            alert_service.create_alert(
                db,
                task_id=task.id,
                job_id=job.id,
                execution_id=execution.id,
                category="topic_card_image",
                message=error_message,
                payload={"job_id": job.id, "failures": image_failures},
            )
            await self._notify_alert_webhooks(db, task, job, error_message)

        execution.raw_response = json.dumps(meta, ensure_ascii=False)
        return summary

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
            logger.exception("推送作业磁盘告警失败 task=%s job=%s execution=%s", task.id, job.id, execution.id)
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
            logger.exception("推送告警到飞书失败 task=%s job=%s", task.id, getattr(job, "id", None))

    def _ensure_html_document(self, content: str) -> str:
        text = (content or "").lstrip("\ufeff").strip()
        if not text:
            raise RuntimeError("HTML 内容为空")
        lower = text.lstrip().lower()
        if not (lower.startswith("<!doctype html") or lower.startswith("<html")):
            raise RuntimeError("模型需返回完整 HTML（缺少 <!DOCTYPE html> 或 <html>）")
        if not text.rstrip().lower().endswith("</html>"):
            raise RuntimeError("模型需返回完整 HTML（缺少 </html>）")
        try:
            BeautifulSoup(text, "html5lib")
        except Exception as exc:
            raise RuntimeError("HTML 内容解析失败") from exc
        return text

    def _extract_html_document(self, content: str) -> str:
        html_source = _strip_markdown_fence(content)
        try:
            return self._ensure_html_document(html_source)
        except RuntimeError as first_error:
            text = (content or "").lstrip("\ufeff").strip()
            lower = text.lower()
            start = lower.find("<!doctype html")
            if start < 0:
                start = lower.find("<html")
            end = lower.rfind("</html>")
            if start < 0 or end < 0 or end < start:
                raise first_error
            end += len("</html>")
            return self._ensure_html_document(text[start:end])

    def _render_html_plan(
        self,
        job: Job,
        execution: Execution,
        generated_at: datetime,
        time_window: Optional[dict],
    ) -> HtmlArtifactPlan:
        template = getattr(job, "github_filename_template", None)
        if not template and job.github_config and job.github_config.filename_template:
            template = job.github_config.filename_template
        template = (template or "新茧群日报_{YYYY-MM-DD}.html").strip()
        days_offset = 0 if _is_weekly_report(job) else int(getattr(job, "days_offset", 0) or 0)
        target_date = generated_at + timedelta(days=days_offset)
        task_rel = getattr(job, "task", None)
        task_name = getattr(task_rel, "name", "") if task_rel else ""
        job_name = getattr(job, "name", "") or ""
        start_dt = target_date
        end_dt = target_date
        if time_window:
            maybe_start = time_window.get("start")
            if isinstance(maybe_start, datetime):
                start_dt = maybe_start
            maybe_end = time_window.get("end")
            if isinstance(maybe_end, datetime):
                end_dt = maybe_end
        end_reference = end_dt - timedelta(seconds=1) if end_dt > start_dt else end_dt
        replacements = {
            "{YYYY-MM-DD HH:MM}": target_date.strftime("%Y-%m-%d %H:%M"),
            "{YYYY-MM-DD}": target_date.strftime("%Y-%m-%d"),
            "{YYYYMMDD_HHmmss}": target_date.strftime("%Y%m%d_%H%M%S"),
            "{YYYYMMDD}": target_date.strftime("%Y%m%d"),
            "{task_name}": task_name,
            "{job_name}": job_name,
            "{job_id}": str(job.id),
            "{task_id}": str(job.task_id),
            "{execution_id}": str(execution.id or ""),
            "{week_start}": self._format_week_label(start_dt),
            "{week_end}": self._format_week_label(end_reference),
        }
        filename = template
        for placeholder, value in replacements.items():
            filename = filename.replace(placeholder, value)
        filename = _sanitize_filename(filename)
        if not filename.lower().endswith(".html"):
            filename = f"{filename}.html"
        return HtmlArtifactPlan(filename=filename, target_date=target_date, generated_at=generated_at)

    def _store_chatlog_backup(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        chatlog_text: str,
        time_window: dict | None,
    ) -> List[Dict[str, str]]:
        if not chatlog_text.strip():
            return []
        job_flag = getattr(job, "chatlog_backup_enabled", None)
        if job_flag is None:
            if not getattr(task, "store_chatlog", False):
                return []
            return self._store_chatlog_backup_legacy(task, job, chatlog_text, time_window)
        if not job_flag:
            return []
        return self._store_chatlog_backup_modern(task, job, execution, chatlog_text, time_window)

    def _store_chatlog_backup_legacy(
        self,
        task: Task,
        job: Job,
        chatlog_text: str,
        time_window: dict | None,
    ) -> List[Dict[str, str]]:
        try:
            subdir = self._backup_dir / f"task_{task.id}" / "chatlogs"
            subdir.mkdir(parents=True, exist_ok=True)

            start_label, end_label = self._format_window_labels(time_window)
            filename = f"{start_label} - {end_label}.txt" if end_label else f"{start_label}.txt"
            path = subdir / filename
            if path.exists():
                stamp = datetime.now(tz=self._tz).strftime("%Y%m%d_%H%M%S")
                filename = f"{start_label} - {end_label} ({stamp}).txt" if end_label else f"{start_label} ({stamp}).txt"
                path = subdir / filename
            normalized = self._format_chatlog_for_export(chatlog_text)
            path.write_text(normalized, encoding="utf-8")
            return [
                {
                    "type": "chatlog",
                    "label": "聊天记录（TXT）",
                    "path": str(path),
                }
            ]
        except Exception:
            logger.exception("Failed to store chatlog backup for task %s job %s", task.id, job.id)
            return []

    def _store_chatlog_backup_modern(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        chatlog_text: str,
        time_window: dict | None,
    ) -> List[Dict[str, str]]:
        try:
            formats = _parse_str_list(getattr(job, "chatlog_backup_formats", None)) or ["txt"]
            directory = self._resolve_output_dir(getattr(job, "chatlog_backup_path", None), "chatlogs")
            template = getattr(job, "chatlog_backup_filename_template", None) or "聊天记录_{week_start}_{week_end}"
            offset = int(getattr(job, "chatlog_backup_filename_date_offset_days", 0) or 0)
            base_name = self._render_output_basename(
                template,
                task=task,
                job=job,
                execution=execution,
                time_window=time_window or {},
                offset_days=offset,
                fallback="聊天记录",
                reference_dt=self._get_offset_reference_datetime(execution, time_window),
            )
            normalized = self._format_chatlog_for_export(chatlog_text)
            artifacts: List[Dict[str, str]] = []
            for fmt in formats:
                ext = fmt.lower()
                if ext not in {"md", "txt"}:
                    ext = "txt"
                filename = base_name if base_name.lower().endswith(f".{ext}") else f"{base_name}.{ext}"
                path = self._ensure_unique_path(directory / filename)
                path.write_text(normalized, encoding="utf-8")
                artifacts.append(
                    {
                        "type": "chatlog",
                        "label": f"聊天记录（{ext.upper()}）",
                        "path": str(path),
                    }
                )
            return artifacts
        except Exception:
            logger.exception("Failed to store chatlog backup for task %s job %s", task.id, job.id)
            return []

    def _format_chatlog_for_export(self, chatlog_text: str) -> str:
        if not chatlog_text:
            return chatlog_text
        lines = chatlog_text.splitlines()
        if not lines:
            return chatlog_text
        formatted: List[str] = []
        sender_pattern = message_stats_utils.SENDER_PATTERN
        for line in lines:
            stripped = line.strip()
            if stripped and sender_pattern.match(stripped):
                if formatted and formatted[-1] != "":
                    formatted.append("")
            formatted.append(line)
        return "\n".join(formatted).rstrip() + "\n"

    def _should_compute_message_stats(self, task: Task, job: Job) -> bool:
        task_requires_count = bool(
            getattr(task, "system_prompt_custom_enabled", False)
            and getattr(task, "system_prompt_include_message_count", False)
        )
        return task_requires_count or bool(getattr(job, "message_stats_enabled", False)) or bool(
            getattr(job, "message_stats_github_enabled", False)
        )

    def _export_message_stats_files(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        stats: Optional[message_stats_utils.MessageStats],
    ) -> List[Dict[str, str]]:
        if not getattr(job, "message_stats_enabled", False) or not stats:
            return []
        formats = _parse_str_list(getattr(job, "message_stats_formats", None))
        if not formats:
            formats = ["md"]
        directory = self._resolve_output_dir(getattr(job, "message_stats_path", None), "message_reports")
        template = getattr(job, "message_stats_filename_template", None) or "每日群成员发言数量统计_{YYYY-MM-DD}"
        raw_offset = getattr(job, "message_stats_filename_date_offset_days", 0) or 0
        offset = 0 if _is_weekly_report(job) else int(raw_offset)
        base_name = self._render_output_basename(
            template,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            offset_days=offset,
            fallback="每日群成员发言数量统计",
            reference_dt=self._get_offset_reference_datetime(execution, time_window),
        )
        time_label = self._format_time_range_label(time_window)
        artifacts: List[Dict[str, str]] = []
        for fmt in formats:
            ext = fmt.lower()
            if ext not in {"md", "csv", "xlsx"}:
                ext = "md"
            filename = base_name if base_name.lower().endswith(f".{ext}") else f"{base_name}.{ext}"
            path = self._ensure_unique_path(directory / filename)
            if ext == "md":
                content = message_stats_utils.render_markdown_report(
                    stats,
                    report_title=base_name,
                    time_range_label=time_label,
                )
                message_stats_utils.write_markdown(path, content)
            elif ext == "csv":
                message_stats_utils.export_csv(path, stats)
            elif ext == "xlsx":
                message_stats_utils.export_xlsx(path, stats)
            artifacts.append(
                {
                    "type": "message_stats",
                    "label": f"消息统计（{ext.upper()}）",
                    "path": str(path),
                }
            )
        return artifacts

    async def _sync_message_stats_to_github(
        self,
        *,
        db,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        stats: Optional[message_stats_utils.MessageStats],
    ) -> Optional[Dict[str, str]]:
        if not getattr(job, "message_stats_github_enabled", False):
            return None
        if not getattr(job, "message_stats_enabled", False):
            return None
        if not stats:
            return None

        config = getattr(job, "message_stats_github_config", None)
        if not config:
            raise RuntimeError("消息统计 GitHub 配置缺失")

        token = decrypt_value(config.token_cipher)
        branch = (config.branch or "main").strip() or "main"
        template = (
            getattr(job, "message_stats_github_filename_template", None)
            or "每日群成员发言数量统计_{YYYY-MM-DD}"
        )
        raw_offset = getattr(job, "message_stats_github_filename_date_offset_days", 0) or 0
        offset = 0 if _is_weekly_report(job) else int(raw_offset)
        reference_dt = self._get_offset_reference_datetime(execution, time_window)
        base_name = self._render_output_basename(
            template,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            offset_days=offset,
            fallback="每日群成员发言数量统计",
            reference_dt=reference_dt,
        )
        filename = base_name if base_name.lower().endswith(".md") else f"{base_name}.md"

        target_dt = reference_dt
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=self._tz)
        target_dt = target_dt + timedelta(days=offset)
        year_label = target_dt.strftime("%Y")
        year_short = target_dt.strftime("%y")
        month_label = str(int(target_dt.strftime("%m")))
        root = (getattr(job, "message_stats_github_root", None) or "xinjian").strip().strip("/ ")
        if not root:
            root = "xinjian"
        relative_dir = f"{root}/{year_label}年/{year_short}年{month_label}月消息统计"
        relative_path = f"{relative_dir}/{filename}"
        relative_path = self._compose_content_path(config.path_prefix, relative_path)
        repo_full_name = f"{config.owner}/{config.repo}"
        github_file_url = self._build_github_file_url(config, branch, relative_path)
        deployment_record = GithubDeployment(
            execution_id=execution.id,
            job_id=job.id,
            task_id=task.id,
            github_config_id=getattr(config, "id", None),
            job_name=job.name,
            task_name=task.name,
            config_name=config.name,
            artifact_type="message_stats",
            artifact_label="GitHub 消息统计",
            repo_full_name=repo_full_name,
            branch=branch,
            repo_path=relative_path,
            github_file_url=github_file_url,
            status="running",
            started_at=datetime.now(tz=self._tz).replace(tzinfo=None),
        )
        db.add(deployment_record)
        db.flush()
        time_label = self._format_time_range_label(time_window)
        content = message_stats_utils.render_markdown_report(
            stats,
            report_title=base_name,
            time_range_label=time_label,
        )
        commit_message = f"feat: sync message stats job {job.id} execution {execution.id}"
        max_retry = max(int(getattr(job, "max_retry", 0) or 0), 0)
        retry_interval = max(int(getattr(job, "retry_interval_sec", 0) or 0), 1)
        try:
            await self._retry_async(
                lambda: github.upload_text_file(
                    token=token,
                    owner=config.owner,
                    repo=config.repo,
                    branch=branch,
                    path=relative_path,
                    content=content,
                    commit_message=commit_message,
                ),
                retries=max_retry,
                retry_interval=retry_interval,
                label="GitHub 消息统计上传",
            )
        except Exception as exc:
            error_message = _format_exception_message("GitHub 消息统计上传", exc)
            deployment_record.status = "failed"
            deployment_record.error_msg = error_message
            deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
            raise
        deployment_record.status = "success"
        deployment_record.error_msg = None
        deployment_record.finished_at = datetime.now(tz=self._tz).replace(tzinfo=None)
        return {
            "type": "github_message_stats",
            "label": "GitHub 消息统计",
            "path": relative_path,
            "repo_path": relative_path,
            "repo": repo_full_name,
            "branch": branch,
            "github_file_url": github_file_url,
            "deployment_record_id": deployment_record.id,
            "deployment_status": "success",
        }

    async def _sync_execution_outputs_to_ima(
        self,
        db,
        *,
        task: Task,
        job: Job,
        execution: Execution,
        file_paths: Sequence[Optional[str]],
    ) -> None:
        try:
            from ..services import ima_sync_service

            valid_paths = [path for path in file_paths if path]
            await ima_sync_service.sync_execution_outputs(
                db,
                task=task,
                job=job,
                execution=execution,
                file_paths=valid_paths,
            )
        except Exception as exc:  # pragma: no cover - protect main flow
            logger.exception("执行后同步到 IMA 失败 execution_id=%s", execution.id)
            execution.ima_sync_status = "failed"
            execution.ima_sync_error = str(exc)
            db.add(execution)
            db.flush()

    def _store_model_output_backups(
        self,
        task: Task,
        job: Job,
        execution: Execution,
        content: str,
        time_window: dict,
    ) -> List[Dict[str, str]]:
        if not getattr(job, "model_output_backup_enabled", False):
            return []
        text = (content or "").strip()
        if not text:
            return []
        formats = _parse_str_list(getattr(job, "model_output_formats", None)) or ["md"]
        directory = self._resolve_output_dir(getattr(job, "model_output_path", None), "model_outputs")
        template = getattr(job, "model_output_filename_template", None) or "模型输出_{YYYY-MM-DD}"
        raw_offset = getattr(job, "model_output_filename_date_offset_days", 0) or 0
        offset = 0 if _is_weekly_report(job) else int(raw_offset)
        base_name = self._render_output_basename(
            template,
            task=task,
            job=job,
            execution=execution,
            time_window=time_window,
            offset_days=offset,
            fallback="模型输出",
            reference_dt=self._get_offset_reference_datetime(execution, time_window),
        )
        normalized = text if text.endswith("\n") else f"{text}\n"
        artifacts: List[Dict[str, str]] = []
        for fmt in formats:
            ext = fmt.lower()
            if ext not in {"md", "txt"}:
                ext = "md"
            filename = base_name if base_name.lower().endswith(f".{ext}") else f"{base_name}.{ext}"
            path = self._ensure_unique_path(directory / filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(normalized, encoding="utf-8")
            artifacts.append(
                {
                    "type": "model_output",
                    "label": f"模型返回结果（{ext.upper()}）",
                    "path": str(path),
                }
            )
        return artifacts

    def _store_html_report(
        self,
        task,
        job: Job,
        execution: Execution,
        html_content: str,
        time_window: dict | None,
        plan: HtmlArtifactPlan,
    ) -> Optional[str]:
        try:
            custom_dir = getattr(job, "html_backup_path", None)
            default_dir = self._backup_dir / "html_reports" / plan.target_date.strftime("%Y")
            default_dir.mkdir(parents=True, exist_ok=True)
            base_dir = (
                self._resolve_output_dir(custom_dir, default_dir)
                if custom_dir
                else default_dir
            )
            filename = plan.filename
            override_template = getattr(job, "html_backup_filename_template", None)
            if override_template:
                base_name = self._render_output_basename(
                    override_template,
                    task=task,
                    job=job,
                    execution=execution,
                    time_window=time_window or {},
                    offset_days=0 if _is_weekly_report(job) else int(getattr(job, "html_backup_filename_date_offset_days", 0) or 0),
                    fallback=plan.filename.rsplit(".", 1)[0],
                    reference_dt=self._get_offset_reference_datetime(execution, time_window),
                )
                filename = base_name if base_name.lower().endswith(".html") else f"{base_name}.html"
            path = base_dir / filename
            path.write_text(html_content, encoding="utf-8")
            return str(path)
        except Exception:
            logger.exception("Failed to store HTML backup job=%s execution=%s", job.id, execution.id)
            return None

    def _resolve_output_dir(self, configured_path: Optional[str], default_subdir: str | Path) -> Path:
        base = Path(default_subdir)
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if not candidate.is_absolute():
                candidate = self._backup_dir / candidate
        else:
            candidate = base if base.is_absolute() else self._backup_dir / base
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate

    def _render_output_basename(
        self,
        template: Optional[str],
        *,
        task: Task,
        job: Job,
        execution: Execution,
        time_window: dict,
        offset_days: int,
        fallback: str,
        reference_dt: Optional[datetime] = None,
    ) -> str:
        pattern = (template or fallback or "report").strip()
        start_dt: datetime = time_window.get("start") or datetime.now(tz=self._tz).replace(tzinfo=None)
        end_dt: datetime = time_window.get("end") or start_dt
        anchor = reference_dt or start_dt
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=self._tz)
        target_dt = anchor + timedelta(days=offset_days)
        week_start_label = self._format_week_label(start_dt)
        end_reference = end_dt - timedelta(seconds=1) if end_dt > start_dt else end_dt
        week_end_label = self._format_week_label(end_reference)
        replacements = {
            "{YYYY-MM-DD HH:MM}": target_dt.strftime("%Y-%m-%d %H:%M"),
            "{YYYY-MM-DD}": target_dt.strftime("%Y-%m-%d"),
            "{YYYYMMDD_HHmmss}": target_dt.strftime("%Y%m%d_%H%M%S"),
            "{YYYYMMDD}": target_dt.strftime("%Y%m%d"),
            "{task_name}": task.name or "",
            "{job_name}": job.name or "",
            "{job_id}": str(job.id or ""),
            "{task_id}": str(task.id or ""),
            "{execution_id}": str(execution.id or ""),
            "{week_start}": week_start_label,
            "{week_end}": week_end_label,
        }
        filename = pattern
        for placeholder, value in replacements.items():
            filename = filename.replace(placeholder, value)
        return _sanitize_filename(filename) or fallback

    def _get_offset_reference_datetime(self, execution: Execution, time_window: Optional[dict]) -> datetime:
        candidates: List[Optional[datetime]] = [
            getattr(execution, "finished_at", None),
            getattr(execution, "started_at", None),
        ]
        if time_window:
            candidates.extend([time_window.get("end"), time_window.get("start")])
        for dt in candidates:
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=self._tz)
                return dt
        return datetime.now(tz=self._tz)

    def _format_time_range_label(self, time_window: dict) -> str:
        start = time_window.get("start")
        end = time_window.get("end")
        if isinstance(start, datetime) and isinstance(end, datetime):
            return f"{start.strftime('%Y-%m-%d %H:%M')} 到 {end.strftime('%Y-%m-%d %H:%M')}"
        return time_window.get("time_str") or ""

    def _ensure_unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        timestamp = datetime.now(tz=self._tz).strftime("%Y%m%d_%H%M%S")
        stem = path.stem
        suffix = path.suffix
        counter = 1
        candidate = path.with_name(f"{stem}_{timestamp}{suffix}")
        while candidate.exists():
            counter += 1
            candidate = path.with_name(f"{stem}_{timestamp}_{counter}{suffix}")
        return candidate

    @staticmethod
    def _format_week_label(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d")

    def _format_window_labels(self, time_window: dict | None) -> tuple[str, Optional[str]]:
        def sanitize(label: str) -> str:
            return label.replace(":", "-")

        if not time_window:
            return sanitize("unknown"), None

        start = time_window.get("start")
        end = time_window.get("end")
        if isinstance(start, datetime):
            start_label = sanitize(start.strftime("%Y-%m-%d %H-%M"))
        else:
            start_label = None
        if isinstance(end, datetime):
            end_label = sanitize(end.strftime("%Y-%m-%d %H-%M"))
        else:
            end_label = None

        if not start_label or not end_label:
            time_str = time_window.get("time_str", "")
            if "~" in time_str:
                start_raw, end_raw = [part.strip() for part in time_str.split("~", 1)]
                start_label = start_label or sanitize(start_raw)
                end_label = end_label or sanitize(end_raw)
            else:
                start_label = start_label or sanitize(time_str or "unknown")

        return start_label or "unknown", end_label

    async def _deploy_html_to_github(
        self,
        job: Job,
        execution: Execution,
        *,
        html_content: str,
        plan: HtmlArtifactPlan,
    ) -> GithubUploadArtifact:
        config = job.github_config
        if not config:
            raise RuntimeError("GitHub 配置缺失")
        token = decrypt_value(config.token_cipher)
        branch = (config.branch or "main").strip() or "main"
        filename = plan.filename if _is_weekly_report(job) else self._compose_html_report_archive_path(plan)
        relative_path = self._compose_content_path(config.path_prefix, filename)
        repo_full_name = f"{config.owner}/{config.repo}"
        pages_url = self._build_pages_url(config, relative_path)
        github_file_url = self._build_github_file_url(config, branch, relative_path)
        commit_message = f"feat: deploy job {job.id} execution {execution.id}"
        await github.upload_html_file(
            token=token,
            owner=config.owner,
            repo=config.repo,
            branch=branch,
            path=relative_path,
            content=html_content,
            commit_message=commit_message,
        )
        return GithubUploadArtifact(
            repo_path=relative_path,
            repo_full_name=repo_full_name,
            branch=branch,
            github_file_url=github_file_url,
            pages_url=pages_url,
        )

    @staticmethod
    def _compose_html_report_archive_path(plan: HtmlArtifactPlan) -> str:
        target_date = plan.target_date
        return f"{target_date.year}年/{target_date.year}年{target_date.month}月/{plan.filename}"

    @staticmethod
    def _compose_content_path(prefix: Optional[str], filename: str) -> str:
        normalized = (prefix or "").strip().strip("/ ")
        if normalized:
            return f"{normalized}/{filename}"
        return filename

    @staticmethod
    def _build_pages_url(config, relative_path: str) -> str:
        base = (config.pages_base_url or f"https://{config.owner}.github.io/{config.repo}/").strip()
        if not base.endswith("/"):
            base += "/"
        return f"{base}{relative_path}"

    @staticmethod
    def _build_github_file_url(config, branch: str, relative_path: str) -> str:
        encoded_branch = quote(branch.strip(), safe="")
        encoded_path = quote(relative_path.strip("/"), safe="/")
        return f"https://github.com/{config.owner}/{config.repo}/blob/{encoded_branch}/{encoded_path}"

    def _calculate_next_run(self, job: Job) -> Optional[datetime]:
        sched_job = self.scheduler.get_job(f"job-{job.id}")
        return sched_job.next_run_time if sched_job else None

def _time_str_to_minutes(value: str) -> int:
    try:
        hour_str, minute_str = value.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
    except (ValueError, AttributeError):
        raise ValueError(f"invalid time format: {value}") from None
    if hour == 24 and minute == 0:
        return 24 * 60
    if 0 <= hour < 24 and 0 <= minute < 60:
        return hour * 60 + minute
    raise ValueError(f"invalid time value: {value}")


def _combine_date_minutes(base_date: date, minutes: int, tz: ZoneInfo) -> datetime:
    anchor = datetime(base_date.year, base_date.month, base_date.day, tzinfo=tz)
    return anchor + timedelta(minutes=minutes)


def _load_weekdays(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    result: List[int] = []
    for item in value:
        try:
            val = int(item)
        except (TypeError, ValueError):
            continue
        result.append(val)
    return result


def _parse_int_list(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [int(item) for item in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _parse_str_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(item) for item in data]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _is_weekly_report(job: Job) -> bool:
    return getattr(job, "schedule_type", "") == "weekly_report"


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "report.html"


def _strip_markdown_fence(content: str) -> str:
    if not content:
        return content
    trimmed = content.strip()
    if not trimmed.startswith("```"):
        return content
    lines = trimmed.splitlines()
    if len(lines) < 2:
        return trimmed
    closing_idx = len(lines) - 1
    while closing_idx > 0 and not lines[closing_idx].strip():
        closing_idx -= 1
    if not lines[0].strip().startswith("```") or not lines[closing_idx].strip().startswith("```"):
        return trimmed
    inner = "\n".join(lines[1:closing_idx]).strip()
    return inner or trimmed


def _parse_llm_chunk(chunk: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> tuple[str, Optional[int], Optional[int]]:
    try:
        data = json.loads(chunk)
    except json.JSONDecodeError:
        return chunk, prompt_tokens, completion_tokens

    text = ""
    if "choices" in data and data["choices"]:
        delta = data["choices"][0].get("delta", {})
        text = delta.get("content", "")
        usage = data.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
            completion_tokens = usage.get("completion_tokens", completion_tokens)
    return text, prompt_tokens, completion_tokens

scheduler_service = SchedulerService()
