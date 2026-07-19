"""Chatlog helper routes."""

from fastapi import APIRouter, HTTPException, Query

from ..services.chatlog_service import ChatlogError, fetch_chatrooms
from ..utils.responses import success_response

router = APIRouter(prefix="/chatlog", tags=["chatlog"])


@router.get("/chatrooms", response_model=dict)
async def list_chatrooms(
    keyword: str | None = Query(default=None, description="搜索关键词"),
    talkers: str | None = Query(default=None, description="按群聊ID列表补充结果，逗号分隔"),
    limit: int = Query(default=50, le=200),
):
    try:
        chatrooms = await fetch_chatrooms(keyword=keyword, limit=limit, talkers=talkers)
    except ChatlogError as exc:
        raise HTTPException(status_code=502, detail={"code": 502, "message": str(exc)}) from exc
    return success_response(chatrooms)
