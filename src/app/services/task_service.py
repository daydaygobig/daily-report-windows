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
from ..repositories.webhook_repo import WebhookRepository
from pydantic_core import PydanticUndefined

from ..schemas.job import JobBase, JobCreate, JobOut, JobUpdate
from ..schemas.task import TaskCreate, TaskOut, TaskUpdate
from ..utils.converters import job_to_dict, task_to_dict
from . import image_card_service, topic_card_service


task_repo = TaskRepository()
job_repo = JobRepository()
github_config_repo = GithubConfigRepository()
template_repo = PromptTemplateRepository()
ima_account_repo = ImaAccountRepository()
model_repo = ModelRepository()
webhook_repo = WebhookRepository()


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
        data["upstream_task_id"] = None
        data.update(_image_task_fields(db, data, target_type="export"))
    else:
        data["model_sequence"] = _normalize_model_sequence(
            db,
            model_sequence=data.get("model_sequence"),
            fallback_model_id=data.get("model_id"),
        )
        data["model_id"] = data["model_sequence"][0]["model_id"]
        data["upstream_task_id"] = _normalize_upstream_task(
            db,
            upstream_task_id=data.get("upstream_task_id"),
            task_type=payload.task_type,
        )
        data["card_input_source"] = _normalize_card_input_source(
            data.get("card_input_source"),
            task_type=payload.task_type,
            upstream_task_id=data.get("upstream_task_id"),
        )
        resolved_prompt, template_id = _resolve_prompt_content(
            db,
            prompt=payload.prompt,
            template_id=payload.prompt_template_id,
        )
        data["prompt"] = resolved_prompt
        data["prompt_template_id"] = template_id
        if payload.task_type == "image_card":
            data["image_model_sequence"] = _normalize_image_model_sequence(
                db,
                image_model_sequence=data.get("image_model_sequence"),
                fallback_image_model_id=data.get("image_model_id"),
            )
            data["image_model_id"] = data["image_model_sequence"][0]["model_id"]
        data.update(_image_task_fields(db, data, target_type=payload.task_type))
    return task_repo.create_task(db, obj_in=data)


def update_task(db: Session, task_id: int, payload: TaskUpdate) -> Task:
    entity = task_repo.get(db, task_id)
    if not entity:
        raise ValueError("任务不存在")
    obj_in = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "topic_style_config" in obj_in:
        obj_in["topic_style_config"] = topic_card_service.normalize_topic_style_config(obj_in["topic_style_config"])
    target_type = obj_in.get("task_type", entity.task_type)
    if target_type not in ("topic_card", "image_card"):
        obj_in["upstream_task_id"] = None
        obj_in["card_input_source"] = "chatlog"
    elif "card_input_source" in obj_in:
        obj_in["card_input_source"] = _normalize_card_input_source(
            obj_in.get("card_input_source"),
            task_type=target_type,
            upstream_task_id=obj_in.get("upstream_task_id", entity.upstream_task_id),
        )
    elif "upstream_task_id" in obj_in and (getattr(entity, "card_input_source", "chatlog") or "chatlog") == "report":
        # 纯日报内容模式下不允许把上游日报解绑（0 表示清除）
        if obj_in["upstream_task_id"] in (None, 0):
            raise ValueError("纯日报内容模式的卡片任务必须绑定上游日报任务")
    elif "upstream_task_id" in obj_in:
        obj_in["upstream_task_id"] = _normalize_upstream_task(
            db,
            upstream_task_id=obj_in.get("upstream_task_id"),
            task_type=target_type,
            self_id=task_id,
        )
    if target_type == "export":
        obj_in["prompt"] = ""
        obj_in["prompt_template_id"] = None
        obj_in["model_id"] = None
        obj_in["model_sequence"] = None
        obj_in["image_model_sequence"] = None
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
        if target_type == "image_card" and ("image_model_sequence" in obj_in or "image_model_id" in obj_in):
            obj_in["image_model_sequence"] = _normalize_image_model_sequence(
                db,
                image_model_sequence=obj_in.get("image_model_sequence"),
                fallback_image_model_id=obj_in.get("image_model_id", entity.image_model_id),
            )
            obj_in["image_model_id"] = obj_in["image_model_sequence"][0]["model_id"]
        if "prompt" in obj_in or "prompt_template_id" in obj_in:
            resolved_prompt, template_id = _resolve_prompt_content(
                db,
                prompt=obj_in.get("prompt"),
                template_id=obj_in.get("prompt_template_id", entity.prompt_template_id),
                fallback_prompt=entity.prompt,
            )
            obj_in["prompt"] = resolved_prompt
            obj_in["prompt_template_id"] = template_id
    effective = task_to_dict(entity)
    effective.update(obj_in)
    obj_in.update(_image_task_fields(db, effective, target_type=target_type))
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


def _normalize_upstream_task(
    db: Session,
    *,
    upstream_task_id: Optional[int],
    task_type: str,
    self_id: Optional[int] = None,
) -> Optional[int]:
    """校验上游日报任务配置；0 或 None 表示清除。"""
    if upstream_task_id in (None, 0):
        return None
    if task_type not in ("topic_card", "image_card"):
        raise ValueError("只有话题卡片/图片卡片任务可以设置上游日报任务")
    if self_id is not None and int(upstream_task_id) == int(self_id):
        raise ValueError("上游日报任务不能是任务本身")
    upstream = task_repo.get(db, int(upstream_task_id))
    if not upstream:
        raise ValueError("上游日报任务不存在")
    if (getattr(upstream, "task_type", "report") or "report") != "report":
        raise ValueError("上游任务必须是日报（report）类型")
    return int(upstream_task_id)


def _normalize_card_input_source(
    value: Optional[str],
    *,
    task_type: str,
    upstream_task_id: Optional[int],
) -> str:
    """卡片任务可选纯日报内容模式（不拉聊天记录）；其余任务一律回落聊天记录模式。"""
    if task_type not in ("topic_card", "image_card"):
        return "chatlog"
    source = (value or "chatlog").strip() or "chatlog"
    if source not in ("chatlog", "report"):
        raise ValueError(f"卡片输入来源不支持：{source}")
    if source == "report" and upstream_task_id in (None, 0):
        raise ValueError("纯日报内容模式的卡片任务必须绑定上游日报任务")
    return source


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
        raise ValueError("模型任务至少需要配置一个文本模型")
    for item in normalized:
        model = model_repo.get(db, item["model_id"])
        if not model:
            raise ValueError(f"模型不存在：{item['model_id']}")
        if (getattr(model, "model_type", "text") or "text") != "text":
            raise ValueError(f"模型不是文本模型：{item['model_id']}")
    return normalized


def _normalize_image_model_sequence(
    db: Session,
    *,
    image_model_sequence: Optional[List[dict]],
    fallback_image_model_id: Optional[int],
) -> List[dict]:
    raw_items = image_model_sequence or []
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
    if not normalized and fallback_image_model_id:
        normalized = [{"model_id": int(fallback_image_model_id), "max_attempts": 2}]
    if not normalized:
        raise ValueError("图片卡片任务至少需要配置一个图片模型")
    for item in normalized:
        model = model_repo.get(db, item["model_id"])
        if not model:
            raise ValueError(f"模型不存在：{item['model_id']}")
        if (getattr(model, "model_type", "text") or "text") != "image":
            raise ValueError(f"模型不是图片模型：{item['model_id']}")
    return normalized


def _image_task_fields(db: Session, effective: dict, *, target_type: str) -> dict:
    template_id = effective.get("prompt_template_id")
    if template_id:
        template = template_repo.get(db, int(template_id))
        if not template:
            raise ValueError("提示词模板不存在")
        if (getattr(template, "template_type", "regular") or "regular") != "regular":
            raise ValueError("任务只能使用常规提示词模板")

    if target_type != "image_card":
        return {
            "image_model_id": None,
            "image_model_sequence": None,
            "image_split_enabled": False,
            "image_split_prompt": None,
        }

    image_model_id = effective.get("image_model_id")
    if not image_model_id:
        raise ValueError("图片卡片任务需要选择图片模型")
    image_model = model_repo.get(db, int(image_model_id))
    if not image_model:
        raise ValueError("图片模型不存在")
    if (getattr(image_model, "model_type", "text") or "text") != "image":
        raise ValueError("所选模型不是图片模型")

    push_ids = [int(value) for value in (effective.get("push_webhook_ids") or []) if value]
    if not push_ids:
        raise ValueError("图片卡片任务至少需要选择一个推送 Webhook")
    webhooks = webhook_repo.get_by_ids(db, push_ids)
    if len(webhooks) != len(set(push_ids)):
        raise ValueError("推送 Webhook 不存在")
    for webhook in webhooks:
        if not (getattr(webhook, "feishu_app_id", None) or "").strip() or not getattr(
            webhook, "feishu_app_secret_cipher", None
        ):
            raise ValueError(f"Webhook「{webhook.name}」未配置飞书应用 App ID / App Secret")

    return {
        "image_model_id": int(image_model_id),
        "image_split_enabled": False,
        "image_split_prompt": None,
    }


def _apply_image_card_job_settings(
    db: Session,
    task: Task,
    obj_in: dict,
    *,
    existing_job: Job | None = None,
) -> dict:
    if getattr(task, "task_type", "report") != "image_card":
        obj_in.update(
            {
                "image_prompt_template_id": None,
                "image_prompt": None,
                "image_split_enabled": False,
                "image_split_prompt": None,
                "card_renderer": "ai",
                "card_font_theme": "A",
            }
        )
        return obj_in

    # 出图方式归一化：ai=AI 直出（需图片提示词模板）；local=本地渲染器（模板可选）
    renderer = str(obj_in.get("card_renderer") or "").strip().lower()
    if renderer not in {"ai", "local"}:
        renderer = str(getattr(existing_job, "card_renderer", "") or "ai").strip().lower()
        renderer = renderer if renderer in {"ai", "local"} else "ai"
    theme = str(obj_in.get("card_font_theme") or "").strip().upper()
    if theme not in {"A", "B", "C"}:
        theme = str(getattr(existing_job, "card_font_theme", "") or "A").strip().upper()
        theme = theme if theme in {"A", "B", "C"} else "A"

    template_id = obj_in.get("image_prompt_template_id")
    if not template_id and existing_job is not None:
        template_id = getattr(existing_job, "image_prompt_template_id", None)
        if not template_id and (getattr(existing_job, "image_prompt", None) or "").strip():
            return obj_in
    if renderer != "local" and not template_id:
        raise ValueError("图片卡片作业需要选择图片提示词模板")
    template = None
    if template_id:
        template = template_repo.get(db, int(template_id))
        if not template:
            raise ValueError("图片提示词模板不存在")
        if (getattr(template, "template_type", "regular") or "regular") != "image":
            raise ValueError("图片卡片作业只能使用图片提示词模板")

    if "image_split_enabled" in obj_in:
        split_enabled = bool(obj_in.get("image_split_enabled"))
    elif existing_job is not None:
        split_enabled = bool(getattr(existing_job, "image_split_enabled", False))
    else:
        split_enabled = True
    split_prompt = obj_in.get("image_split_prompt")
    if "image_split_prompt" not in obj_in and existing_job is not None:
        split_prompt = getattr(existing_job, "image_split_prompt", None)

    if renderer == "local":
        obj_in.update(
            {
                "image_prompt_template_id": int(template_id) if template_id else None,
                "image_prompt": template.content if template else None,
                "image_split_enabled": split_enabled,
                "image_split_prompt": image_card_service.normalize_split_prompt(
                    split_enabled,
                    split_prompt,
                ),
                "card_renderer": "local",
                "card_font_theme": theme,
            }
        )
        return obj_in

    obj_in.update(
        {
            "image_prompt_template_id": int(template_id),
            "image_prompt": template.content,
            "image_split_enabled": split_enabled,
            "image_split_prompt": image_card_service.normalize_split_prompt(
                split_enabled,
                split_prompt,
            ),
            "card_renderer": "ai",
            "card_font_theme": theme,
        }
    )
    return obj_in


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
    obj = _apply_image_card_job_settings(db, task, obj)
    return job_repo.create_job(db, obj_in=obj)


def update_job(db: Session, job_id: int, payload: JobUpdate) -> Job:
    entity = job_repo.get_by_id(db, job_id)
    if not entity:
        raise ValueError("作业不存在")
    task = task_repo.get(db, entity.task_id)
    if not task:
        raise ValueError("任务不存在")
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
    obj_in = _apply_image_card_job_settings(db, task, obj_in, existing_job=entity)
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


def _job_base_defaults() -> dict:
    """从 JobBase schema 派生字段默认值，避免与 pydantic 定义重复维护。"""
    defaults: dict = {}
    for name, field in JobBase.model_fields.items():
        if field.default is not PydanticUndefined and field.default is not None:
            defaults[name] = field.default
        elif field.default_factory is not None:
            defaults[name] = field.default_factory()
    return defaults


def _apply_job_feature_settings(obj_in: dict, *, is_update: bool) -> dict:
    def ensure_default(key: str, default):
        if key in obj_in:
            if obj_in[key] in (None, ""):
                obj_in[key] = default
        elif not is_update:
            obj_in[key] = default

    for key, default in _job_base_defaults().items():
        ensure_default(key, default)

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

    if obj_in.get("chatlog_backup_enabled"):
        formats = obj_in.get("chatlog_backup_formats")
        if not formats:
            obj_in["chatlog_backup_formats"] = ["txt"]
    else:
        if "chatlog_backup_formats" in obj_in:
            obj_in["chatlog_backup_formats"] = None

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
        "max_image_count",
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
