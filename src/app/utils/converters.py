"""Helper functions to convert ORM entities into API-friendly structures."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..models.job import Job
from ..models.task import Task
from ..schemas.job import JobOut


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
    """以 JobOut schema 为唯一字段清单序列化 Job，仅追加 API 展示扩展字段。

    字段事实来源收敛为 models/job.py（表结构）与 schemas/job.py（API 契约）两处，
    本函数不再维护第三份字段清单。
    """
    data = JobOut.model_validate(job).model_dump()
    data["github_config"] = (
        {"id": job.github_config.id, "name": job.github_config.name} if job.github_config else None
    )
    stats_config = getattr(job, "message_stats_github_config", None)
    data["message_stats_github_config"] = (
        {"id": stats_config.id, "name": stats_config.name} if stats_config else None
    )
    # chatlog 备份三态回落：job 未显式配置（NULL）时沿用 task.store_chatlog
    raw_chatlog_enabled = getattr(job, "chatlog_backup_enabled", None)
    task_store_chatlog = bool(getattr(job, "task", None) and getattr(job.task, "store_chatlog", False))
    chatlog_backup_enabled = raw_chatlog_enabled if raw_chatlog_enabled is not None else task_store_chatlog
    data["chatlog_backup_enabled"] = chatlog_backup_enabled
    if data.get("chatlog_backup_formats") is None and chatlog_backup_enabled:
        data["chatlog_backup_formats"] = ["txt"]
    return data


def _load_json(raw: str | None, default):
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default
