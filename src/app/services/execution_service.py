"""Execution history service."""

import json
from contextlib import nullcontext
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, urlparse

from sqlalchemy.orm import Session, object_session

from ..models.execution import Execution
from ..models.github_deployment import GithubDeployment
from ..models.disk_monitor import DiskIoRecord
from ..repositories.execution_repo import ExecutionRepository
from ..schemas.execution import ExecutionOut
from .github_view_url import build_view_url

execution_repo = ExecutionRepository()
_STALE_RUNNING_MESSAGE = "执行被中断：服务重启或进程退出导致状态未回写"
_TOPIC_TYPE_LABELS = {
    "industry_business": "行业商业",
    "work_methods": "工作方法",
    "career_growth": "求职发展",
    "mind_wellbeing": "心理认知",
}
_STYLE_LABELS = {
    "style_a": "极简线框",
    "style_b": "温暖气泡",
    "style_c": "快报嵌套",
    "style_d": "兜底毛玻璃",
}
_THEME_LABELS = {
    "amber": "琥珀橙",
    "blue": "靛蓝",
    "green": "翠绿",
    "neutral": "中性紫",
}
_DELIVERY_STATUS_LABELS = {
    "success": "成功",
    "failed": "失败",
    "pending": "待处理",
}
_IMAGE_LAYOUT_LABELS = {
    "single": "单张",
    "collection": "合集长图",
}


def list_recent_executions(db: Session, limit: int = 50) -> List[ExecutionOut]:
    _repair_stale_executions(db)
    executions = execution_repo.list_recent(db, limit=limit)
    return [_to_schema(execution) for execution in executions]


def list_executions_paginated(
    db: Session,
    *,
    page: int,
    page_size: int,
    execution_id: Optional[int] = None,
    task_id: Optional[int] = None,
    job_id: Optional[int] = None,
    status: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    _repair_stale_executions(db)
    total, executions = execution_repo.list_paginated(
        db,
        page=page,
        page_size=page_size,
        execution_id=execution_id,
        task_id=task_id,
        job_id=job_id,
        status=status,
        start_time=start_time,
        end_time=end_time,
    )
    items = [_to_schema(execution).model_dump() for execution in executions]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_execution(db: Session, execution_id: int) -> Optional[ExecutionOut]:
    _repair_stale_executions(db)
    execution = execution_repo.get(db, execution_id)
    if not execution:
        return None
    return _to_schema(execution)


def _safe_loads(payload: str) -> Dict[str, Any]:
    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {"raw": payload}


def _repair_stale_executions(db: Session) -> None:
    stale = (
        db.query(Execution)
        .filter(Execution.status == "running", Execution.finished_at.isnot(None))
        .all()
    )
    if not stale:
        return
    for execution in stale:
        execution.status = "failed"
        if not execution.error_msg:
            execution.error_msg = _STALE_RUNNING_MESSAGE
    db.flush()


def _to_schema(execution) -> ExecutionOut:
    job = execution.job
    task = job.task if job else None
    job_name = job.name if job else None
    task_name = task.name if task else None
    job_execution_time = job.execution_time if job else None
    job_created_at = job.created_at if job else None
    prompt_context = _safe_loads(execution.raw_request) if execution.raw_request else None
    prompt_usage = _safe_loads(execution.prompt_usage) if execution.prompt_usage else None
    db = object_session(execution)
    deployment_records = _github_deployment_records(db, execution)
    html_deployment_record = _html_deployment_record(deployment_records)
    github_deployments = [_github_deployment_item(record) for record in deployment_records]
    raw_exported = execution.exported_files
    exported_files = _safe_load_list(raw_exported) if raw_exported else None
    deploy_artifact = _deployment_artifact(html_deployment_record)
    deploy_url = deploy_artifact.get("url") if deploy_artifact else execution.deploy_url
    if deploy_artifact:
        exported_files = _merge_deploy_artifact(exported_files, deploy_artifact)
    if exported_files is not None:
        execution.exported_files = exported_files
    no_autoflush = db.no_autoflush if db is not None else nullcontext()

    try:
        with no_autoflush:
            schema = ExecutionOut.model_validate(execution, from_attributes=True).model_copy(
                update={
                    "job_name": job_name,
                    "task_name": task_name,
                    "job_execution_time": job_execution_time,
                    "job_created_at": job_created_at,
                    "prompt_context": prompt_context,
                    "is_manual": bool(getattr(execution, "is_manual", False)),
                    "prompt_usage": prompt_usage,
                    "github_config_name": execution.github_config.name if execution.github_config else None,
                    "deploy_url": deploy_url,
                    "deploy_record_id": html_deployment_record.id if html_deployment_record else None,
                    "deploy_repo_path": deploy_artifact.get("repo_path") if deploy_artifact else None,
                    "deploy_repo_full_name": deploy_artifact.get("repo") if deploy_artifact else None,
                    "deploy_branch": deploy_artifact.get("branch") if deploy_artifact else None,
                    "deploy_github_file_url": deploy_artifact.get("github_file_url") if deploy_artifact else None,
                    "github_deployments": github_deployments or None,
                    "ima_sync_status": getattr(execution, "ima_sync_status", None),
                    "ima_sync_error": getattr(execution, "ima_sync_error", None),
                    "ima_sync_batch_id": getattr(execution, "ima_sync_batch_id", None),
                    "exported_files": exported_files,
                    "disk_io": _latest_disk_io(execution),
                    "topic_card_meta": _topic_card_meta(execution),
                    "image_card_meta": _image_card_meta(execution),
                }
            )
    finally:
        execution.exported_files = raw_exported
    return schema


def _merge_deploy_artifact(
    exported_files: Optional[List[Dict[str, Any]]],
    deploy_artifact: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items = list(exported_files or [])
    for index, item in enumerate(items):
        if item.get("type") == "github":
            items[index] = {**item, **deploy_artifact}
            return items
    items.append(deploy_artifact)
    return items


def _github_deployment_records(db: Optional[Session], execution) -> List[GithubDeployment]:
    if not getattr(execution, "id", None):
        return []
    if db is not None:
        return (
            db.query(GithubDeployment)
            .filter(GithubDeployment.execution_id == execution.id)
            .order_by(GithubDeployment.id.asc())
            .all()
        )
    return list(getattr(execution, "deploy_records", []) or [])


def _html_deployment_record(records: List[GithubDeployment]) -> Optional[GithubDeployment]:
    for record in records:
        if record.artifact_type in (None, "html_report"):
            return record
    return None


def _github_deployment_item(record: GithubDeployment) -> Dict[str, Any]:
    artifact = _deployment_artifact(record)
    view_url = build_view_url(record, fallback_url=record.pages_url)
    return {
        "id": record.id,
        "artifact_type": record.artifact_type or "html_report",
        "artifact_label": record.artifact_label or ("消息统计" if record.artifact_type == "message_stats" else "HTML 日报"),
        "status": record.status,
        "error_msg": record.error_msg,
        "pages_url": view_url,
        "repo_full_name": (artifact or {}).get("repo"),
        "branch": (artifact or {}).get("branch"),
        "repo_path": (artifact or {}).get("repo_path"),
        "github_file_url": (artifact or {}).get("github_file_url"),
    }


def _deployment_artifact(record) -> Optional[Dict[str, Any]]:
    if not record:
        return None
    repo_path = record.repo_path or _infer_repo_path_from_pages_url(record)
    repo_full_name = record.repo_full_name or _repo_full_name(record)
    branch = record.branch or _branch(record)
    github_file_url = record.github_file_url or _build_github_file_url(repo_full_name, branch, repo_path)
    view_url = build_view_url(record, fallback_url=record.pages_url)
    return {
        "type": "github",
        "label": record.artifact_label or "GitHub 页面",
        "url": view_url,
        "path": repo_path,
        "repo_path": repo_path,
        "repo": repo_full_name,
        "branch": branch,
        "github_file_url": github_file_url,
    }


def _repo_full_name(record) -> Optional[str]:
    config = record.github_config
    if config and config.owner and config.repo:
        return f"{config.owner}/{config.repo}"
    return None


def _branch(record) -> Optional[str]:
    config = record.github_config
    if config and config.branch:
        return config.branch
    return "main" if record.pages_url else None


def _build_github_file_url(repo_full_name: Optional[str], branch: Optional[str], repo_path: Optional[str]) -> Optional[str]:
    if not repo_full_name or not branch or not repo_path:
        return None
    encoded_branch = quote(branch.strip(), safe="")
    encoded_path = quote(repo_path.strip("/"), safe="/")
    return f"https://github.com/{repo_full_name}/blob/{encoded_branch}/{encoded_path}"


def _infer_repo_path_from_pages_url(record) -> Optional[str]:
    if not record.pages_url:
        return None
    config = record.github_config
    if config:
        base = (config.pages_base_url or f"https://{config.owner}.github.io/{config.repo}/").strip()
        if not base.endswith("/"):
            base += "/"
        if record.pages_url.startswith(base):
            return unquote(record.pages_url[len(base) :].lstrip("/"))

    parsed = urlparse(record.pages_url)
    fallback_path = parsed.path.lstrip("/")
    if config and config.repo and fallback_path.startswith(f"{config.repo}/"):
        fallback_path = fallback_path[len(config.repo) + 1 :]
    return unquote(fallback_path) or None


def _topic_card_meta(execution) -> Optional[Dict[str, Any]]:
    if not execution.raw_response:
        return None
    data = _safe_loads(execution.raw_response)
    if data.get("type") != "topic_card":
        return None

    cards = data.get("cards") if isinstance(data.get("cards"), list) else []
    deliveries = data.get("deliveries") if isinstance(data.get("deliveries"), list) else []

    return {
        "文字布局": _text_layout_label(data.get("text_layout")),
        "图片推送": "已开启" if data.get("image_enabled") else "未开启",
        "图片布局": _image_layout_label(data.get("image_layout")),
        "话题数量": len(cards),
        "话题列表": [_topic_card_item(card) for card in cards if isinstance(card, dict)],
        "推送记录": [_topic_delivery_item(item) for item in deliveries if isinstance(item, dict)],
    }


def _image_card_meta(execution) -> Optional[Dict[str, Any]]:
    if not execution.raw_response:
        return None
    data = _safe_loads(execution.raw_response)
    if data.get("type") != "image_card":
        return None

    deliveries = data.get("deliveries") if isinstance(data.get("deliveries"), list) else []
    images = [_image_card_item(item, data.get("size")) for item in deliveries if isinstance(item, dict)]
    expected_count = int(data.get("block_count") or len(images) or 0)
    generated_count = sum(1 for item in images if item.get("生成状态") == "成功")
    if generated_count == expected_count and expected_count > 0 and not data.get("generation_error"):
        generation_status = "成功"
    elif generated_count > 0:
        generation_status = "部分成功"
    else:
        generation_status = "失败"

    push_records = [record for item in images for record in item.get("推送记录", [])]
    push_success_count = sum(1 for item in push_records if item.get("状态") == "成功")
    if not push_records:
        push_status = "未执行"
    elif push_success_count == len(push_records):
        push_status = "成功"
    elif push_success_count > 0:
        push_status = "部分失败"
    else:
        push_status = "失败"

    request_params = data.get("request_params") if isinstance(data.get("request_params"), dict) else {}
    return {
        "图片模型": str(data.get("image_model_name") or request_params.get("model") or "-"),
        "内容块数量": expected_count,
        "请求比例": str(data.get("aspect_ratio") or "auto"),
        "分辨率档位": str(data.get("resolution") or "auto").upper(),
        "请求尺寸": str(data.get("size") or request_params.get("size") or "auto"),
        "请求参数": {
            "model": request_params.get("model") or data.get("image_model_name") or "-",
            "n": request_params.get("n") or 1,
            "size": request_params.get("size") or data.get("size") or "auto",
            "output_format": request_params.get("output_format") or "png",
        },
        "生成状态": generation_status,
        "生成成功数": generated_count,
        "推送状态": push_status,
        "推送成功数": push_success_count,
        "推送总数": len(push_records),
        "图片列表": images,
    }


def _image_card_item(item: Dict[str, Any], fallback_size: Any) -> Dict[str, Any]:
    requested_size = str(item.get("requested_size") or fallback_size or "auto")
    actual_size = item.get("actual_size")
    if not actual_size and item.get("actual_width") and item.get("actual_height"):
        actual_size = f"{item['actual_width']}x{item['actual_height']}"
    webhooks = item.get("webhooks") if isinstance(item.get("webhooks"), list) else []
    return {
        "序号": item.get("image_index"),
        "生成状态": _DELIVERY_STATUS_LABELS.get(str(item.get("status") or "success"), str(item.get("status") or "-")),
        "请求尺寸": requested_size,
        "实际尺寸": str(actual_size) if actual_size else "-",
        "文件大小": _format_bytes(item.get("size_bytes")),
        "错误信息": item.get("error"),
        "推送记录": [
            {
                "推送渠道": webhook.get("webhook_name") or f"Webhook {webhook.get('webhook_id') or '-'}",
                "状态": _DELIVERY_STATUS_LABELS.get(str(webhook.get("status") or ""), str(webhook.get("status") or "-")),
                "图片标识": webhook.get("image_key"),
                "错误信息": webhook.get("error"),
            }
            for webhook in webhooks
            if isinstance(webhook, dict)
        ],
    }


def _topic_card_item(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "标题": str(card.get("title") or "-"),
        "话题类型": _TOPIC_TYPE_LABELS.get(str(card.get("topic_type") or ""), "工作方法"),
        "版式": _STYLE_LABELS.get(str(card.get("style_key") or ""), "温暖气泡"),
        "主题色": _THEME_LABELS.get(str(card.get("theme") or ""), "靛蓝"),
        "短标签": [str(item) for item in card.get("tags", []) if isinstance(item, str)],
        "讨论时段": str(card.get("time_range") or "-"),
    }


def _topic_delivery_item(item: Dict[str, Any]) -> Dict[str, Any]:
    images = item.get("images") if isinstance(item.get("images"), list) else []
    return {
        "推送渠道": item.get("webhook_name") or f"Webhook {item.get('webhook_id') or '-'}",
        "状态": _DELIVERY_STATUS_LABELS.get(str(item.get("status") or ""), str(item.get("status") or "-")),
        "错误信息": item.get("error"),
        "图片列表": [_topic_image_item(image) for image in images if isinstance(image, dict)],
    }


def _topic_image_item(image: Dict[str, Any]) -> Dict[str, Any]:
    width = image.get("width")
    height = image.get("height")
    size_bytes = image.get("size_bytes")
    return {
        "渲染引擎": str(image.get("engine") or "-").upper(),
        "图片布局": _image_layout_label(image.get("layout")),
        "图片尺寸": f"{width or '-'} × {height or '-'}",
        "文件大小": _format_bytes(size_bytes),
        "图片标识": str(image.get("image_key") or "-"),
    }


def _text_layout_label(value: Any) -> str:
    return {
        "per_topic": "逐话题",
        "merged": "合并",
        "auto": "自动",
    }.get(str(value or ""), str(value or "-"))


def _image_layout_label(value: Any) -> str:
    return _IMAGE_LAYOUT_LABELS.get(str(value or ""), str(value or "-"))


def _format_bytes(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} B" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024
    return "-"


def _latest_disk_io(execution) -> Optional[Dict[str, Any]]:
    db = object_session(execution)
    if db is None:
        return None
    record = (
        db.query(DiskIoRecord)
        .filter(DiskIoRecord.execution_id == execution.id)
        .order_by(DiskIoRecord.id.desc())
        .first()
    )
    if not record:
        return None
    return {
        "id": record.id,
        "provider": record.provider,
        "backend_read_bytes": record.backend_read_bytes,
        "backend_write_bytes": record.backend_write_bytes,
        "weflow_read_bytes": record.weflow_read_bytes,
        "weflow_write_bytes": record.weflow_write_bytes,
        "weflow_captured": bool(record.weflow_captured),
        "exported_file_bytes": record.exported_file_bytes,
        "chatlog_decrypt_write_bytes": record.chatlog_decrypt_write_bytes,
        "chatlog_decrypt_status": record.chatlog_decrypt_status,
        "chatlog_work_dir": record.chatlog_work_dir,
        "disk_write_bytes": record.disk_write_bytes,
        "total_read_bytes": record.total_read_bytes,
        "total_write_bytes": record.total_write_bytes,
        "media_enabled": bool(record.media_enabled),
        "is_warning": bool(record.is_warning),
        "warning_reason": record.warning_reason,
        "job_alert_threshold_bytes": record.job_alert_threshold_bytes,
        "job_alert_triggered": bool(record.job_alert_triggered),
        "job_alert_sent": bool(record.job_alert_sent),
        "job_alert_error": record.job_alert_error,
    }


def _safe_load_list(payload: str) -> Optional[List[Dict[str, Any]]]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data
    return None
