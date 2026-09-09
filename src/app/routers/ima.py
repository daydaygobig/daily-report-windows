"""Routes for IMA sync settings and records."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.orm import Session

from ..errors import AppError, NotFoundError
from ..dependencies import get_db
from ..scheduler.service import scheduler_service
from ..schemas.ima import (
    ImaAccountCreate,
    ImaAccountUpdate,
    ImaCredentialPreview,
    ImaKnowledgeFolderPreview,
    ImaSyncJobCreate,
    ImaSyncJobUpdate,
    ImaSyncSettingsUpdate,
)
from ..services import ima_sync_service
from ..utils.responses import success_response

router = APIRouter(prefix="/ima", tags=["ima"])

_TIME_FMT = "%Y-%m-%d %H:%M"
_PAGE_SIZE_CHOICES = {10, 20, 50, 100}


@router.get("/settings", response_model=dict)
def get_ima_settings(db: Session = Depends(get_db)):
    view = ima_sync_service.get_settings_view(db, next_run_at=scheduler_service.get_ima_auto_sync_next_run())
    return success_response(view.model_dump())


@router.put("/settings", response_model=dict)
def update_ima_settings(payload: ImaSyncSettingsUpdate, db: Session = Depends(get_db)):
    logger.info(
        "保存 IMA 设置 default_account_id={}",
        payload.default_account_id,
    )
    entity = ima_sync_service.update_settings(db, payload)
    db.commit()
    scheduler_service.trigger_reload()
    view = ima_sync_service.get_settings_view(db, next_run_at=scheduler_service.get_ima_auto_sync_next_run())
    logger.info("IMA 设置保存完成 id={}", entity.id)
    return success_response(view.model_dump(), message="ima 设置已保存")


@router.get("/accounts", response_model=dict)
def list_ima_accounts(db: Session = Depends(get_db)):
    items = ima_sync_service.list_accounts(db)
    return success_response([item.model_dump() for item in items])


@router.post("/accounts", response_model=dict)
def create_ima_account(payload: ImaAccountCreate, db: Session = Depends(get_db)):
    try:
        entity = ima_sync_service.create_account(db, payload)
    except ValueError as exc:
        raise AppError(str(exc), code=400) from exc
    db.commit()
    view = ima_sync_service.get_account(db, entity.id)
    return success_response(view.model_dump() if view else None, message="ima 账号已创建")


@router.put("/accounts/{account_id}", response_model=dict)
def update_ima_account(account_id: int, payload: ImaAccountUpdate, db: Session = Depends(get_db)):
    try:
        entity = ima_sync_service.update_account(db, account_id, payload)
    except ValueError as exc:
        raise (NotFoundError(str(exc)) if "不存在" in str(exc) else AppError(str(exc), code=400)) from exc
    db.commit()
    view = ima_sync_service.get_account(db, entity.id)
    return success_response(view.model_dump() if view else None, message="ima 账号已更新")


@router.delete("/accounts/{account_id}", response_model=dict)
def delete_ima_account(account_id: int, db: Session = Depends(get_db)):
    try:
        ima_sync_service.delete_account(db, account_id)
    except ValueError as exc:
        raise AppError(str(exc), code=400) from exc
    db.commit()
    return success_response(message="ima 账号已删除")


@router.post("/accounts/{account_id}/test", response_model=dict)
async def test_ima_account(account_id: int, db: Session = Depends(get_db)):
    try:
        message = await ima_sync_service.test_account_connection(db, account_id)
    except Exception as exc:
        logger.warning("IMA 账号测试失败 account_id={}: {}", account_id, exc)
        db.commit()
        raise AppError(str(exc), code=400) from exc
    db.commit()
    return success_response({"ok": True, "message": message}, message=message)


@router.post("/settings/test", response_model=dict)
async def test_ima_settings(payload: Optional[ImaCredentialPreview] = None, db: Session = Depends(get_db)):
    try:
        message = await ima_sync_service.test_connection(db, preview=payload)
    except Exception as exc:
        logger.warning("IMA 测试连接失败: {}", exc)
        raise AppError(str(exc), code=400) from exc
    return success_response({"ok": True, "message": message}, message=message)


@router.get("/options/note-folders", response_model=dict)
async def get_note_folders(account_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    try:
        options = await ima_sync_service.list_note_folder_options(db, account_id=account_id)
    except Exception as exc:
        logger.warning("IMA 拉取笔记本失败: {}", exc)
        raise AppError(str(exc), code=400) from exc
    return success_response([item.model_dump() for item in options])


@router.post("/options/note-folders/preview", response_model=dict)
async def preview_note_folders(payload: ImaCredentialPreview, db: Session = Depends(get_db)):
    try:
        options = await ima_sync_service.list_note_folder_options(db, preview=payload)
    except Exception as exc:
        logger.warning("IMA 预览拉取笔记本失败: {}", exc)
        raise AppError(str(exc), code=400) from exc
    return success_response([item.model_dump() for item in options])


@router.get("/options/knowledge-bases", response_model=dict)
async def get_knowledge_bases(account_id: Optional[int] = Query(None), db: Session = Depends(get_db)):
    try:
        options = await ima_sync_service.list_knowledge_base_options(db, account_id=account_id)
    except Exception as exc:
        logger.warning("IMA 拉取知识库列表失败: {}", exc)
        raise AppError(str(exc), code=400) from exc
    return success_response([item.model_dump() for item in options])


@router.post("/options/knowledge-bases/preview", response_model=dict)
async def preview_knowledge_bases(payload: ImaCredentialPreview, db: Session = Depends(get_db)):
    try:
        options = await ima_sync_service.list_knowledge_base_options(db, preview=payload)
    except Exception as exc:
        logger.warning("IMA 预览拉取知识库列表失败: {}", exc)
        raise AppError(str(exc), code=400) from exc
    return success_response([item.model_dump() for item in options])


@router.get("/options/knowledge-folders", response_model=dict)
async def get_knowledge_folders(
    knowledge_base_id: str = Query(...),
    account_id: Optional[int] = Query(None),
    force_refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        options = await ima_sync_service.list_knowledge_folder_options(
            db,
            knowledge_base_id,
            account_id=account_id,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        logger.warning("IMA 拉取知识库文件夹失败 knowledge_base_id={}: {}", knowledge_base_id, exc)
        raise AppError(str(exc), code=400) from exc
    return success_response([item.model_dump() for item in options])


@router.post("/options/knowledge-folders/preview", response_model=dict)
async def preview_knowledge_folders(payload: ImaKnowledgeFolderPreview, db: Session = Depends(get_db)):
    try:
        options = await ima_sync_service.list_knowledge_folder_options(
            db,
            payload.knowledge_base_id,
            preview=payload,
        )
    except Exception as exc:
        logger.warning("IMA 预览拉取知识库文件夹失败 knowledge_base_id={}: {}", payload.knowledge_base_id, exc)
        raise AppError(str(exc), code=400) from exc
    return success_response([item.model_dump() for item in options])


@router.post("/manual-sync", response_model=dict)
async def manual_sync(db: Session = Depends(get_db)):
    try:
        result = await ima_sync_service.run_manual_directory_sync(db)
    except Exception as exc:
        logger.warning("IMA 手动同步失败: {}", exc)
        raise AppError(str(exc), code=400) from exc
    db.commit()
    return success_response(result.model_dump(), message=result.message)


@router.get("/sync-jobs", response_model=dict)
def list_sync_jobs(db: Session = Depends(get_db)):
    items = ima_sync_service.list_sync_jobs(db, next_run_lookup=scheduler_service.get_ima_sync_job_next_run)
    return success_response([item.model_dump() for item in items])


@router.post("/sync-jobs", response_model=dict)
def create_sync_job(payload: ImaSyncJobCreate, db: Session = Depends(get_db)):
    entity = ima_sync_service.create_sync_job(db, payload)
    db.commit()
    scheduler_service.trigger_reload()
    view = ima_sync_service.get_sync_job(db, entity.id, next_run_lookup=scheduler_service.get_ima_sync_job_next_run)
    return success_response(view.model_dump() if view else None, message="ima 同步作业已创建")


@router.put("/sync-jobs/{sync_job_id}", response_model=dict)
def update_sync_job(sync_job_id: int, payload: ImaSyncJobUpdate, db: Session = Depends(get_db)):
    try:
        entity = ima_sync_service.update_sync_job(db, sync_job_id, payload)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    db.commit()
    scheduler_service.trigger_reload()
    view = ima_sync_service.get_sync_job(db, entity.id, next_run_lookup=scheduler_service.get_ima_sync_job_next_run)
    return success_response(view.model_dump() if view else None, message="ima 同步作业已更新")


@router.delete("/sync-jobs/{sync_job_id}", response_model=dict)
def delete_sync_job(sync_job_id: int, db: Session = Depends(get_db)):
    try:
        ima_sync_service.delete_sync_job(db, sync_job_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    db.commit()
    scheduler_service.trigger_reload()
    return success_response(message="ima 同步作业已删除")


@router.post("/sync-jobs/{sync_job_id}/run", response_model=dict)
async def run_sync_job(sync_job_id: int, db: Session = Depends(get_db)):
    try:
        result = await ima_sync_service.run_sync_job_once(db, sync_job_id, trigger_type="manual")
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    except Exception as exc:
        logger.warning("IMA 同步作业手动执行失败 sync_job_id={}: {}", sync_job_id, exc)
        raise AppError(str(exc), code=400) from exc
    db.commit()
    return success_response(result.model_dump(), message=result.message)


@router.get("/records/batches", response_model=dict)
def list_ima_record_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
    ima_account_id: Optional[int] = Query(None),
    task_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    sync_job_id: Optional[int] = Query(None),
    sync_scope: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    trigger_type: Optional[str] = Query(None),
    execution_id: Optional[int] = Query(None),
    batch_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if page_size not in _PAGE_SIZE_CHOICES:
        page_size = 50
    start_dt = datetime.strptime(start_time, _TIME_FMT) if start_time else None
    end_dt = datetime.strptime(end_time, _TIME_FMT) if end_time else None
    data = ima_sync_service.list_batch_summaries_paginated(
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
        start_time=start_dt,
        end_time=end_dt,
    )
    return success_response(data)


@router.get("/records/batches/{batch_id}/items", response_model=dict)
def list_ima_batch_items(batch_id: str, db: Session = Depends(get_db)):
    items = ima_sync_service.list_batch_records(db, batch_id)
    return success_response([item.model_dump() for item in items])


@router.get("/records", response_model=dict)
def list_ima_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(50),
    ima_account_id: Optional[int] = Query(None),
    task_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    sync_job_id: Optional[int] = Query(None),
    sync_scope: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    trigger_type: Optional[str] = Query(None),
    execution_id: Optional[int] = Query(None),
    batch_id: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if page_size not in _PAGE_SIZE_CHOICES:
        page_size = 50
    start_dt = datetime.strptime(start_time, _TIME_FMT) if start_time else None
    end_dt = datetime.strptime(end_time, _TIME_FMT) if end_time else None
    data = ima_sync_service.list_records_paginated(
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
        start_time=start_dt,
        end_time=end_dt,
    )
    return success_response(data)
