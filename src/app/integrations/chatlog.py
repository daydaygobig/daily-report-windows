"""Client for interacting with chatlog HTTP API."""

from datetime import datetime
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from ..config import get_settings

settings = get_settings()


def _normalize_time_range(raw: str) -> str:
    """Normalize time range to chatlog-supported date-only format."""

    if not raw:
        return raw

    parts = [part.strip() for part in str(raw).split("~", 1)]

    def _extract_date(value: str) -> str:
        for separator in (" ", "T"):
            if separator in value:
                value = value.split(separator, 1)[0]
        return value

    normalized = [_extract_date(part) for part in parts if part]
    if len(parts) == 2:
        if len(normalized) == 2:
            return "~".join(normalized)
        if normalized:
            return normalized[0]
    return normalized[0] if normalized else raw


async def ensure_decrypted(
    required_until: datetime,
    *,
    buffer_sec: int = 0,
    timeout: Optional[int] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask chatlog to decrypt local DB files until required_until is covered."""

    payload = {
        "required_until": required_until.strftime("%Y-%m-%d %H:%M:%S"),
        "buffer_sec": buffer_sec,
    }
    timeout = timeout or settings.chatlog_decrypt_timeout_sec
    base_url = base_url or settings.chatlog_base_url

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/api/v1/decrypt", json=payload)
        response.raise_for_status()
        return response.json()


async def stream_chatlog(
    talker: str,
    time_range: str,
    *,
    sender: Optional[str] = None,
    keyword: Optional[str] = None,
    timeout: Optional[int] = None,
    base_url: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream chatlog messages as plain text."""

    params: Dict[str, str] = {"talker": talker, "time": _normalize_time_range(time_range), "format": "text"}
    if sender:
        params["sender"] = sender
    if keyword:
        params["keyword"] = keyword

    timeout = timeout or settings.chatlog_timeout_sec
    base_url = base_url or settings.chatlog_base_url

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", f"{base_url}/api/v1/chatlog", params=params) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line
