"""Pydantic schemas for Job entity."""

import json
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .base import ORMBase

TopicTextLayout = Literal["per_topic", "merged", "auto"]
TopicImageLayout = Literal["single", "collection", "auto"]
ImageAspectRatio = Literal["auto", "1:1", "3:2", "2:3", "9:16", "1:3"]
ImageResolution = Literal["auto", "1k", "2k", "4k"]


class JobBase(BaseModel):
    name: str = Field(..., max_length=120)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    execution_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    date_baseline: Literal["current_day", "previous_day"] = "current_day"
    schedule_type: str = Field(..., max_length=50)
    cron_expression: Optional[str] = None
    weekdays: Optional[List[int]] = None
    offset_minutes: int = Field(default=0, ge=0, le=1440)
    interval_enabled: bool = False
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    window_start: str = Field(default="00:00", pattern=r"^\d{2}:\d{2}$")
    window_end: str = Field(default="24:00", pattern=r"^\d{2}:\d{2}$")
    disk_alert_enabled: bool = False
    disk_alert_threshold_bytes: int = Field(default=104857600, ge=1)
    max_retry: int = Field(default=1, ge=0, le=10)
    retry_interval_sec: int = Field(default=300, ge=60)
    is_enabled: bool = True
    description: Optional[str] = None
    github_deploy_enabled: bool = False
    github_config_id: Optional[int] = Field(default=None, ge=1)
    github_filename_template: Optional[str] = None
    html_backup_enabled: bool = False
    html_backup_path: Optional[str] = None
    html_backup_filename_template: Optional[str] = None
    html_backup_filename_date_offset_days: int = Field(default=0, ge=-7, le=7)
    days_offset: int = 0
    message_stats_enabled: bool = False
    message_stats_formats: Optional[List[str]] = Field(default_factory=lambda: ["md"])
    message_stats_path: Optional[str] = "backups/message_reports"
    message_stats_filename_template: Optional[str] = "每日群成员发言数量统计_{YYYY-MM-DD}"
    message_stats_filename_date_offset_days: int = Field(default=-1, ge=-7, le=7)
    message_stats_github_enabled: bool = False
    message_stats_github_config_id: Optional[int] = Field(default=None, ge=1)
    message_stats_github_filename_template: Optional[str] = "每日群成员发言数量统计_{YYYY-MM-DD}"
    message_stats_github_filename_date_offset_days: int = Field(default=0, ge=-7, le=7)
    message_stats_github_root: Optional[str] = "xinjian"
    chatlog_backup_enabled: Optional[bool] = False
    chatlog_backup_formats: Optional[List[Literal["md", "txt"]]] = Field(default_factory=lambda: ["txt"])
    chatlog_backup_path: Optional[str] = "backups/chatlogs"
    chatlog_backup_filename_template: Optional[str] = "聊天记录_{week_start}_{week_end}"
    chatlog_backup_filename_date_offset_days: int = Field(default=0, ge=-7, le=7)
    model_output_backup_enabled: bool = False
    model_output_path: Optional[str] = "backups/model_outputs"
    model_output_formats: Optional[List[Literal["md", "txt"]]] = Field(default_factory=lambda: ["md"])
    model_output_filename_template: Optional[str] = "模型输出_{YYYY-MM-DD}"
    model_output_filename_date_offset_days: int = Field(default=-1, ge=-7, le=7)
    ima_sync_enabled: bool = False
    ima_use_default_account: bool = True
    ima_account_id: Optional[int] = Field(default=None, ge=1)
    ima_use_default_target: bool = True
    ima_target_type: Optional[Literal["note", "knowledge_base"]] = None
    ima_note_folder_id: Optional[str] = None
    ima_note_folder_name: Optional[str] = None
    ima_knowledge_base_id: Optional[str] = None
    ima_knowledge_base_name: Optional[str] = None
    ima_knowledge_folder_id: Optional[str] = None
    ima_knowledge_folder_name: Optional[str] = None
    weekly_period: Optional[Literal["current_week", "previous_week"]] = "previous_week"
    weekly_start_day: Optional[int] = Field(default=0, ge=0, le=6)
    weekly_start_time: Optional[str] = Field(default="00:00", pattern=r"^\d{2}:\d{2}$")
    weekly_end_day: Optional[int] = Field(default=6, ge=0, le=6)
    weekly_end_time: Optional[str] = Field(default="24:00", pattern=r"^\d{2}:\d{2}$")
    topic_text_layout: TopicTextLayout = "per_topic"
    topic_text_merge_threshold: int = Field(default=3, ge=1, le=20)
    topic_image_enabled: bool = False
    topic_image_layout: TopicImageLayout = "single"
    topic_image_merge_threshold: int = Field(default=3, ge=1, le=20)
    topic_image_backup_enabled: bool = False
    topic_image_backup_path: Optional[str] = None
    image_prompt_template_id: Optional[int] = Field(default=None, ge=1)
    image_split_enabled: bool = True
    image_split_prompt: Optional[str] = None
    image_aspect_ratio: ImageAspectRatio = "auto"
    image_resolution: ImageResolution = "auto"
    max_image_count: int = Field(default=6, ge=1, le=20)

    @model_validator(mode="after")
    def validate_job(cls, values: "JobBase"):
        window_start = values.window_start
        window_end = values.window_end
        if window_start and window_end and _time_to_minutes(window_end) <= _time_to_minutes(window_start):
            raise ValueError("生效范围的结束时间必须晚于开始时间")
        if values.interval_enabled:
            if values.schedule_type == "weekly_report":
                raise ValueError("周报模式不支持按间隔执行")
            if values.schedule_type == "custom_cron":
                raise ValueError("自定义 Cron 不支持按间隔执行")
            if values.schedule_type == "manual":
                raise ValueError("手动执行不支持按间隔执行")
            if not values.interval_minutes or values.interval_minutes <= 0:
                raise ValueError("按间隔执行需要设置间隔频率（分钟）")
        if values.disk_alert_enabled and values.disk_alert_threshold_bytes <= 0:
            raise ValueError("磁盘写入告警阈值必须大于 0")
        if values.github_deploy_enabled and not values.github_config_id:
            raise ValueError("启用 GitHub 部署时需选择配置")
        if values.message_stats_enabled:
            formats = values.message_stats_formats or []
            if not formats:
                raise ValueError("至少选择一种群消息统计导出格式")
        if values.message_stats_github_enabled:
            if not values.message_stats_enabled:
                raise ValueError("开启群消息统计同步前需先启用导出群消息统计")
            if not values.message_stats_github_config_id:
                raise ValueError("启用群消息统计同步时需选择 GitHub 配置")
        if values.model_output_backup_enabled:
            formats = values.model_output_formats or []
            if not formats:
                raise ValueError("至少选择一种模型输出备份格式")
        if values.ima_sync_enabled and not values.model_output_backup_enabled:
            raise ValueError("启用 ima 同步前需先开启备份模型返回结果")
        if values.ima_sync_enabled and not values.ima_use_default_account and not values.ima_account_id:
            raise ValueError("请选择 ima 账号")
        if values.ima_sync_enabled and not values.ima_use_default_target:
            if values.ima_target_type == "note" and not values.ima_note_folder_id:
                raise ValueError("请选择 ima 笔记本")
            if values.ima_target_type == "knowledge_base" and not values.ima_knowledge_base_id:
                raise ValueError("请选择 ima 知识库")
        if values.schedule_type == "weekly_report":
            weekdays = values.weekdays or []
            if len(weekdays) != 1:
                raise ValueError("周报模式仅支持选择一个执行日")
            if values.weekly_start_day is None or values.weekly_end_day is None:
                raise ValueError("请配置周报时间窗口的起止日期")
            if values.weekly_start_time is None or values.weekly_end_time is None:
                raise ValueError("请配置周报时间窗口的起止时间")
        return values


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    execution_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    date_baseline: Optional[str] = Field(default=None)
    schedule_type: Optional[str] = Field(default=None, max_length=50)
    cron_expression: Optional[str] = None
    weekdays: Optional[List[int]] = None
    offset_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    interval_enabled: Optional[bool] = None
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    window_start: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    window_end: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    disk_alert_enabled: Optional[bool] = None
    disk_alert_threshold_bytes: Optional[int] = Field(default=None, ge=1)
    max_retry: Optional[int] = Field(default=None, ge=0, le=10)
    retry_interval_sec: Optional[int] = Field(default=None, ge=60)
    is_enabled: Optional[bool] = None
    description: Optional[str] = None
    github_deploy_enabled: Optional[bool] = None
    github_config_id: Optional[int] = Field(default=None, ge=1)
    html_backup_enabled: Optional[bool] = None
    html_backup_path: Optional[str] = None
    html_backup_filename_template: Optional[str] = None
    html_backup_filename_date_offset_days: Optional[int] = Field(default=None, ge=-7, le=7)
    github_filename_template: Optional[str] = None
    days_offset: Optional[int] = None
    message_stats_enabled: Optional[bool] = None
    message_stats_formats: Optional[List[str]] = None
    message_stats_path: Optional[str] = None
    message_stats_filename_template: Optional[str] = None
    message_stats_filename_date_offset_days: Optional[int] = Field(default=None, ge=-7, le=7)
    message_stats_github_enabled: Optional[bool] = None
    message_stats_github_config_id: Optional[int] = Field(default=None, ge=1)
    message_stats_github_filename_template: Optional[str] = None
    message_stats_github_filename_date_offset_days: Optional[int] = Field(default=None, ge=-7, le=7)
    message_stats_github_root: Optional[str] = None
    chatlog_backup_enabled: Optional[bool] = None
    chatlog_backup_formats: Optional[List[Literal["md", "txt"]]] = None
    chatlog_backup_path: Optional[str] = None
    chatlog_backup_filename_template: Optional[str] = None
    chatlog_backup_filename_date_offset_days: Optional[int] = Field(default=None, ge=-7, le=7)
    model_output_backup_enabled: Optional[bool] = None
    model_output_path: Optional[str] = None
    model_output_formats: Optional[List[Literal["md", "txt"]]] = None
    model_output_filename_template: Optional[str] = None
    model_output_filename_date_offset_days: Optional[int] = Field(default=None, ge=-7, le=7)
    ima_sync_enabled: Optional[bool] = None
    ima_use_default_account: Optional[bool] = None
    ima_account_id: Optional[int] = Field(default=None, ge=1)
    ima_use_default_target: Optional[bool] = None
    ima_target_type: Optional[Literal["note", "knowledge_base"]] = None
    ima_note_folder_id: Optional[str] = None
    ima_note_folder_name: Optional[str] = None
    ima_knowledge_base_id: Optional[str] = None
    ima_knowledge_base_name: Optional[str] = None
    ima_knowledge_folder_id: Optional[str] = None
    ima_knowledge_folder_name: Optional[str] = None
    weekly_period: Optional[Literal["current_week", "previous_week"]] = None
    weekly_start_day: Optional[int] = Field(default=None, ge=0, le=6)
    weekly_start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    weekly_end_day: Optional[int] = Field(default=None, ge=0, le=6)
    weekly_end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    topic_text_layout: Optional[TopicTextLayout] = None
    topic_text_merge_threshold: Optional[int] = Field(default=None, ge=1, le=20)
    topic_image_enabled: Optional[bool] = None
    topic_image_layout: Optional[TopicImageLayout] = None
    topic_image_merge_threshold: Optional[int] = Field(default=None, ge=1, le=20)
    topic_image_backup_enabled: Optional[bool] = None
    topic_image_backup_path: Optional[str] = None
    image_prompt_template_id: Optional[int] = Field(default=None, ge=1)
    image_split_enabled: Optional[bool] = None
    image_split_prompt: Optional[str] = None
    image_aspect_ratio: Optional[ImageAspectRatio] = None
    image_resolution: Optional[ImageResolution] = None
    max_image_count: Optional[int] = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def validate_job(cls, values: "JobUpdate"):
        window_start = values.window_start
        window_end = values.window_end
        if window_start and window_end and _time_to_minutes(window_end) <= _time_to_minutes(window_start):
            raise ValueError("生效范围的结束时间必须晚于开始时间")
        if values.interval_enabled:
            if values.schedule_type == "custom_cron":
                raise ValueError("自定义 Cron 不支持按间隔执行")
            if values.schedule_type == "weekly_report":
                raise ValueError("周报模式不支持按间隔执行")
            if values.schedule_type == "manual":
                raise ValueError("手动执行不支持按间隔执行")
        if values.interval_minutes is not None and values.interval_minutes <= 0:
            raise ValueError("间隔频率必须大于 0")
        if values.disk_alert_threshold_bytes is not None and values.disk_alert_threshold_bytes <= 0:
            raise ValueError("磁盘写入告警阈值必须大于 0")
        if values.message_stats_enabled and values.message_stats_formats is not None and not values.message_stats_formats:
            raise ValueError("至少选择一种群消息统计导出格式")
        if values.message_stats_github_enabled and values.message_stats_enabled is False:
            raise ValueError("开启群消息统计同步前需先启用导出群消息统计")
        if values.model_output_backup_enabled and values.model_output_formats is not None and not values.model_output_formats:
            raise ValueError("至少选择一种模型输出备份格式")
        if values.ima_sync_enabled and values.model_output_backup_enabled is False:
            raise ValueError("启用 ima 同步前需先开启备份模型返回结果")
        return values


def _load_json_list(value: Any) -> Any:
    """ORM 的 JSON 列表存为 TEXT；schema 直接从 ORM 校验时兼容字符串/列表两种输入。"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


class JobOut(ORMBase):
    task_id: int
    name: str
    start_time: str
    end_time: str
    execution_time: Optional[str]
    date_baseline: str
    schedule_type: str
    cron_expression: Optional[str]
    weekdays: Optional[List[int]]
    offset_minutes: int
    interval_enabled: bool
    interval_minutes: Optional[int]
    window_start: str
    window_end: str
    disk_alert_enabled: bool
    disk_alert_threshold_bytes: int
    max_retry: int
    retry_interval_sec: int
    is_enabled: bool
    description: Optional[str]
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    github_deploy_enabled: bool
    github_config_id: Optional[int]
    html_backup_enabled: bool
    html_backup_path: Optional[str]
    html_backup_filename_template: Optional[str]
    html_backup_filename_date_offset_days: int
    github_filename_template: Optional[str]
    days_offset: int
    display_order: int
    message_stats_enabled: bool
    message_stats_formats: Optional[List[str]]
    message_stats_path: Optional[str]
    message_stats_filename_template: Optional[str]
    message_stats_filename_date_offset_days: int
    message_stats_github_enabled: bool
    message_stats_github_config_id: Optional[int]
    message_stats_github_filename_template: Optional[str]
    message_stats_github_filename_date_offset_days: int
    message_stats_github_root: Optional[str]
    chatlog_backup_enabled: Optional[bool]  # ORM 存 NULL 时由读取侧按 task.store_chatlog 三态回落
    chatlog_backup_formats: Optional[List[str]]
    chatlog_backup_path: Optional[str]
    chatlog_backup_filename_template: Optional[str]
    chatlog_backup_filename_date_offset_days: int
    model_output_backup_enabled: bool
    model_output_path: Optional[str]
    model_output_formats: Optional[List[str]]
    model_output_filename_template: Optional[str]
    model_output_filename_date_offset_days: int
    ima_sync_enabled: bool
    ima_use_default_account: bool
    ima_account_id: Optional[int]
    ima_account_name: Optional[str]
    ima_use_default_target: bool
    ima_target_type: Optional[str]
    ima_note_folder_id: Optional[str]
    ima_note_folder_name: Optional[str]
    ima_knowledge_base_id: Optional[str]
    ima_knowledge_base_name: Optional[str]
    ima_knowledge_folder_id: Optional[str]
    ima_knowledge_folder_name: Optional[str]
    weekly_period: Optional[str]
    weekly_start_day: Optional[int]
    weekly_start_time: Optional[str]
    weekly_end_day: Optional[int]
    weekly_end_time: Optional[str]
    topic_text_layout: str
    topic_text_merge_threshold: int
    topic_image_enabled: bool
    topic_image_layout: str
    topic_image_merge_threshold: int
    topic_image_backup_enabled: bool
    topic_image_backup_path: Optional[str]
    image_prompt_template_id: Optional[int] = None
    image_prompt: Optional[str] = None
    image_split_enabled: bool = False
    image_split_prompt: Optional[str] = None
    image_aspect_ratio: ImageAspectRatio = "auto"
    image_resolution: ImageResolution = "auto"
    max_image_count: int = 6

    @field_validator(
        "weekdays",
        "message_stats_formats",
        "chatlog_backup_formats",
        "model_output_formats",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def _parse_json_text_columns(cls, value: Any) -> Any:
        return _load_json_list(value)


class JobReorderPayload(BaseModel):
    job_ids: List[int]


def _time_to_minutes(value: str) -> int:
    hour_str, minute_str = value.split(":")
    hour = int(hour_str)
    minute = int(minute_str)
    if hour == 24 and minute == 0:
        return 24 * 60
    if 0 <= hour < 24 and 0 <= minute < 60:
        return hour * 60 + minute
    raise ValueError("时间格式需为 HH:MM 且合法")
