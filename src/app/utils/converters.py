"""Helper functions to convert ORM entities into API-friendly structures."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..models.job import Job
from ..models.task import Task


def serialize_weekdays(weekdays: Optional[List[int]]) -> Optional[str]:
    if weekdays is None:
        return None
    return json.dumps(weekdays)


def serialize_list(values: Optional[List[int | str]]) -> Optional[str]:
    if values is None:
        return None
    return json.dumps(values)


def task_to_dict(task: Task) -> Dict[str, Any]:
    model_sequence = _load_json(getattr(task, "model_sequence", None), default=[])
    if not model_sequence and getattr(task, "model_id", None):
        model_sequence = [{"model_id": task.model_id, "max_attempts": 2}]
    image_model_sequence = _load_json(getattr(task, "image_model_sequence", None), default=[])
    if not image_model_sequence and getattr(task, "image_model_id", None):
        image_model_sequence = [{"model_id": task.image_model_id, "max_attempts": 2}]
    return {
        "id": task.id,
        "name": task.name,
        "task_type": getattr(task, "task_type", "report") or "report",
        "prompt": task.prompt,
        "model_id": task.model_id,
        "image_model_id": getattr(task, "image_model_id", None),
        "upstream_task_id": getattr(task, "upstream_task_id", None),
        "card_input_source": getattr(task, "card_input_source", None) or "chatlog",
        "image_model_sequence": image_model_sequence,
        "model_sequence": model_sequence,
        "prompt_template_id": getattr(task, "prompt_template_id", None),
        "talkers": _load_json(task.talkers, default=[]),
        "talker_names": _load_json(task.talker_names, default=[]),
        "push_webhook_ids": _load_json(task.push_webhook_ids, default=[]),
        "alert_webhook_ids": _load_json(task.alert_webhook_ids, default=None),
        "is_active": task.is_active,
        "store_local_results": bool(task.store_local_results),
        "store_chatlog": bool(getattr(task, "store_chatlog", False)),
        "system_prompt_custom_enabled": bool(getattr(task, "system_prompt_custom_enabled", False)),
        "system_prompt_template": getattr(task, "system_prompt_template", None),
        "system_prompt_include_message_count": bool(getattr(task, "system_prompt_include_message_count", False)),
        "topic_style_config": _load_json(getattr(task, "topic_style_config", None), default={}),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def job_to_dict(job: Job) -> Dict[str, Any]:
    task_store_chatlog = bool(getattr(job, "task", None) and getattr(job.task, "store_chatlog", False))
    raw_chatlog_enabled = getattr(job, "chatlog_backup_enabled", None)
    chatlog_backup_enabled = raw_chatlog_enabled if raw_chatlog_enabled is not None else task_store_chatlog
    chatlog_backup_formats = _load_json(getattr(job, "chatlog_backup_formats", None), default=None)
    if chatlog_backup_formats is None and chatlog_backup_enabled:
        chatlog_backup_formats = ["txt"]
    return {
        "id": job.id,
        "task_id": job.task_id,
        "name": job.name,
        "start_time": job.start_time,
        "end_time": job.end_time,
        "date_baseline": job.date_baseline,
        "schedule_type": job.schedule_type,
        "cron_expression": job.cron_expression,
        "weekdays": _load_json(job.weekdays, default=None),
        "execution_time": job.execution_time,
        "offset_minutes": job.offset_minutes,
        "interval_enabled": bool(getattr(job, "interval_enabled", False)),
        "interval_minutes": job.interval_minutes,
        "window_start": job.window_start,
        "window_end": job.window_end,
        "disk_alert_enabled": bool(getattr(job, "disk_alert_enabled", False)),
        "disk_alert_threshold_bytes": getattr(job, "disk_alert_threshold_bytes", 100 * 1024 * 1024),
        "max_retry": job.max_retry,
        "retry_interval_sec": job.retry_interval_sec,
        "is_enabled": job.is_enabled,
        "description": job.description,
        "last_run_at": job.last_run_at,
        "next_run_at": job.next_run_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "github_deploy_enabled": bool(getattr(job, "github_deploy_enabled", False)),
        "github_config_id": job.github_config_id,
        "github_config": {
            "id": job.github_config.id,
            "name": job.github_config.name,
        }
        if job.github_config
        else None,
        "html_backup_enabled": bool(getattr(job, "html_backup_enabled", False)),
        "html_backup_path": getattr(job, "html_backup_path", None),
        "html_backup_filename_template": getattr(job, "html_backup_filename_template", None),
        "html_backup_filename_date_offset_days": getattr(job, "html_backup_filename_date_offset_days", 0),
        "github_filename_template": getattr(job, "github_filename_template", None),
        "days_offset": getattr(job, "days_offset", 0),
        "display_order": getattr(job, "display_order", 0),
        "message_stats_enabled": bool(getattr(job, "message_stats_enabled", False)),
        "message_stats_formats": _load_json(getattr(job, "message_stats_formats", None), default=None),
        "message_stats_path": getattr(job, "message_stats_path", None),
        "message_stats_filename_template": getattr(job, "message_stats_filename_template", None),
        "message_stats_filename_date_offset_days": getattr(job, "message_stats_filename_date_offset_days", 0),
        "message_stats_github_enabled": bool(getattr(job, "message_stats_github_enabled", False)),
        "message_stats_github_config_id": getattr(job, "message_stats_github_config_id", None),
        "message_stats_github_config": {
            "id": job.message_stats_github_config.id,
            "name": job.message_stats_github_config.name,
        }
        if getattr(job, "message_stats_github_config", None)
        else None,
        "message_stats_github_filename_template": getattr(job, "message_stats_github_filename_template", None),
        "message_stats_github_filename_date_offset_days": getattr(job, "message_stats_github_filename_date_offset_days", 0),
        "message_stats_github_root": getattr(job, "message_stats_github_root", None),
        "chatlog_backup_enabled": chatlog_backup_enabled,
        "chatlog_backup_formats": chatlog_backup_formats,
        "chatlog_backup_path": getattr(job, "chatlog_backup_path", None),
        "chatlog_backup_filename_template": getattr(job, "chatlog_backup_filename_template", None),
        "chatlog_backup_filename_date_offset_days": getattr(job, "chatlog_backup_filename_date_offset_days", 0),
        "model_output_backup_enabled": bool(getattr(job, "model_output_backup_enabled", False)),
        "model_output_path": getattr(job, "model_output_path", None),
        "model_output_formats": _load_json(getattr(job, "model_output_formats", None), default=None),
        "model_output_filename_template": getattr(job, "model_output_filename_template", None),
        "model_output_filename_date_offset_days": getattr(job, "model_output_filename_date_offset_days", 0),
        "ima_sync_enabled": bool(getattr(job, "ima_sync_enabled", False)),
        "ima_use_default_account": bool(getattr(job, "ima_use_default_account", True)),
        "ima_account_id": getattr(job, "ima_account_id", None),
        "ima_account_name": getattr(getattr(job, "ima_account", None), "name", None),
        "ima_use_default_target": bool(getattr(job, "ima_use_default_target", True)),
        "ima_target_type": getattr(job, "ima_target_type", None),
        "ima_note_folder_id": getattr(job, "ima_note_folder_id", None),
        "ima_note_folder_name": getattr(job, "ima_note_folder_name", None),
        "ima_knowledge_base_id": getattr(job, "ima_knowledge_base_id", None),
        "ima_knowledge_base_name": getattr(job, "ima_knowledge_base_name", None),
        "ima_knowledge_folder_id": getattr(job, "ima_knowledge_folder_id", None),
        "ima_knowledge_folder_name": getattr(job, "ima_knowledge_folder_name", None),
        "weekly_period": getattr(job, "weekly_period", None),
        "weekly_start_day": getattr(job, "weekly_start_day", None),
        "weekly_start_time": getattr(job, "weekly_start_time", None),
        "weekly_end_day": getattr(job, "weekly_end_day", None),
        "weekly_end_time": getattr(job, "weekly_end_time", None),
        "topic_text_layout": getattr(job, "topic_text_layout", "per_topic") or "per_topic",
        "topic_text_merge_threshold": getattr(job, "topic_text_merge_threshold", 3) or 3,
        "topic_image_enabled": bool(getattr(job, "topic_image_enabled", False)),
        "topic_image_layout": getattr(job, "topic_image_layout", "single") or "single",
        "topic_image_merge_threshold": getattr(job, "topic_image_merge_threshold", 3) or 3,
        "topic_image_backup_enabled": bool(getattr(job, "topic_image_backup_enabled", False)),
        "topic_image_backup_path": getattr(job, "topic_image_backup_path", None),
        "image_prompt_template_id": getattr(job, "image_prompt_template_id", None),
        "image_prompt": getattr(job, "image_prompt", None),
        "image_split_enabled": bool(getattr(job, "image_split_enabled", False)),
        "image_split_prompt": getattr(job, "image_split_prompt", None),
        "image_aspect_ratio": getattr(job, "image_aspect_ratio", "auto") or "auto",
        "image_resolution": getattr(job, "image_resolution", "auto") or "auto",
        "max_image_count": getattr(job, "max_image_count", 6) or 6,
    }


def _load_json(raw: str | None, default):
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
