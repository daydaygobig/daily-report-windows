"""APScheduler 装配、作业注册与触发器构建（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from ..db import session_scope
from ..models.disk_monitor import DiskInspectionJob
from ..models.job import Job
from ..services import disk_monitor_service

from .common import (
    job_repo,
)
from .parsing import (
    _parse_int_list,
    _time_str_to_minutes,
)

class SchedulingMixin:
    """调度器生命周期与作业编排。"""

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
            logger.exception("执行磁盘巡检任务失败 inspection_job_id={}", inspection_job_id)
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
            logger.exception("执行 IMA 同步作业失败 sync_job_id={}", sync_job_id)

    def _schedule_job(self, job: Job) -> Optional[datetime]:
        existing = self.scheduler.get_job(f"job-{job.id}")
        if existing:
            existing.remove()
        if not job.is_enabled or not self._is_within_active_range(job):
            logger.info("Job {} ({}) is outside active range or disabled", job.id, job.name)
            job.next_run_at = None
            return None

        if job.interval_enabled:
            plan = self._compute_next_interval_plan(job)
            if not plan:
                logger.info("Job {} has no available interval execution plan", job.id)
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
            logger.info("Scheduled interval job {} next run at {}", job.id, next_local)
            return next_local

        trigger = self._build_trigger(job)
        if not trigger:
            logger.warning("Job {} has invalid schedule", job.id)
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
        logger.info("Scheduled job {} ({}) execution_time={}", job.id, job.name, execution_time_str)
        next_run = aps_job.next_run_time
        if next_run:
            next_local = next_run.astimezone(self._tz).replace(tzinfo=None)
            job.next_run_at = next_local
            logger.info("Job {} next run at {} (local time)", job.id, next_local)
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


    def _calculate_next_run(self, job: Job) -> Optional[datetime]:
        sched_job = self.scheduler.get_job(f"job-{job.id}")
        return sched_job.next_run_time if sched_job else None
