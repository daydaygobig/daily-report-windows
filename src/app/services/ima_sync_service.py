"""IMA sync settings and record services."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from loguru import logger
from sqlalchemy.orm import Session

from ..config import get_settings
from ..integrations import feishu
from ..integrations.ima import ImaApiError, ImaClient, ImaCredentials, ImaTarget
from ..integrations.security import decrypt_value, encrypt_value
from ..models.execution import Execution
from ..models.ima_account import ImaAccount
from ..models.ima_sync_job import ImaSyncJob
from ..models.ima_sync_record import ImaSyncRecord
from ..models.ima_sync_setting import ImaSyncSetting
from ..models.job import Job
from ..repositories.ima_account_repo import ImaAccountRepository
from ..repositories.ima_sync_job_repo import ImaSyncJobRepository
from ..repositories.ima_sync_record_repo import ImaSyncRecordRepository
from ..repositories.ima_sync_setting_repo import ImaSyncSettingRepository
from ..repositories.webhook_repo import WebhookRepository
from ..schemas.ima import (
    ImaAccountCreate,
    ImaAccountOut,
    ImaAccountUpdate,
    ImaSyncBatchOut,
    ImaCredentialPreview,
    ImaFolderOption,
    ImaSyncJobCreate,
    ImaSyncJobOut,
    ImaSyncJobUpdate,
    ImaManualSyncResult,
    ImaOption,
    ImaSyncRecordOut,
    ImaSyncSettingsOut,
    ImaSyncSettingsUpdate,
)
from ..utils.converters import _load_json

settings = get_settings()
account_repo = ImaAccountRepository()
setting_repo = ImaSyncSettingRepository()
sync_job_repo = ImaSyncJobRepository()
record_repo = ImaSyncRecordRepository()
webhook_repo = WebhookRepository()

SUPPORTED_FILE_TYPES: Dict[str, Dict[str, object]] = {
    "md": {"media_type": 7, "content_type": "text/markdown"},
    "txt": {"media_type": 13, "content_type": "text/plain"},
}
_KNOWLEDGE_FOLDER_CACHE_TTL_SECONDS = 300
_knowledge_folder_cache: Dict[tuple[int, str], tuple[float, List[Dict[str, str]]]] = {}


@dataclass
class SyncSummary:
    batch_id: str
    scanned_count: int = 0
    success_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0

    @property
    def status(self) -> str:
        if self.failed_count and not self.success_count and not self.skipped_count:
            return "failed"
        if self.failed_count:
            return "partial"
        if self.success_count:
            return "success"
        if self.skipped_count:
            return "skipped"
        return "none"

    @property
    def message(self) -> str:
        return (
            f"本次扫描 {self.scanned_count} 个文件，新增同步 {self.success_count} 个，"
            f"跳过重复 {self.skipped_count} 个，失败 {self.failed_count} 个"
        )


def get_settings_entity(db: Session) -> ImaSyncSetting:
    entity = setting_repo.get_singleton(db)
    if entity:
        return entity
    entity = setting_repo.create_default(db)
    db.flush()
    return entity


def get_settings_view(db: Session, *, next_run_at: Optional[datetime] = None) -> ImaSyncSettingsOut:
    account = _ensure_default_account_pointer(db)
    entity = get_settings_entity(db)
    return ImaSyncSettingsOut.model_validate(
        {
            "id": entity.id,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
            "default_account_id": account.id if account else entity.default_account_id,
            "default_account_name": account.name if account else None,
            "last_sync_at": entity.last_sync_at,
            "last_sync_status": entity.last_sync_status,
            "last_sync_summary": entity.last_sync_summary,
            "next_run_at": next_run_at,
        }
    )


def update_settings(db: Session, payload: ImaSyncSettingsUpdate) -> ImaSyncSetting:
    entity = get_settings_entity(db)
    data = payload.model_dump()
    default_account_id = data.get("default_account_id")
    if default_account_id:
        account = account_repo.get(db, default_account_id)
        if not account:
            raise ValueError("默认 ima 账号不存在")
        account_repo.clear_default(db)
        account_repo.update(db, entity=account, obj_in={"is_default": True})
    return setting_repo.update_settings(db, entity=entity, obj_in=data)


def list_accounts(db: Session) -> List[ImaAccountOut]:
    _ensure_default_account_pointer(db)
    return [_account_to_schema(item) for item in account_repo.list_all(db)]


def get_account(db: Session, account_id: int) -> Optional[ImaAccountOut]:
    _ensure_default_account_pointer(db)
    entity = account_repo.get(db, account_id)
    if not entity:
        return None
    return _account_to_schema(entity)


def create_account(db: Session, payload: ImaAccountCreate) -> ImaAccount:
    _ensure_legacy_account_migrated(db)
    data = _normalize_account_payload(payload)
    existing = account_repo.list_all(db)
    if not existing:
        data["is_default"] = True
    if data.get("is_default"):
        account_repo.clear_default(db)
    entity = account_repo.create(db, obj_in=data)
    _sync_default_account_setting(db, entity if entity.is_default else None)
    return entity


def update_account(db: Session, account_id: int, payload: ImaAccountUpdate) -> ImaAccount:
    entity = account_repo.get(db, account_id)
    if not entity:
        raise ValueError("ima 账号不存在")
    data = _normalize_account_payload(payload)
    if data.get("is_default"):
        account_repo.clear_default(db)
    updated = account_repo.update(db, entity=entity, obj_in=data)
    _sync_default_account_setting(db, updated if updated.is_default else None)
    return updated


def delete_account(db: Session, account_id: int) -> None:
    entity = account_repo.get(db, account_id)
    if not entity:
        raise ValueError("ima 账号不存在")
    if db.query(Job).filter(Job.ima_account_id == account_id).first():
        raise ValueError("该 ima 账号已被群聊日报作业使用，不能删除")
    if db.query(ImaSyncJob).filter(ImaSyncJob.ima_account_id == account_id).first():
        raise ValueError("该 ima 账号已被 ima 同步作业使用，不能删除")
    account_repo.delete(db, entity=entity)
    db.flush()
    _sync_default_account_setting(db, None)


async def test_connection(
    db: Session,
    preview: Optional[ImaCredentialPreview] = None,
    *,
    account_id: Optional[int] = None,
) -> str:
    client = _build_client(db, preview=preview, account_id=account_id)
    success_parts: List[str] = []
    failed_parts: List[str] = []

    try:
        folders = await client.list_note_folders()
    except Exception as exc:
        failed_parts.append(f"笔记接口不可用：{exc}")
    else:
        success_parts.append(f"{len(folders)} 个笔记本")

    try:
        knowledge_bases = await client.list_knowledge_bases()
    except Exception as exc:
        failed_parts.append(f"知识库接口不可用：{exc}")
    else:
        success_parts.append(f"{len(knowledge_bases)} 个知识库")

    if success_parts:
        message = f"连接成功，已读取到 {'，'.join(success_parts)}"
        if failed_parts:
            message = f"{message}。另外：{'；'.join(failed_parts)}"
        return message

    raise ValueError("；".join(failed_parts) or "ima 连接失败")


async def test_account_connection(db: Session, account_id: int) -> str:
    account = _require_account(db, account_id)
    try:
        message = await test_connection(db, account_id=account.id)
    except Exception as exc:
        account_repo.update(
            db,
            entity=account,
            obj_in={
                "last_test_at": datetime.utcnow(),
                "last_test_status": "failed",
                "last_test_message": str(exc),
            },
        )
        raise
    account_repo.update(
        db,
        entity=account,
        obj_in={
            "last_test_at": datetime.utcnow(),
            "last_test_status": "success",
            "last_test_message": message,
        },
    )
    return message


async def list_note_folder_options(
    db: Session,
    *,
    account_id: Optional[int] = None,
    preview: Optional[ImaCredentialPreview] = None,
) -> List[ImaOption]:
    client = _build_client(db, preview=preview, account_id=account_id)
    folders = await client.list_note_folders()
    options: List[ImaOption] = []
    for item in folders:
        folder_id = item.get("folder_id")
        name = item.get("name")
        if folder_id and name:
            options.append(ImaOption(label=str(name), value=str(folder_id)))
    return options


async def list_knowledge_base_options(
    db: Session,
    *,
    account_id: Optional[int] = None,
    preview: Optional[ImaCredentialPreview] = None,
) -> List[ImaOption]:
    client = _build_client(db, preview=preview, account_id=account_id)
    items = await client.list_knowledge_bases()
    return [
        ImaOption(label=str(item.get("name")), value=str(item.get("id")))
        for item in items
        if item.get("id") and item.get("name")
    ]


async def list_knowledge_folder_options(
    db: Session,
    knowledge_base_id: str,
    *,
    account_id: Optional[int] = None,
    preview: Optional[ImaCredentialPreview] = None,
    force_refresh: bool = False,
) -> List[ImaFolderOption]:
    cache_key: Optional[tuple[int, str]] = None
    if preview is None:
        resolved_account_id = account_id if account_id is not None else _resolve_default_account(db).id
        cache_key = (resolved_account_id, knowledge_base_id)
        if not force_refresh:
            cached = _knowledge_folder_cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) <= _KNOWLEDGE_FOLDER_CACHE_TTL_SECONDS:
                return [ImaFolderOption(label=item["label"], value=item["value"]) for item in cached[1]]

    client = _build_client(db, preview=preview, account_id=account_id)
    items = await client.list_knowledge_folders(knowledge_base_id)
    options = [ImaFolderOption(label=item["label"], value=item["value"]) for item in items]
    if cache_key is not None:
        _knowledge_folder_cache[cache_key] = (
            time.monotonic(),
            [{"label": item.label, "value": item.value} for item in options],
        )
    return options


def list_sync_jobs(db: Session, *, next_run_lookup=None) -> List[ImaSyncJobOut]:
    items = sync_job_repo.list_all(db)
    return [
        _sync_job_to_schema(item, next_run_at=next_run_lookup(item.id) if next_run_lookup else None)
        for item in items
    ]


def get_sync_job(db: Session, sync_job_id: int, *, next_run_lookup=None) -> Optional[ImaSyncJobOut]:
    entity = sync_job_repo.get(db, sync_job_id)
    if not entity:
        return None
    next_run_at = next_run_lookup(sync_job_id) if next_run_lookup else None
    return _sync_job_to_schema(entity, next_run_at=next_run_at)


def create_sync_job(db: Session, payload: ImaSyncJobCreate) -> ImaSyncJob:
    data = _normalize_sync_job_payload(payload)
    _require_account(db, data.get("ima_account_id"))
    return sync_job_repo.create(db, obj_in=data)


def update_sync_job(db: Session, sync_job_id: int, payload: ImaSyncJobUpdate) -> ImaSyncJob:
    entity = sync_job_repo.get(db, sync_job_id)
    if not entity:
        raise ValueError("ima 同步作业不存在")
    data = _normalize_sync_job_payload(payload)
    _require_account(db, data.get("ima_account_id"))
    return sync_job_repo.update(db, entity=entity, obj_in=data)


def delete_sync_job(db: Session, sync_job_id: int) -> None:
    entity = sync_job_repo.get(db, sync_job_id)
    if not entity:
        raise ValueError("ima 同步作业不存在")
    sync_job_repo.delete(db, entity=entity)
    db.flush()


async def run_sync_job_once(db: Session, sync_job_id: int, *, trigger_type: str) -> ImaManualSyncResult:
    entity = sync_job_repo.get(db, sync_job_id)
    if not entity:
        raise ValueError("ima 同步作业不存在")
    summary = await _run_sync_job(db, sync_job=entity, trigger_type=trigger_type)
    return ImaManualSyncResult(
        batch_id=summary.batch_id,
        scanned_count=summary.scanned_count,
        success_count=summary.success_count,
        skipped_count=summary.skipped_count,
        failed_count=summary.failed_count,
        message=summary.message,
    )


def list_enabled_sync_jobs(db: Session) -> List[ImaSyncJob]:
    return sync_job_repo.list_enabled(db)


def list_records_paginated(
    db: Session,
    *,
    page: int,
    page_size: int,
    ima_account_id: Optional[int] = None,
    task_id: Optional[int] = None,
    job_id: Optional[int] = None,
    sync_job_id: Optional[int] = None,
    sync_scope: Optional[str] = None,
    status: Optional[str] = None,
    trigger_type: Optional[str] = None,
    execution_id: Optional[int] = None,
    batch_id: Optional[str] = None,
    query: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    total, items = record_repo.list_paginated(
        db,
        page=page,
        page_size=page_size,
        ima_account_id=ima_account_id,
        task_id=task_id,
        job_id=job_id,
        sync_job_id=sync_job_id,
        sync_scope=sync_scope,
        status=status,
        trigger_type=trigger_type,
        execution_id=execution_id,
        batch_id=batch_id,
        query=query,
        start_time=start_time,
        end_time=end_time,
    )
    return {
        "items": [_record_to_schema(item).model_dump() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_batch_summaries_paginated(
    db: Session,
    *,
    page: int,
    page_size: int,
    ima_account_id: Optional[int] = None,
    task_id: Optional[int] = None,
    job_id: Optional[int] = None,
    sync_job_id: Optional[int] = None,
    sync_scope: Optional[str] = None,
    status: Optional[str] = None,
    trigger_type: Optional[str] = None,
    execution_id: Optional[int] = None,
    batch_id: Optional[str] = None,
    query: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    records = record_repo.list_all_filtered(
        db,
        ima_account_id=ima_account_id,
        task_id=task_id,
        job_id=job_id,
        sync_job_id=sync_job_id,
        sync_scope=sync_scope,
        status=status,
        trigger_type=trigger_type,
        execution_id=execution_id,
        batch_id=batch_id,
        query=query,
        start_time=start_time,
        end_time=end_time,
    )
    summaries = _build_batch_summaries(records)
    total = len(summaries)
    start_idx = max(page - 1, 0) * page_size
    end_idx = start_idx + page_size
    return {
        "items": [item.model_dump() for item in summaries[start_idx:end_idx]],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def list_batch_records(db: Session, batch_id: str) -> List[ImaSyncRecordOut]:
    items = record_repo.list_by_batch(db, batch_id)
    return [_record_to_schema(item) for item in items]


async def run_manual_directory_sync(db: Session) -> ImaManualSyncResult:
    settings_entity = get_settings_entity(db)
    summary = await _run_directory_sync(
        db,
        settings_entity=settings_entity,
        trigger_type="manual",
    )
    return ImaManualSyncResult(
        batch_id=summary.batch_id,
        scanned_count=summary.scanned_count,
        success_count=summary.success_count,
        skipped_count=summary.skipped_count,
        failed_count=summary.failed_count,
        message=summary.message,
    )


async def run_auto_directory_sync(db: Session) -> Optional[SyncSummary]:
    settings_entity = get_settings_entity(db)
    if not settings_entity.auto_sync_enabled:
        return None
    return await _run_directory_sync(db, settings_entity=settings_entity, trigger_type="auto")


async def run_auto_sync_job(db: Session, sync_job_id: int) -> Optional[SyncSummary]:
    entity = sync_job_repo.get(db, sync_job_id)
    if not entity or not entity.is_enabled:
        return None
    return await _run_sync_job(db, sync_job=entity, trigger_type="auto")


async def sync_execution_outputs(
    db: Session,
    *,
    task,
    job: Job,
    execution: Execution,
    file_paths: Iterable[str],
) -> None:
    if not getattr(job, "ima_sync_enabled", False):
        execution.ima_sync_status = "none"
        execution.ima_sync_error = None
        execution.ima_sync_batch_id = None
        db.add(execution)
        db.flush()
        return
    try:
        settings_entity = get_settings_entity(db)
        account = _resolve_job_account(db, job=job, settings_entity=settings_entity)
        client = _build_client(db, account=account)
        batch_id = uuid4().hex
        target = _resolve_job_target(settings_entity, account=account, job=job)
        summary = SyncSummary(batch_id=batch_id)
        for raw_path in file_paths:
            path = Path(raw_path)
            if not path.exists():
                continue
            summary.scanned_count += 1
            record = await _sync_single_file(
                db,
                client=client,
                batch_id=batch_id,
                trigger_type="job",
                source_type="job_model_output",
                path=path,
                task_id=task.id if task else None,
                job_id=job.id,
                execution_id=execution.id,
                sync_job_id=None,
                account=account,
                target=target,
            )
            _apply_summary(summary, record)
        execution.ima_sync_batch_id = batch_id
        execution.ima_sync_status = summary.status
        execution.ima_sync_error = None if summary.status != "failed" else summary.message
    except Exception as exc:  # pragma: no cover - keep main flow safe
        logger.exception("IMA 同步失败 execution_id=%s", execution.id)
        execution.ima_sync_status = "failed"
        execution.ima_sync_error = str(exc)
    finally:
        db.add(execution)
        db.flush()


async def _run_directory_sync(
    db: Session,
    *,
    settings_entity: ImaSyncSetting,
    trigger_type: str,
) -> SyncSummary:
    account = _resolve_default_account(db, settings_entity=settings_entity)
    client = _build_client(db, account=account)
    target = _resolve_legacy_directory_target(settings_entity, account=account)
    root_path = _resolve_sync_path(settings_entity.local_sync_path)
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError("本地同步路径不存在或不是目录")
    batch_id = uuid4().hex
    summary = SyncSummary(batch_id=batch_id)
    allowed = set(_load_json(settings_entity.allowed_extensions, default=["md", "txt"]) or ["md", "txt"])
    files = _scan_files(root_path, recursive=bool(settings_entity.recursive_enabled), allowed_extensions=allowed)
    for path in files:
        summary.scanned_count += 1
        record = await _sync_single_file(
            db,
            client=client,
            batch_id=batch_id,
            trigger_type=trigger_type,
            source_type="local_directory",
            path=path,
            task_id=None,
            job_id=None,
            execution_id=None,
            sync_job_id=None,
            account=account,
            target=target,
            root_path=root_path,
        )
        _apply_summary(summary, record)
    setting_repo.update_settings(
        db,
        entity=settings_entity,
        obj_in={
            "last_sync_at": datetime.utcnow(),
            "last_sync_status": summary.status,
            "last_sync_summary": summary.message,
        },
    )
    db.flush()
    return summary


async def _run_sync_job(
    db: Session,
    *,
    sync_job: ImaSyncJob,
    trigger_type: str,
) -> SyncSummary:
    account = _resolve_sync_job_account(db, sync_job)
    client = _build_client(db, account=account)
    target = _resolve_sync_job_target(sync_job)
    root_path = _resolve_sync_path(sync_job.local_sync_path)
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError("本地同步路径不存在或不是目录")

    batch_id = uuid4().hex
    summary = SyncSummary(batch_id=batch_id)
    allowed = set(_load_json(sync_job.allowed_extensions, default=["md", "txt"]) or ["md", "txt"])
    files = _scan_files(root_path, recursive=bool(sync_job.recursive_enabled), allowed_extensions=allowed)
    for path in files:
        summary.scanned_count += 1
        record = await _sync_single_file(
            db,
            client=client,
            batch_id=batch_id,
            trigger_type=trigger_type,
            source_type="ima_sync_job",
            path=path,
            task_id=None,
            job_id=None,
            execution_id=None,
            sync_job_id=sync_job.id,
            account=account,
            target=target,
            root_path=root_path,
        )
        _apply_summary(summary, record)

    sync_job_repo.update(
        db,
        entity=sync_job,
        obj_in={
            "last_sync_at": datetime.utcnow(),
            "last_sync_status": summary.status,
            "last_sync_summary": summary.message,
        },
    )
    db.flush()

    if trigger_type == "auto" and sync_job.webhook_id and summary.failed_count:
        await _notify_sync_job_webhook(db, sync_job=sync_job, summary=summary, target=target)
    return summary


async def _sync_single_file(
    db: Session,
    *,
    client: ImaClient,
    batch_id: str,
    trigger_type: str,
    source_type: str,
    path: Path,
    task_id: Optional[int],
    job_id: Optional[int],
    execution_id: Optional[int],
    sync_job_id: Optional[int],
    account: ImaAccount,
    target: ImaTarget,
    root_path: Optional[Path] = None,
) -> ImaSyncRecord:
    suffix = path.suffix.lower().lstrip(".")
    if suffix not in SUPPORTED_FILE_TYPES:
        return _create_record(
            db,
            batch_id=batch_id,
            trigger_type=trigger_type,
            source_type=source_type,
            path=path,
            source_path=_render_source_path(path, root_path),
            task_id=task_id,
            job_id=job_id,
            execution_id=execution_id,
            sync_job_id=sync_job_id,
            account=account,
            target=target,
            status="failed",
            error_message=f"暂不支持的文件类型：.{suffix}",
        )
    try:
        if target.target_type == "knowledge_base":
            meta = SUPPORTED_FILE_TYPES[suffix]
            is_duplicate = await client.check_kb_duplicate(
                knowledge_base_id=target.knowledge_base_id or "",
                file_name=path.name,
                media_type=int(meta["media_type"]),
                folder_id=target.knowledge_folder_id or None,
            )
            if is_duplicate:
                return _create_record(
                    db,
                    batch_id=batch_id,
                    trigger_type=trigger_type,
                    source_type=source_type,
                    path=path,
                    source_path=_render_source_path(path, root_path),
                    task_id=task_id,
                    job_id=job_id,
                    execution_id=execution_id,
                    sync_job_id=sync_job_id,
                    account=account,
                    target=target,
                    status="skipped",
                    skip_reason="duplicate",
                )
            media_id = await client.upload_file_to_kb(
                file_path=path,
                target=target,
                media_type=int(meta["media_type"]),
                content_type=str(meta["content_type"]),
                file_ext=suffix,
            )
            return _create_record(
                db,
                batch_id=batch_id,
                trigger_type=trigger_type,
                source_type=source_type,
                path=path,
                source_path=_render_source_path(path, root_path),
                task_id=task_id,
                job_id=job_id,
                execution_id=execution_id,
                sync_job_id=sync_job_id,
                account=account,
                target=target,
                status="success",
                remote_media_id=media_id,
            )
        duplicate_note = await client.search_note_by_title(path.stem, target.note_folder_id)
        if duplicate_note:
            return _create_record(
                db,
                batch_id=batch_id,
                trigger_type=trigger_type,
                source_type=source_type,
                path=path,
                source_path=_render_source_path(path, root_path),
                task_id=task_id,
                job_id=job_id,
                execution_id=execution_id,
                sync_job_id=sync_job_id,
                account=account,
                target=target,
                status="skipped",
                skip_reason="duplicate",
            )
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            return _create_record(
                db,
                batch_id=batch_id,
                trigger_type=trigger_type,
                source_type=source_type,
                path=path,
                source_path=_render_source_path(path, root_path),
                task_id=task_id,
                job_id=job_id,
                execution_id=execution_id,
                sync_job_id=sync_job_id,
                account=account,
                target=target,
                status="failed",
                error_message=f"文件不是合法 UTF-8，无法同步到 ima 笔记：{exc}",
            )
        doc_id = await client.import_note(title=path.stem, content=content, folder_id=target.note_folder_id)
        return _create_record(
            db,
            batch_id=batch_id,
            trigger_type=trigger_type,
            source_type=source_type,
            path=path,
            source_path=_render_source_path(path, root_path),
            task_id=task_id,
            job_id=job_id,
            execution_id=execution_id,
            sync_job_id=sync_job_id,
            account=account,
            target=target,
            status="success",
            remote_doc_id=doc_id,
        )
    except ImaApiError as exc:
        return _create_record(
            db,
            batch_id=batch_id,
            trigger_type=trigger_type,
            source_type=source_type,
            path=path,
            source_path=_render_source_path(path, root_path),
            task_id=task_id,
            job_id=job_id,
            execution_id=execution_id,
            sync_job_id=sync_job_id,
            account=account,
            target=target,
            status="failed",
            error_code=exc.code,
            error_explanation=exc.explanation,
            error_message=exc.message,
        )
    except Exception as exc:
        logger.exception("IMA 单文件同步失败 path={}", path)
        return _create_record(
            db,
            batch_id=batch_id,
            trigger_type=trigger_type,
            source_type=source_type,
            path=path,
            source_path=_render_source_path(path, root_path),
            task_id=task_id,
            job_id=job_id,
            execution_id=execution_id,
            sync_job_id=sync_job_id,
            account=account,
            target=target,
            status="failed",
            error_message=str(exc),
        )


def _create_record(
    db: Session,
    *,
    batch_id: str,
    trigger_type: str,
    source_type: str,
    path: Path,
    source_path: str,
    task_id: Optional[int],
    job_id: Optional[int],
    execution_id: Optional[int],
    sync_job_id: Optional[int],
    account: ImaAccount,
    target: ImaTarget,
    status: str,
    skip_reason: Optional[str] = None,
    error_code: Optional[int] = None,
    error_explanation: Optional[str] = None,
    error_message: Optional[str] = None,
    remote_doc_id: Optional[str] = None,
    remote_media_id: Optional[str] = None,
) -> ImaSyncRecord:
    stat = path.stat()
    record = record_repo.create(
        db,
        obj_in={
            "batch_id": batch_id,
            "trigger_type": trigger_type,
            "source_type": source_type,
            "source_path": str(path.resolve()),
            "source_name": path.name,
            "source_size": stat.st_size,
            "source_mtime": datetime.fromtimestamp(stat.st_mtime),
            "ima_account_id": account.id,
            "ima_account_name": account.name,
            "sync_job_id": sync_job_id,
            "task_id": task_id,
            "job_id": job_id,
            "execution_id": execution_id,
            "target_type": target.target_type,
            "note_folder_id": target.note_folder_id,
            "note_folder_name": target.note_folder_name,
            "knowledge_base_id": target.knowledge_base_id,
            "knowledge_base_name": target.knowledge_base_name,
            "knowledge_folder_id": target.knowledge_folder_id,
            "knowledge_folder_name": target.knowledge_folder_name,
            "status": status,
            "skip_reason": skip_reason,
            "error_code": error_code,
            "error_explanation": error_explanation,
            "error_message": error_message,
            "remote_doc_id": remote_doc_id,
            "remote_media_id": remote_media_id,
        },
    )
    logger.info(
        "IMA 记录 batch={} status={} source={} target={} display={}",
        batch_id,
        status,
        path,
        target.target_type,
        source_path,
    )
    return record


def _resolve_job_target(settings_entity: ImaSyncSetting, *, account: ImaAccount, job: Job) -> ImaTarget:
    use_default = bool(getattr(job, "ima_use_default_target", True))
    if use_default:
        return _resolve_account_default_target(account)
    target_type = getattr(job, "ima_target_type", None) or account.default_target_type or "knowledge_base"
    if target_type == "note":
        return ImaTarget(
            target_type="note",
            note_folder_id=getattr(job, "ima_note_folder_id", None),
            note_folder_name=getattr(job, "ima_note_folder_name", None),
        )
    knowledge_base_id = getattr(job, "ima_knowledge_base_id", None)
    if not knowledge_base_id:
        raise ValueError("未配置 ima 知识库")
    knowledge_folder_name = getattr(job, "ima_knowledge_folder_name", None) or "根目录"
    return ImaTarget(
        target_type="knowledge_base",
        knowledge_base_id=knowledge_base_id,
        knowledge_base_name=getattr(job, "ima_knowledge_base_name", None),
        knowledge_folder_id=getattr(job, "ima_knowledge_folder_id", None),
        knowledge_folder_name=knowledge_folder_name,
    )


def _resolve_account_default_target(account: ImaAccount) -> ImaTarget:
    target_type = account.default_target_type or "knowledge_base"
    if target_type == "note":
        if not account.default_note_folder_id:
            raise ValueError("该 ima 账号未配置默认笔记本")
        return ImaTarget(
            target_type="note",
            note_folder_id=account.default_note_folder_id,
            note_folder_name=account.default_note_folder_name,
        )
    if not account.default_knowledge_base_id:
        raise ValueError("该 ima 账号未配置默认知识库")
    return ImaTarget(
        target_type="knowledge_base",
        knowledge_base_id=account.default_knowledge_base_id,
        knowledge_base_name=account.default_knowledge_base_name,
        knowledge_folder_id=account.default_knowledge_folder_id,
        knowledge_folder_name=account.default_knowledge_folder_name or "根目录",
    )


def _resolve_legacy_directory_target(settings_entity: ImaSyncSetting, *, account: ImaAccount) -> ImaTarget:
    target_type = settings_entity.default_target_type or account.default_target_type or "knowledge_base"
    if target_type == "note":
        note_folder_id = settings_entity.default_note_folder_id or account.default_note_folder_id
        note_folder_name = settings_entity.default_note_folder_name or account.default_note_folder_name
        if not note_folder_id:
            raise ValueError("未配置默认 ima 笔记本")
        return ImaTarget(target_type="note", note_folder_id=note_folder_id, note_folder_name=note_folder_name)
    knowledge_base_id = settings_entity.default_knowledge_base_id or account.default_knowledge_base_id
    if not knowledge_base_id:
        raise ValueError("未配置默认 ima 知识库")
    return ImaTarget(
        target_type="knowledge_base",
        knowledge_base_id=knowledge_base_id,
        knowledge_base_name=settings_entity.default_knowledge_base_name or account.default_knowledge_base_name,
        knowledge_folder_id=settings_entity.default_knowledge_folder_id or account.default_knowledge_folder_id,
        knowledge_folder_name=(
            settings_entity.default_knowledge_folder_name or account.default_knowledge_folder_name or "根目录"
        ),
    )


def _build_client(
    db: Session,
    preview: Optional[ImaCredentialPreview] = None,
    *,
    account: Optional[ImaAccount] = None,
    account_id: Optional[int] = None,
) -> ImaClient:
    if preview is not None:
        client_id = (preview.client_id or "").strip()
        api_key = (preview.api_key or "").strip()
        if not client_id or not api_key:
            raise ValueError("请先填写 Client ID 和 API Key，再加载 ima 选项")
        return ImaClient(ImaCredentials(client_id=client_id, api_key=api_key))

    if account is None:
        if account_id:
            account = _require_account(db, account_id)
        else:
            account = _resolve_default_account(db)
    client_id = (account.client_id or "").strip()
    api_key = decrypt_value(account.api_key_cipher) if account.api_key_cipher else ""
    if not client_id or not api_key:
        raise ValueError("请先配置 ima Client ID 和 API Key")
    return ImaClient(ImaCredentials(client_id=client_id, api_key=api_key))


def _mask_client_id(value: str) -> str:
    trimmed = (value or "").strip()
    if len(trimmed) <= 8:
        return trimmed
    return f"{trimmed[:4]}...{trimmed[-4:]}"


def _normalize_account_payload(payload: ImaAccountCreate | ImaAccountUpdate) -> dict:
    data = payload.model_dump()
    data["name"] = (data.get("name") or "").strip()
    data["client_id"] = (data.get("client_id") or "").strip()
    api_key = (data.pop("api_key", "") or "").strip()
    if not data["name"]:
        raise ValueError("请输入账号名称")
    if not data["client_id"] or not api_key:
        raise ValueError("请输入 Client ID 和 API Key")
    if data.get("default_target_type") == "note":
        data["default_knowledge_base_id"] = None
        data["default_knowledge_base_name"] = None
        data["default_knowledge_folder_id"] = None
        data["default_knowledge_folder_name"] = None
    else:
        if data.get("default_knowledge_folder_id") == "root":
            data["default_knowledge_folder_id"] = None
            data["default_knowledge_folder_name"] = "根目录"
        data["default_note_folder_id"] = None
        data["default_note_folder_name"] = None
    data["api_key_cipher"] = encrypt_value(api_key)
    return data


def _account_to_schema(entity: ImaAccount) -> ImaAccountOut:
    return ImaAccountOut.model_validate(
        {
            "id": entity.id,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
            "name": entity.name,
            "client_id": entity.client_id,
            "api_key": decrypt_value(entity.api_key_cipher) if entity.api_key_cipher else "",
            "client_id_masked": _mask_client_id(entity.client_id),
            "is_enabled": bool(entity.is_enabled),
            "is_default": bool(entity.is_default),
            "remark": entity.remark,
            "default_target_type": entity.default_target_type or "knowledge_base",
            "default_note_folder_id": entity.default_note_folder_id,
            "default_note_folder_name": entity.default_note_folder_name,
            "default_knowledge_base_id": entity.default_knowledge_base_id,
            "default_knowledge_base_name": entity.default_knowledge_base_name,
            "default_knowledge_folder_id": entity.default_knowledge_folder_id,
            "default_knowledge_folder_name": entity.default_knowledge_folder_name,
            "last_test_at": entity.last_test_at,
            "last_test_status": entity.last_test_status,
            "last_test_message": entity.last_test_message,
        }
    )


def _sync_default_account_setting(db: Session, default_account: Optional[ImaAccount]) -> None:
    entity = get_settings_entity(db)
    setting_repo.update_settings(
        db,
        entity=entity,
        obj_in={"default_account_id": default_account.id if default_account else None},
    )


def _ensure_legacy_account_migrated(db: Session) -> Optional[ImaAccount]:
    existing = account_repo.list_all(db)
    if existing:
        return None
    entity = get_settings_entity(db)
    client_id = (entity.client_id or "").strip()
    api_key = decrypt_value(entity.api_key_cipher) if entity.api_key_cipher else ""
    if not client_id or not api_key:
        return None
    account = account_repo.create(
        db,
        obj_in={
            "name": "默认ima账号",
            "client_id": client_id,
            "api_key_cipher": encrypt_value(api_key),
            "is_enabled": True,
            "is_default": True,
            "remark": "由历史单账号配置自动迁移",
            "default_target_type": entity.default_target_type or "knowledge_base",
            "default_note_folder_id": entity.default_note_folder_id,
            "default_note_folder_name": entity.default_note_folder_name,
            "default_knowledge_base_id": entity.default_knowledge_base_id,
            "default_knowledge_base_name": entity.default_knowledge_base_name,
            "default_knowledge_folder_id": entity.default_knowledge_folder_id,
            "default_knowledge_folder_name": entity.default_knowledge_folder_name,
        },
    )
    _sync_default_account_setting(db, account)
    return account


def _ensure_default_account_pointer(db: Session) -> Optional[ImaAccount]:
    migrated = _ensure_legacy_account_migrated(db)
    if migrated:
        return migrated
    entity = get_settings_entity(db)
    if entity.default_account_id:
        account = account_repo.get(db, entity.default_account_id)
        if account:
            if not account.is_default:
                account_repo.clear_default(db)
                account_repo.update(db, entity=account, obj_in={"is_default": True})
            return account
    account = account_repo.get_default(db)
    if account:
        _sync_default_account_setting(db, account)
        return account
    first = next(iter(account_repo.list_all(db)), None)
    if first:
        account_repo.update(db, entity=first, obj_in={"is_default": True})
        _sync_default_account_setting(db, first)
        return first
    return None


def _require_account(db: Session, account_id: Optional[int]) -> ImaAccount:
    if not account_id:
        raise ValueError("请选择 ima 账号")
    account = account_repo.get(db, account_id)
    if not account:
        raise ValueError("ima 账号不存在")
    if not account.is_enabled:
        raise ValueError("所选 ima 账号已停用")
    return account


def _resolve_default_account(db: Session, *, settings_entity: Optional[ImaSyncSetting] = None) -> ImaAccount:
    account = _ensure_default_account_pointer(db)
    if not account:
        raise ValueError("请先在 ima账号管理 中配置至少一个可用账号")
    if not account.is_enabled:
        raise ValueError("默认 ima 账号已停用")
    return account


def _resolve_job_account(db: Session, *, job: Job, settings_entity: Optional[ImaSyncSetting] = None) -> ImaAccount:
    if bool(getattr(job, "ima_use_default_account", True)):
        return _resolve_default_account(db, settings_entity=settings_entity)
    return _require_account(db, getattr(job, "ima_account_id", None))


def _resolve_sync_job_account(db: Session, sync_job: ImaSyncJob) -> ImaAccount:
    if getattr(sync_job, "ima_account_id", None):
        return _require_account(db, sync_job.ima_account_id)
    return _resolve_default_account(db)


def _scan_files(root: Path, *, recursive: bool, allowed_extensions: set[str]) -> List[Path]:
    pattern = "**/*" if recursive else "*"
    results: List[Path] = []
    for candidate in root.glob(pattern):
        if not candidate.is_file():
            continue
        suffix = candidate.suffix.lower().lstrip(".")
        if suffix in allowed_extensions:
            results.append(candidate)
    return sorted(results, key=lambda item: str(item).lower())


def _resolve_sync_path(raw_path: Optional[str]) -> Path:
    if not raw_path:
        raise ValueError("请先配置本地同步路径")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = Path(settings.local_backup_dir).expanduser().resolve() / path
    return path.resolve()


def _apply_summary(summary: SyncSummary, record: ImaSyncRecord) -> None:
    if record.status == "success":
        summary.success_count += 1
    elif record.status == "skipped":
        summary.skipped_count += 1
    elif record.status == "failed":
        summary.failed_count += 1


def _sync_job_to_schema(entity: ImaSyncJob, *, next_run_at: Optional[datetime] = None) -> ImaSyncJobOut:
    allowed_extensions = _load_json(entity.allowed_extensions, default=["md", "txt"]) or ["md", "txt"]
    return ImaSyncJobOut.model_validate(
        {
            "id": entity.id,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
            "name": entity.name,
            "is_enabled": bool(entity.is_enabled),
            "ima_account_id": entity.ima_account_id,
            "ima_account_name": entity.ima_account.name if getattr(entity, "ima_account", None) else None,
            "target_type": entity.target_type,
            "note_folder_id": entity.note_folder_id,
            "note_folder_name": entity.note_folder_name,
            "knowledge_base_id": entity.knowledge_base_id,
            "knowledge_base_name": entity.knowledge_base_name,
            "knowledge_folder_id": entity.knowledge_folder_id,
            "knowledge_folder_name": entity.knowledge_folder_name,
            "local_sync_path": entity.local_sync_path,
            "recursive_enabled": bool(entity.recursive_enabled),
            "allowed_extensions": allowed_extensions,
            "schedule_frequency": entity.schedule_frequency or "daily",
            "schedule_weekday": entity.schedule_weekday or 0,
            "schedule_time": entity.schedule_time or "08:00",
            "webhook_id": entity.webhook_id,
            "webhook_name": entity.webhook.name if entity.webhook else None,
            "last_sync_at": entity.last_sync_at,
            "last_sync_status": entity.last_sync_status,
            "last_sync_summary": entity.last_sync_summary,
            "next_run_at": next_run_at,
        }
    )


def _normalize_sync_job_payload(payload: ImaSyncJobCreate | ImaSyncJobUpdate) -> dict:
    data = payload.model_dump()
    target_type = data.get("target_type") or "knowledge_base"
    data["name"] = (data.get("name") or "").strip()
    data["local_sync_path"] = (data.get("local_sync_path") or "").strip()
    data["schedule_time"] = ((data.get("schedule_time") or "").strip() or "08:00")
    if data.get("allowed_extensions") is not None:
        data["allowed_extensions"] = json.dumps(data["allowed_extensions"], ensure_ascii=False)

    if target_type == "note":
        data["knowledge_base_id"] = None
        data["knowledge_base_name"] = None
        data["knowledge_folder_id"] = None
        data["knowledge_folder_name"] = None
    else:
        if data.get("knowledge_folder_id") == "root":
            data["knowledge_folder_id"] = None
            data["knowledge_folder_name"] = "根目录"
        data["note_folder_id"] = None
        data["note_folder_name"] = None
    return data


def _resolve_sync_job_target(sync_job: ImaSyncJob) -> ImaTarget:
    if sync_job.target_type == "note":
        return ImaTarget(
            target_type="note",
            note_folder_id=sync_job.note_folder_id,
            note_folder_name=sync_job.note_folder_name,
        )
    if not sync_job.knowledge_base_id:
        raise ValueError("未配置 ima 知识库")
    return ImaTarget(
        target_type="knowledge_base",
        knowledge_base_id=sync_job.knowledge_base_id,
        knowledge_base_name=sync_job.knowledge_base_name,
        knowledge_folder_id=sync_job.knowledge_folder_id,
        knowledge_folder_name=sync_job.knowledge_folder_name or "根目录",
    )


async def _notify_sync_job_webhook(
    db: Session,
    *,
    sync_job: ImaSyncJob,
    summary: SyncSummary,
    target: ImaTarget,
) -> None:
    webhook = webhook_repo.get(db, sync_job.webhook_id)
    if not webhook:
        return
    target_display = (
        sync_job.note_folder_name or "ima 笔记"
        if target.target_type == "note"
        else f"{sync_job.knowledge_base_name or '-'} / {sync_job.knowledge_folder_name or '根目录'}"
    )
    content = "\n".join(
        [
            f"**同步作业**：{sync_job.name}",
            f"**本地目录**：{sync_job.local_sync_path}",
            f"**同步目标**：{target_display}",
            f"**结果摘要**：{summary.message}",
        ]
    )
    await feishu.send_markdown(
        webhook,
        title="ima 自动同步告警",
        subtitle="自动同步出现失败文件",
        content=content,
        template=webhook.card_header_color or "red",
    )


def _record_sync_scope(record: ImaSyncRecord) -> str:
    if getattr(record, "sync_job_id", None):
        return "ima_sync_job"
    return "daily_report_job"


def _build_batch_summaries(records: List[ImaSyncRecord]) -> List[ImaSyncBatchOut]:
    grouped: dict[str, List[ImaSyncRecord]] = {}
    ordered_batch_ids: List[str] = []
    for record in records:
        if not record.batch_id:
            continue
        if record.batch_id not in grouped:
            grouped[record.batch_id] = []
            ordered_batch_ids.append(record.batch_id)
        grouped[record.batch_id].append(record)

    summaries: List[ImaSyncBatchOut] = []
    for batch_id in ordered_batch_ids:
        items = grouped[batch_id]
        first = items[0]
        success_count = sum(1 for item in items if item.status == "success")
        skipped_count = sum(1 for item in items if item.status == "skipped")
        failed_count = sum(1 for item in items if item.status == "failed")
        if failed_count and success_count == 0 and skipped_count == 0:
            status = "failed"
        elif failed_count:
            status = "partial"
        elif success_count:
            status = "success"
        elif skipped_count:
            status = "skipped"
        else:
            status = "none"

        target_display = (
            f"ima 笔记 / {first.note_folder_name or '-'}"
            if first.target_type == "note"
            else f"ima 知识库 / {first.knowledge_base_name or '-'} / {first.knowledge_folder_name or '根目录'}"
        )
        summaries.append(
            ImaSyncBatchOut(
                batch_id=batch_id,
                created_at=first.created_at,
                trigger_type=first.trigger_type,
                sync_scope=_record_sync_scope(first),
                ima_account_id=getattr(first, "ima_account_id", None),
                ima_account_name=(
                    first.ima_account.name if getattr(first, "ima_account", None) else getattr(first, "ima_account_name", None)
                ),
                sync_job_id=getattr(first, "sync_job_id", None),
                sync_job_name=first.sync_job.name if getattr(first, "sync_job", None) else None,
                task_id=first.task_id,
                task_name=first.task.name if getattr(first, "task", None) else None,
                job_id=first.job_id,
                job_name=first.job.name if getattr(first, "job", None) else None,
                execution_id=first.execution_id,
                target_type=first.target_type,
                target_display=target_display,
                total_count=len(items),
                success_count=success_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                status=status,
                summary=(
                    f"共 {len(items)} 个文件，成功 {success_count} 个，跳过 {skipped_count} 个，失败 {failed_count} 个"
                ),
            )
        )
    return summaries


def _record_to_schema(record: ImaSyncRecord) -> ImaSyncRecordOut:
    sync_job = getattr(record, "sync_job", None)
    task = getattr(record, "task", None)
    job = getattr(record, "job", None)
    account = getattr(record, "ima_account", None)
    return ImaSyncRecordOut.model_validate(
        {
            "id": record.id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "batch_id": record.batch_id,
            "trigger_type": record.trigger_type,
            "source_type": record.source_type,
            "source_path": record.source_path,
            "source_name": record.source_name,
            "source_size": record.source_size,
            "source_mtime": record.source_mtime,
            "ima_account_id": record.ima_account_id,
            "ima_account_name": account.name if account else record.ima_account_name,
            "sync_job_id": record.sync_job_id,
            "sync_job_name": sync_job.name if sync_job else None,
            "sync_scope": _record_sync_scope(record),
            "task_id": record.task_id,
            "task_name": task.name if task else None,
            "job_id": record.job_id,
            "job_name": job.name if job else None,
            "execution_id": record.execution_id,
            "target_type": record.target_type,
            "note_folder_id": record.note_folder_id,
            "note_folder_name": record.note_folder_name,
            "knowledge_base_id": record.knowledge_base_id,
            "knowledge_base_name": record.knowledge_base_name,
            "knowledge_folder_id": record.knowledge_folder_id,
            "knowledge_folder_name": record.knowledge_folder_name,
            "status": record.status,
            "skip_reason": record.skip_reason,
            "error_code": record.error_code,
            "error_explanation": record.error_explanation,
            "error_message": record.error_message,
            "remote_doc_id": record.remote_doc_id,
            "remote_media_id": record.remote_media_id,
        }
    )


def _render_source_path(path: Path, root_path: Optional[Path]) -> str:
    if root_path is None:
        return str(path.resolve())
    try:
        return str(path.resolve().relative_to(root_path.resolve()))
    except ValueError:
        return str(path.resolve())
