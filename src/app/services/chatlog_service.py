"""Utilities to interact with chatlog service via backend."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import httpx

from ..config import get_settings

settings = get_settings()


class ChatlogError(RuntimeError):
    """Raised when chatlog service interaction fails."""


async def fetch_chatrooms(
    keyword: Optional[str] = None,
    *,
    limit: int = 50,
    talkers: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return chatroom metadata from chatlog service.

    Args:
        keyword: Optional fuzzy keyword to search chatrooms.
        limit: Maximum number of chatrooms to fetch for keyword query.
        talkers: Optional comma-separated chatroom IDs that must appear in the result.
    """

    params: Dict[str, Any] = {"format": "json", "limit": limit}
    if keyword:
        params["keyword"] = keyword

    async with httpx.AsyncClient(timeout=settings.chatlog_timeout_sec) as client:
        response = await client.get(f"{settings.chatlog_base_url}/api/v1/chatroom", params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ChatlogError(f"Chatlog API 错误: {exc.response.status_code}") from exc

        payload = response.json()
        items = payload.get("items", [])
    normalized: Dict[str, Dict[str, Any]] = {}
    for item in items:
        normalized_item = _normalize_chatroom_item(item)
        if normalized_item:
            normalized[normalized_item["name"]] = normalized_item

    talker_ids: Sequence[str] = []
    if talkers:
        talker_ids = [value.strip() for value in talkers.split(",") if value.strip()]

    for talker in talker_ids:
        if talker in normalized:
            continue
        detail = await _fetch_single_chatroom(talker)
        if detail:
            normalized[detail["name"]] = detail
        else:
            normalized[talker] = {
                "name": talker,
                "display_name": talker,
                "owner": None,
                "raw": None,
                "user_count": 0,
            }

    return list(normalized.values())


def _normalize_chatroom_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    name = item.get("name")
    if not name:
        return None
    display = item.get("remark") or item.get("nickName") or item.get("nickname") or name
    return {
        "name": name,
        "display_name": display,
        "owner": item.get("owner"),
        "raw": item,
        "user_count": len(item.get("users") or []),
    }


async def _fetch_single_chatroom(talker: str) -> Optional[Dict[str, Any]]:
    params = {"format": "json", "limit": 20, "keyword": talker}
    async with httpx.AsyncClient(timeout=settings.chatlog_timeout_sec) as client:
        try:
            response = await client.get(f"{settings.chatlog_base_url}/api/v1/chatroom", params=params)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        payload = response.json()
        items = payload.get("items", [])
        if not items:
            return None
        for item in items:
            normalized = _normalize_chatroom_item(item)
            if normalized and normalized["name"] == talker:
                return normalized
        normalized = _normalize_chatroom_item(items[0])
        return normalized
