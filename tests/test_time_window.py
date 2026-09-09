"""时间窗口计算家族的特征测试：锁住 fixed/跨天/previous_day/manual/weekly/自定义区间的现有行为。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.models.job import Job
from app.scheduler.service import SchedulerService

service = SchedulerService()
TZ = service._tz


def make_job(**kw) -> Job:
    """构造不入库的瞬时 Job 对象（窗口计算只读属性，不访问数据库）。"""
    defaults = dict(
        task_id=1,
        name="窗口作业",
        start_time="08:00",
        end_time="22:00",
        date_baseline="current_day",
        schedule_type="daily",
    )
    defaults.update(kw)
    return Job(**defaults)


def test_fixed_window_same_day():
    window = service._calculate_time_window(make_job())
    assert "~" in window["time_str"]
    start, end = window["start"], window["end"]
    assert (start.hour, start.minute) == (8, 0)
    assert (end.hour, end.minute) == (22, 0)
    assert start.date() == end.date()


def test_fixed_window_crosses_midnight_uses_previous_day_start():
    window = service._calculate_time_window(make_job(start_time="22:00", end_time="06:00"))
    start, end = window["start"], window["end"]
    assert end - start == timedelta(hours=8)
    assert start.date() == end.date() - timedelta(days=1)


def test_fixed_window_previous_day_baseline():
    # 现有行为：previous_day 只把窗口起点移到昨天，终点仍落在今天 23:59
    job = make_job(start_time="00:00", end_time="23:59", date_baseline="previous_day")
    window = service._calculate_time_window(job)
    today = datetime.now(TZ).date()
    assert window["start"].date() == today - timedelta(days=1)
    assert window["end"].date() == today


def test_previous_day_baseline_cross_midnight_extends_end():
    job = make_job(start_time="22:00", end_time="06:00", date_baseline="previous_day")
    window = service._calculate_time_window(job)
    start, end = window["start"], window["end"]
    assert start.date() == end.date() - timedelta(days=1)
    assert end - start == timedelta(hours=8)


def test_manual_fixed_window_walks_back_until_past():
    # 手动补算窗口仅在执行时间 >= 24:00 时触发（如"当天结束"类作业），
    # 从今天往回找第一个 end 已过去的窗口
    job = make_job(
        start_time="00:00",
        end_time="23:00",
        execution_time="24:00",
        schedule_type="manual",
    )
    window = service._calculate_time_window(job, is_manual=True)
    now = datetime.now(TZ)
    start, end = window["start"], window["end"]
    assert end <= now
    assert end - start == timedelta(hours=23)
    assert start.date() == end.date()


def test_offset_minutes_shifts_window():
    window = service._calculate_time_window(make_job(offset_minutes=30))
    assert (window["start"].hour, window["start"].minute) == (8, 30)
    assert (window["end"].hour, window["end"].minute) == (22, 30)


def test_custom_time_range_in_description():
    job = make_job(description="手动补发 2026-09-01 08:00~2026-09-01 12:00")
    window = service._calculate_time_window(job)
    assert window["time_str"] == "2026-09-01 08:00~2026-09-01 12:00"
    assert (window["start"].hour, window["start"].minute) == (8, 0)


def test_relative_window_from_description_json():
    config = {"relative_window": {"end_offset_minutes": -30, "duration_minutes": 60}}
    job = make_job(description=json.dumps(config, ensure_ascii=False))
    window = service._calculate_time_window(job)
    start, end = window["start"], window["end"]
    assert end - start == timedelta(minutes=60)
    now = datetime.now()
    assert abs((now - end).total_seconds() - 30 * 60) < 120


def test_weekly_report_window_covers_previous_week():
    job = make_job(
        schedule_type="weekly_report",
        weekly_period="previous_week",
        weekly_start_day=0,
        weekly_end_day=6,
        weekly_start_time="00:00",
        weekly_end_time="24:00",
    )
    window = service._calculate_time_window(job)
    start, end = window["start"], window["end"]
    assert end - start == timedelta(days=7)
    assert start.weekday() == 0
    assert start.date() < datetime.now(TZ).date()


def test_active_range_parsing():
    in_range = make_job(description=json.dumps({"active_range": "2000-01-01~2099-12-31"}))
    out_range = make_job(description=json.dumps({"active_range": "2020-01-01~2020-12-31"}))
    no_range = make_job(description="普通文字描述")
    assert service._is_within_active_range(in_range) is True
    assert service._is_within_active_range(out_range) is False
    assert service._is_within_active_range(no_range) is True


def test_misfire_window_from_retry_config():
    job = make_job(max_retry=3, retry_interval_sec=60)
    assert service._calculate_misfire_window(job) == 240
    zero_retry = make_job(max_retry=0, retry_interval_sec=100)
    assert service._calculate_misfire_window(zero_retry) == 300
