"""Business logic for task and job management."""

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models.job import Job
from ..models.task import Task
from ..repositories.github_config_repo import GithubConfigRepository
from ..repositories.ima_account_repo import ImaAccountRepository
from ..repositories.job_repo import JobRepository
from ..repositories.model_repo import ModelRepository
from ..repositories.prompt_template_repo import PromptTemplateRepository
from ..repositories.task_repo import TaskRepository
from ..schemas.job import JobCreate, JobOut, JobUpdate
from ..schemas.task import TaskCreate, TaskOut, TaskUpdate
from ..utils.converters import job_to_dict, task_to_dict
from . import topic_card_service


task_repo = TaskRepository()
job_repo = JobRepository()
github_config_repo = GithubConfigRepository()
template_repo = PromptTemplateRepository()
ima_account_repo = ImaAccountRepository()
model_repo = ModelRepository()


def _sorted_jobs(task: Task) -> List[Job]:
    return sorted(task.jobs, key=lambda job: (getattr(job, "display_order", 0), job.id or 0))


def list_tasks(db: Session) -> List[TaskOut]:
    tasks = task_repo.list_all(db)
    result: List[TaskOut] = []
    for task in tasks:
        task_dict = task_to_dict(task)
        task_dict["topic_style_config"] = topic_card_service.normalize_topic_style_config(task_dict.get("topic_style_config"))
        jobs = _sorted_jobs(task)
        task_dict["jobs"] = [JobOut.model_validate(job_to_dict(job)) for job in jobs]
        result.append(TaskOut.model_validate(task_dict))
    return result


def create_task(db: Session, payload: TaskCreate) -> Task:
    data = payload.model_dump()
    data["topic_style_config"] = topic_card_service.normalize_topic_style_config(data.get("topic_style_config"))
    if payload.task_type == "export":
        data["prompt"] = ""
        data["prompt_template_id"] = None
        data["model_id"] = None
        data["model_sequence"] = None
        data["push_webhook_ids"] = []
        data["system_prompt_custom_enabled"] = False
        data["system_prompt_template"] = None
        data["system_prompt_include_message_count"] = False
    else:
        data["model_sequence"] = _normalize_model_sequence(
            db,
            model_sequence=data.get("model_sequence"),
            fallback_model_id=data.get("model_id"),
        )
        data["model_id"] = data["model_sequence"][0]["model_id"]
        resolved_prompt, template_id = _resolve_prompt_content(
            db,
            prompt=payload.prompt,
            template_id=payload.prompt_template_id,
        )
        data["prompt"] = resolved_prompt
        data["prompt_template_id"] = template_id
    return task_repo.create_task(db, obj_in=data)


def update_task(db: Session, task_id: int, payload: TaskUpdate) -> Task:
    entity = task_repo.get(db, task_id)
    if not entity:
        raise ValueError("任务不存在")
    obj_in = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "topic_style_config" in obj_in:
        obj_in["topic_style_config"] = topic_card_service.normalize_topic_style_config(obj_in["topic_style_config"])
    target_type = obj_in.get("task_type", entity.task_type)
    if target_type == "export":
        obj_in["prompt"] = ""
        obj_in["prompt_template_id"] = None
        obj_in["model_id"] = None
        obj_in["model_sequence"] = None
        obj_in["push_webhook_ids"] = []
        obj_in["system_prompt_custom_enabled"] = False
        obj_in["system_prompt_template"] = None
        obj_in["system_prompt_include_message_count"] = False
    else:
        if "model_sequence" in obj_in or "model_id" in obj_in:
            obj_in["model_sequence"] = _normalize_model_sequence(
                db,
                model_sequence=obj_in.get("model_sequence"),
                fallback_model_id=obj_in.get("model_id", entity.model_id),
            )
            obj_in["model_id"] = obj_in["model_sequence"][0]["model_id"]
        if "prompt" in obj_in or "prompt_template_id" in obj_in:
            resolved_prompt, template_id = _resolve_prompt_content(
                db,
                prompt=obj_in.get("prompt"),
                template_id=obj_in.get("prompt_template_id", entity.prompt_template_id),
                fallback_prompt=entity.prompt,
            )
            obj_in["prompt"] = resolved_prompt
            obj_in["prompt_template_id"] = template_id
    return task_repo.update_task(db, entity=entity, obj_in=obj_in)


def delete_task(db: Session, task_id: int) -> None:
    entity = task_repo.get(db, task_id)
    if not entity:
        raise ValueError("任务不存在")
    task_repo.delete(db, entity=entity)


def get_task(db: Session, task_id: int) -> TaskOut:
    entity = task_repo.get_with_jobs(db, task_id)
    if not entity:
        raise ValueError("任务不存在")
    task_dict = task_to_dict(entity)
    task_dict["topic_style_config"] = topic_card_service.normalize_topic_style_config(task_dict.get("topic_style_config"))
    jobs = _sorted_jobs(entity)
    task_dict["jobs"] = [JobOut.model_validate(job_to_dict(job)) for job in jobs]
    return TaskOut.model_validate(task_dict)


def _normalize_model_sequence(
    db: Session,
    *,
    model_sequence: Optional[List[dict]],
    fallback_model_id: Optional[int],
) -> List[dict]:
    raw_items = model_sequence or []
    normalized: List[dict] = []
    for item in raw_items:
        if not item:
            continue
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        model_id = int(item.get("model_id") or 0)
        if model_id <= 0:
            continue
        max_attempts = max(int(item.get("max_attempts") or 2), 1)
        normalized.append({"model_id": model_id, "max_attempts": max_attempts})
    if not normalized and fallback_model_id:
        normalized = [{"model_id": int(fallback_model_id), "max_attempts": 2}]
    if not normalized:
        raise ValueError("日报和话题卡片任务至少需要配置一个模型")
    for item in normalized:
        if not model_repo.get(db, item["model_id"]):
            raise ValueError(f"模型不存在：{item['model_id']}")
    return normalized


def create_job(db: Session, task_id: int, payload: JobCreate) -> Job:
    task = task_repo.get(db, task_id)
    if not task:
        raise ValueError("任务不存在")
    obj = payload.model_dump()
    obj["task_id"] = task_id
    max_order = job_repo.get_max_display_order(db, task_id)
    obj["display_order"] = max_order + 1
    if "chatlog_backup_enabled" not in obj:
        obj["chatlog_backup_enabled"] = bool(getattr(task, "store_chatlog", False))
    obj = _apply_github_settings(db, obj_in=obj, is_update=False)
    obj = _apply_job_feature_settings(obj, is_update=False)
    obj = _apply_message_stats_github_settings(db, obj_in=obj, is_update=False)
    obj = _apply_ima_account_settings(db, obj_in=obj, is_update=False)
    return job_repo.create_job(db, obj_in=obj)


def update_job(db: Session, job_id: int, payload: JobUpdate) -> Job:
    entity = job_repo.get_by_id(db, job_id)
    if not entity:
        raise ValueError("作业不存在")
    obj_in = {k: v for k, v in payload.model_dump().items() if v is not None}
    obj_in = _apply_github_settings(db, obj_in=obj_in, existing_config_id=entity.github_config_id, is_update=True)
    obj_in = _apply_job_feature_settings(obj_in, is_update=True)
    obj_in = _apply_message_stats_github_settings(
        db,
        obj_in=obj_in,
        existing_config_id=entity.message_stats_github_config_id,
        is_update=True,
    )
    obj_in = _apply_ima_account_settings(
        db,
        obj_in=obj_in,
        existing_account_id=entity.ima_account_id,
        is_update=True,
    )
    return job_repo.update_job(db, entity=entity, obj_in=obj_in)


def delete_job(db: Session, job_id: int) -> None:
    entity = job_repo.get_by_id(db, job_id)
    if not entity:
        raise ValueError("作业不存在")
    job_repo.delete(db, entity=entity)


def reorder_jobs(db: Session, task_id: int, job_ids: List[int]) -> List[Job]:
    task = task_repo.get_with_jobs(db, task_id)
    if not task:
        raise ValueError("任务不存在")
    existing_jobs = job_repo.list_by_task(db, task_id)
    existing_ids = [job.id for job in existing_jobs]
    if len(job_ids) != len(existing_ids) or set(job_ids) != set(existing_ids):
        raise ValueError("作业列表与当前配置不一致")
    job_map = {job.id: job for job in existing_jobs}
    for order, job_id in enumerate(job_ids):
        job = job_map.get(job_id)
        if not job:
            raise ValueError(f"作业 {job_id} 不属于任务 {task_id}")
        job.display_order = order
        db.add(job)
    db.flush()
    return [job_map[job_id] for job_id in job_ids]


def _resolve_prompt_content(
    db: Session,
    *,
    prompt: Optional[str],
    template_id: Optional[int],
    fallback_prompt: Optional[str] = None,
) -> Tuple[str, Optional[int]]:
    text = (prompt if prompt is not None else fallback_prompt) or ""
    if template_id:
        template = template_repo.get(db, template_id)
        if not template:
            raise ValueError("提示词模板不存在")
        desired = text.strip() or template.content
        if not desired.strip():
            raise ValueError("提示词内容不能为空")
        if desired != template.content:
            template_repo.update(db, entity=template, obj_in={"content": desired})
            task_repo.sync_prompt_template(db, template_id, desired)
        return desired, template_id

    if not text.strip():
        raise ValueError("提示词内容不能为空")
    return text, None


def _apply_github_settings(
    db: Session,
    obj_in: dict,
    *,
    existing_config_id: Optional[int] = None,
    is_update: bool = False,
) -> dict:
    enabled = bool(obj_in.get("github_deploy_enabled"))
    config_id = obj_in.get("github_config_id")
    if enabled:
        target_id = config_id or existing_config_id
        if not target_id:
            raise ValueError("启用 GitHub 部署时需选择配置")
        config = github_config_repo.get(db, target_id)
        if not config:
            raise ValueError("GitHub 配置不存在")
        obj_in["github_config_id"] = target_id
    else:
        obj_in["github_config_id"] = None
        obj_in.setdefault("days_offset", 0)

    if "days_offset" in obj_in:
        try:
            obj_in["days_offset"] = int(obj_in["days_offset"] or 0)
        except (TypeError, ValueError):
            obj_in["days_offset"] = 0
    if "html_backup_enabled" not in obj_in:
        obj_in["html_backup_enabled"] = False
    if "html_backup_filename_template" not in obj_in and not is_update:
        obj_in["html_backup_filename_template"] = None
    if "html_backup_filename_date_offset_days" not in obj_in:
        obj_in["html_backup_filename_date_offset_days"] = -1
    if "github_deploy_enabled" not in obj_in:
        obj_in["github_deploy_enabled"] = False
    return obj_in


def _apply_job_feature_settings(obj_in: dict, *, is_update: bool) -> dict:
    def ensure_default(key: str, default):
        if key in obj_in:
            if obj_in[key] in (None, ""):
                obj_in[key] = default
        elif not is_update:
            obj_in[key] = default

    ensure_default("message_stats_enabled", False)
    ensure_default("message_stats_path", "backups/message_reports")
    ensure_default("message_stats_filename_template", "每日群成员发言数量统计_{YYYY-MM-DD}")
    ensure_default("message_stats_filename_date_offset_days", -1)
    ensure_default("message_stats_github_enabled", False)
    ensure_default("message_stats_github_filename_template", "每日群成员发言数量统计_{YYYY-MM-DD}")
    ensure_default("message_stats_github_filename_date_offset_days", 0)
    ensure_default("message_stats_github_root", "xinjian")
    message_stats_enabled = obj_in.get("message_stats_enabled")
    if message_stats_enabled:
        formats = obj_in.get("message_stats_formats")
        if not formats:
            obj_in["message_stats_formats"] = ["md"]
    elif message_stats_enabled is False:
        if "message_stats_formats" in obj_in:
            obj_in["message_stats_formats"] = None
        if "message_stats_github_enabled" in obj_in:
            obj_in["message_stats_github_enabled"] = False

    ensure_default("chatlog_backup_enabled", False)
    ensure_default("chatlog_backup_path", "backups/chatlogs")
    ensure_default("chatlog_backup_filename_template", "聊天记录_{week_start}_{week_end}")
    ensure_default("chatlog_backup_filename_date_offset_days", 0)
    if obj_in.get("chatlog_backup_enabled"):
        formats = obj_in.get("chatlog_backup_formats")
        if not formats:
            obj_in["chatlog_backup_formats"] = ["txt"]
    else:
        if "chatlog_backup_formats" in obj_in:
            obj_in["chatlog_backup_formats"] = None

    ensure_default("model_output_backup_enabled", False)
    ensure_default("model_output_path", "backups/model_outputs")
    ensure_default("model_output_filename_template", "模型输出_{YYYY-MM-DD}")
    ensure_default("model_output_filename_date_offset_days", -1)
    ensure_default("ima_sync_enabled", False)
    ensure_default("ima_use_default_account", True)
    ensure_default("ima_use_default_target", True)
    if obj_in.get("model_output_backup_enabled"):
        formats = obj_in.get("model_output_formats")
        if not formats:
            obj_in["model_output_formats"] = ["md"]
    else:
        if "model_output_formats" in obj_in:
            obj_in["model_output_formats"] = None
        if "ima_sync_enabled" in obj_in:
            obj_in["ima_sync_enabled"] = False
    if obj_in.get("ima_sync_enabled") is False:
        if "ima_account_id" in obj_in:
            obj_in["ima_account_id"] = None
    if obj_in.get("ima_use_default_account") is True and "ima_account_id" in obj_in:
        obj_in["ima_account_id"] = None

    ensure_default("weekly_period", "previous_week")
    ensure_default("weekly_start_day", 0)
    ensure_default("weekly_start_time", "00:00")
    ensure_default("weekly_end_day", 6)
    ensure_default("weekly_end_time", "24:00")
    ensure_default("topic_text_layout", "per_topic")
    ensure_default("topic_text_merge_threshold", 3)
    ensure_default("topic_image_enabled", False)
    ensure_default("topic_image_layout", "single")
    ensure_default("topic_image_merge_threshold", 3)
    ensure_default("topic_image_backup_enabled", False)
    ensure_default("topic_image_backup_path", None)
    ensure_default("disk_alert_enabled", False)
    ensure_default("disk_alert_threshold_bytes", 100 * 1024 * 1024)

    ensure_default("html_backup_filename_template", None)
    ensure_default("html_backup_filename_date_offset_days", -1)

    for key in (
        "message_stats_filename_date_offset_days",
        "message_stats_github_filename_date_offset_days",
        "chatlog_backup_filename_date_offset_days",
        "model_output_filename_date_offset_days",
        "html_backup_filename_date_offset_days",
        "disk_alert_threshold_bytes",
        "weekly_start_day",
        "weekly_end_day",
        "topic_text_merge_threshold",
        "topic_image_merge_threshold",
    ):
        if key in obj_in and obj_in[key] is not None:
            try:
                obj_in[key] = int(obj_in[key])
            except (TypeError, ValueError):
                obj_in[key] = 0
    return obj_in


def _apply_message_stats_github_settings(
    db: Session,
    obj_in: dict,
    *,
    existing_config_id: Optional[int] = None,
    is_update: bool = False,
) -> dict:
    message_stats_enabled = obj_in.get("message_stats_enabled")
    if message_stats_enabled is False:
        obj_in["message_stats_github_enabled"] = False

    enabled_flag = obj_in.get("message_stats_github_enabled")
    config_id = obj_in.get("message_stats_github_config_id")
    if enabled_flag is True:
        target_id = config_id or existing_config_id
        if not target_id:
            raise ValueError("启用群消息统计同步时需选择 GitHub 配置")
        config = github_config_repo.get(db, target_id)
        if not config:
            raise ValueError("GitHub 配置不存在")
        obj_in["message_stats_github_config_id"] = target_id
    elif enabled_flag is False:
        obj_in["message_stats_github_config_id"] = None
        if not is_update:
            obj_in.setdefault("message_stats_github_enabled", False)
    elif config_id is not None:
        config = github_config_repo.get(db, config_id)
        if not config:
            raise ValueError("GitHub 配置不存在")
        obj_in["message_stats_github_config_id"] = config_id

    if "message_stats_github_filename_template" in obj_in and obj_in["message_stats_github_filename_template"] in (None, ""):
        obj_in["message_stats_github_filename_template"] = "每日群成员发言数量统计_{YYYY-MM-DD}"
    if "message_stats_github_root" in obj_in:
        root_value = obj_in["message_stats_github_root"]
        if isinstance(root_value, str):
            root_value = root_value.strip().strip("/ ")
        if root_value in (None, ""):
            root_value = "xinjian"
        obj_in["message_stats_github_root"] = root_value
    if "message_stats_github_filename_date_offset_days" in obj_in:
        try:
            obj_in["message_stats_github_filename_date_offset_days"] = int(
                obj_in["message_stats_github_filename_date_offset_days"] or 0
            )
        except (TypeError, ValueError):
            obj_in["message_stats_github_filename_date_offset_days"] = 0
    return obj_in


def _apply_ima_account_settings(
    db: Session,
    obj_in: dict,
    *,
    existing_account_id: Optional[int] = None,
    is_update: bool = False,
) -> dict:
    enabled_flag = obj_in.get("ima_sync_enabled")
    if enabled_flag is False:
        obj_in["ima_account_id"] = None
        if not is_update:
            obj_in.setdefault("ima_use_default_account", True)
        return obj_in

    use_default_account = obj_in.get("ima_use_default_account")
    if use_default_account is True:
        obj_in["ima_account_id"] = None
        return obj_in

    account_id = obj_in.get("ima_account_id")
    target_id = account_id or existing_account_id
    if use_default_account is False:
        if not target_id:
            raise ValueError("请选择 ima 账号")
        account = ima_account_repo.get(db, target_id)
        if not account:
            raise ValueError("所选 ima 账号不存在")
        if not account.is_enabled:
            raise ValueError("所选 ima 账号已停用")
        obj_in["ima_account_id"] = target_id
    return obj_in
