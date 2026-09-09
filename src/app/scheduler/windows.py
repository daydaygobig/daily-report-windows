"""执行时间窗口计算（拆分自 scheduler/service.py，内容不变）。"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from loguru import logger

from ..models.job import Job
from ..utils.interval_schedule import build_daily_interval_plans as build_shared_interval_plans
from ..utils.interval_schedule import compute_next_interval_plan as compute_shared_interval_plan

from .parsing import (
    _combine_date_minutes,
    _load_weekdays,
    _time_str_to_minutes,
)
from .types import (
    IntervalPlan,
)

class WindowMixin:
    """fixed/manual/weekly/自定义与相对时间窗口计算。"""

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
            logger.warning("作业 {} 使用自定义 Cron，跳过按间隔执行", job.id)
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
            logger.warning("Job {} time_range parse failed: {}", job.id, time_range)
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
            logger.warning("Invalid time range {} <= {}", end_dt, start_dt)
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

