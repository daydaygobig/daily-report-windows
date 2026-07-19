"""Unified chat record routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..schemas.chat_records import ChatRecordSettingsUpdate
from ..services import chat_record_service
from ..utils.responses import success_response

router = APIRouter(prefix="/chat-records", tags=["chat-records"])


@router.get("/settings", response_model=dict)
def get_settings(db: Session = Depends(get_db)):
    return success_response(chat_record_service.get_settings_view(db).model_dump())


@router.put("/settings", response_model=dict)
async def update_settings(payload: ChatRecordSettingsUpdate, db: Session = Depends(get_db)):
    try:
        view = await chat_record_service.update_settings(db, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": 400, "message": str(exc)}) from exc
    return success_response(view.model_dump())


@router.post("/settings/test", response_model=dict)
async def test_settings(payload: ChatRecordSettingsUpdate | None = None, db: Session = Depends(get_db)):
    try:
        result = await chat_record_service.test_settings(db, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": 400, "message": str(exc)}) from exc
    return success_response(result.model_dump())


@router.get("/status", response_model=dict)
async def status(db: Session = Depends(get_db)):
    result = await chat_record_service.get_status(db)
    return success_response(result.model_dump())


@router.get("/chatrooms", response_model=dict)
async def list_chatrooms(
    keyword: str | None = Query(default=None),
    talkers: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
):
    try:
        chatrooms = await chat_record_service.fetch_chatrooms(keyword=keyword, limit=limit, talkers=talkers)
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"code": 502, "message": str(exc)}) from exc
    return success_response(chatrooms)
