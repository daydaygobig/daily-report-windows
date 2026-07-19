"""Shared helpers for windowed interval scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, List, Optional
from zoneinfo import ZoneInfo


@dataclass
class IntervalWindowPlan:
    fire_time: datetime
    window_start: datetime
    window_end: datetime


def combine_date_minutes(target_day: date, total_minutes: int, tz: ZoneInfo) -> datetime:
    if total_minutes >= 24 * 60:
        extra_days, minute_of_day = divmod(total_minutes, 24 * 60)
        dt = datetime(target_day.year, target_day.month, target_day.day, tzinfo=tz)
        return dt + timedelta(days=extra_days, minutes=minute_of_day)
    hour, minute = divmod(total_minutes, 60)
    return datetime(target_day.year, target_day.month, target_day.day, hour, minute, tzinfo=tz)


def build_daily_interval_plans(
    *,
    day: date,
    interval_minutes: int,
    window_start_minutes: int,
    window_end_minutes: int,
    tz: ZoneInfo,
    first_fire_minutes: Optional[int] = None,
) -> List[IntervalWindowPlan]:
    if interval_minutes <= 0 or window_end_minutes <= window_start_minutes:
        return []

    range_start = combine_date_minutes(day, window_start_minutes, tz)
    range_end = combine_date_minutes(day, window_end_minutes, tz)
    default_first = min(range_end, range_start + timedelta(minutes=interval_minutes))

    first_fire = default_first
    if first_fire_minutes is not None:
        requested_dt = combine_date_minutes(day, first_fire_minutes, tz)
        first_fire = max(range_start, requested_dt, default_first)
        if first_fire > range_end:
            first_fire = range_end
        if first_fire <= range_start:
            first_fire = range_start + timedelta(minutes=interval_minutes)
        if first_fire > range_end:
            first_fire = range_end

    interval_delta = timedelta(minutes=interval_minutes)
    plans: List[IntervalWindowPlan] = []
    prev_start = range_start
    current_fire = first_fire
    while current_fire <= range_end:
        window_start = max(prev_start, current_fire - interval_delta)
        plan = IntervalWindowPlan(
            fire_time=current_fire,
            window_start=window_start,
            window_end=current_fire,
        )
        plans.append(plan)
        if current_fire >= range_end:
            break
        next_fire = current_fire + interval_delta
        if next_fire > range_end:
            next_fire = range_end
        prev_start = plan.window_end
        current_fire = next_fire
    return plans


def compute_next_interval_plan(
    *,
    search_start: datetime,
    interval_minutes: int,
    window_start_minutes: int,
    window_end_minutes: int,
    tz: ZoneInfo,
    date_allowed: Callable[[date], bool],
    first_fire_minutes: Optional[int] = None,
    max_days: int = 60,
) -> Optional[IntervalWindowPlan]:
    if interval_minutes <= 0:
        return None
    for offset in range(max_days):
        current_date = search_start.date() + timedelta(days=offset)
        if not date_allowed(current_date):
            continue
        plans = build_daily_interval_plans(
            day=current_date,
            interval_minutes=interval_minutes,
            window_start_minutes=window_start_minutes,
            window_end_minutes=window_end_minutes,
            tz=tz,
            first_fire_minutes=first_fire_minutes,
        )
        for plan in plans:
            if plan.fire_time > search_start:
                return plan
    return None
