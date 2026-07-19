"""Unified chat record source service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import session_scope
from ..integrations import chatlog, weflow
from ..integrations.security import decrypt_value, encrypt_value
from ..models.chat_record_setting import ChatRecordSetting
from ..repositories.chat_record_setting_repo import ChatRecordSettingRepository
from ..schemas.chat_records import (
    ChatRecordSettingsOut,
    ChatRecordSettingsUpdate,
    ChatRecordStatus,
    ChatRecordTestResult,
)


class ChatRecordError(RuntimeError):
    """Raised when the active chat record source fails."""


settings = get_settings()
setting_repo = ChatRecordSettingRepository()


def get_settings_entity(db: Session) -> ChatRecordSetting:
    entity = setting_repo.get_singleton(db)
    if entity:
        return entity
    entity = setting_repo.create_default(db)
    db.flush()
    return entity


def get_settings_view(db: Session) -> ChatRecordSettingsOut:
    entity = get_settings_entity(db)
    return _settings_out(entity)


async def update_settings(db: Session, payload: ChatRecordSettingsUpdate) -> ChatRecordSettingsOut:
    entity = get_settings_entity(db)
    data = payload.model_dump()
    token_value = data.pop("weflow_token", None)
    if token_value is not None:
        token_value = token_value.strip()
        data["weflow_token_cipher"] = encrypt_value(token_value) if token_value else None
    elif payload.provider == "weflow" and not entity.weflow_token_cipher and settings.weflow_access_token:
        data["weflow_token_cipher"] = encrypt_value(settings.weflow_access_token)
    data["weflow_include_media"] = False
    await _probe_payload(data, existing=entity)
    updated = setting_repo.update_settings(db, entity=entity, obj_in=data)
    return _settings_out(updated)


async def test_settings(db: Session, payload: Optional[ChatRecordSettingsUpdate] = None) -> ChatRecordTestResult:
    entity = get_settings_entity(db)
    if payload is None:
        status = await get_status(db)
        return ChatRecordTestResult(
            ok=status.status == "ok",
            provider=status.provider,
            status=status.status,
            message=status.message,
        )
    data = payload.model_dump()
    token_value = data.pop("weflow_token", None)
    if token_value is not None:
        token_value = token_value.strip()
        data["weflow_token_cipher"] = encrypt_value(token_value) if token_value else None
    await _probe_payload(data, existing=entity)
    return ChatRecordTestResult(ok=True, provider=payload.provider, status="ok", message="聊天记录接口可用")


async def get_status(db: Session) -> ChatRecordStatus:
    entity = get_settings_entity(db)
    try:
        await _probe_entity(entity)
        return ChatRecordStatus(provider=entity.provider, status="ok", message="聊天记录接口可用")
    except ChatRecordError as exc:
        status = "invalid_token" if "Token" in str(exc) else "unreachable"
        return ChatRecordStatus(provider=entity.provider, status=status, message=str(exc))
    except Exception as exc:
        return ChatRecordStatus(provider=entity.provider, status="unreachable", message=str(exc))


async def fetch_chatrooms(
    keyword: Optional[str] = None,
    *,
    limit: int = 50,
    talkers: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with session_scope() as db:
        entity = get_settings_entity(db)
        runtime = _runtime_from_entity(entity)
    if runtime["provider"] == "weflow":
        return await _fetch_weflow_chatrooms(runtime["weflow"], keyword=keyword, limit=limit, talkers=talkers)
    return await _fetch_chatlog_chatrooms(runtime["chatlog"], keyword=keyword, limit=limit, talkers=talkers)


async def collect_messages(talkers: List[str], time_window: dict, telemetry: Optional[dict] = None) -> str:
    with session_scope() as db:
        entity = get_settings_entity(db)
        runtime = _runtime_from_entity(entity)
    if telemetry is not None:
        telemetry["provider"] = runtime["provider"]
    if runtime["provider"] == "weflow":
        return await _collect_weflow_messages(runtime["weflow"], talkers, time_window)
    return await _collect_chatlog_messages(runtime["chatlog"], talkers, time_window, telemetry=telemetry)


def _settings_out(entity: ChatRecordSetting) -> ChatRecordSettingsOut:
    return ChatRecordSettingsOut.model_validate(
        {
            "id": entity.id,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
            "provider": entity.provider,
            "chatlog_base_url": entity.chatlog_base_url,
            "chatlog_timeout_sec": entity.chatlog_timeout_sec,
            "chatlog_decrypt_before_fetch": bool(entity.chatlog_decrypt_before_fetch),
            "chatlog_decrypt_cache_enabled": bool(entity.chatlog_decrypt_cache_enabled),
            "chatlog_decrypt_timeout_sec": entity.chatlog_decrypt_timeout_sec,
            "chatlog_decrypt_cache_buffer_sec": entity.chatlog_decrypt_cache_buffer_sec,
            "chatlog_work_dir": entity.chatlog_work_dir,
            "weflow_base_url": entity.weflow_base_url,
            "has_weflow_token": bool(entity.weflow_token_cipher or settings.weflow_access_token),
            "weflow_page_limit": entity.weflow_page_limit,
            "weflow_page_timeout_sec": entity.weflow_page_timeout_sec,
            "weflow_empty_page_retry": entity.weflow_empty_page_retry,
            "weflow_include_media": False,
        }
    )


def _runtime_from_entity(entity: ChatRecordSetting) -> Dict[str, Any]:
    return {
        "provider": entity.provider,
        "chatlog": {
            "base_url": entity.chatlog_base_url.rstrip("/"),
            "timeout_sec": entity.chatlog_timeout_sec,
            "decrypt_before_fetch": bool(entity.chatlog_decrypt_before_fetch),
            "decrypt_timeout_sec": entity.chatlog_decrypt_timeout_sec,
            "decrypt_cache_enabled": bool(entity.chatlog_decrypt_cache_enabled),
            "decrypt_cache_buffer_sec": entity.chatlog_decrypt_cache_buffer_sec,
            "work_dir": entity.chatlog_work_dir,
        },
        "weflow": _weflow_config_from_entity(entity),
    }


def _weflow_config_from_entity(entity: ChatRecordSetting) -> weflow.WeFlowConfig:
    token = ""
    if entity.weflow_token_cipher:
        token = decrypt_value(entity.weflow_token_cipher)
    elif settings.weflow_access_token:
        token = settings.weflow_access_token
    return weflow.WeFlowConfig(
        base_url=entity.weflow_base_url.rstrip("/"),
        token=token,
        page_limit=entity.weflow_page_limit,
        page_timeout_sec=entity.weflow_page_timeout_sec,
        empty_page_retry=entity.weflow_empty_page_retry,
    )


async def _probe_payload(data: Dict[str, Any], *, existing: ChatRecordSetting) -> None:
    merged = _entity_payload(existing)
    merged.update(data)
    if merged["provider"] == "weflow" and not merged.get("weflow_token_cipher"):
        raise ChatRecordError("WeFlow Token 不能为空")
    temp = ChatRecordSetting(**merged)
    await _probe_entity(temp)


async def _probe_entity(entity: ChatRecordSetting) -> None:
    if entity.provider == "weflow":
        config = _weflow_config_from_entity(entity)
        if not config.token:
            raise ChatRecordError("WeFlow Token 不能为空")
        try:
            await weflow.probe_health(config)
        except weflow.WeFlowError as exc:
            raise ChatRecordError(f"WeFlow 服务不可用：{exc}") from exc
        except Exception as exc:
            raise ChatRecordError(f"WeFlow 服务不可用：{exc}") from exc
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{entity.chatlog_base_url.rstrip('/')}/health")
            response.raise_for_status()
    except Exception as exc:
        raise ChatRecordError(f"ChatLog 服务不可用：{exc}") from exc


def _entity_payload(entity: ChatRecordSetting) -> Dict[str, Any]:
    return {
        "provider": entity.provider,
        "chatlog_base_url": entity.chatlog_base_url,
        "chatlog_timeout_sec": entity.chatlog_timeout_sec,
        "chatlog_decrypt_before_fetch": entity.chatlog_decrypt_before_fetch,
        "chatlog_decrypt_timeout_sec": entity.chatlog_decrypt_timeout_sec,
        "chatlog_decrypt_cache_enabled": entity.chatlog_decrypt_cache_enabled,
        "chatlog_decrypt_cache_buffer_sec": entity.chatlog_decrypt_cache_buffer_sec,
        "chatlog_work_dir": entity.chatlog_work_dir,
        "weflow_base_url": entity.weflow_base_url,
        "weflow_token_cipher": entity.weflow_token_cipher,
        "weflow_page_limit": entity.weflow_page_limit,
        "weflow_page_timeout_sec": entity.weflow_page_timeout_sec,
        "weflow_empty_page_retry": entity.weflow_empty_page_retry,
        "weflow_include_media": False,
    }


async def _fetch_chatlog_chatrooms(
    config: Dict[str, Any],
    *,
    keyword: Optional[str],
    limit: int,
    talkers: Optional[str],
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"format": "json", "limit": limit}
    if keyword:
        params["keyword"] = keyword
    async with httpx.AsyncClient(timeout=config["timeout_sec"]) as client:
        response = await client.get(f"{config['base_url']}/api/v1/chatroom", params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
    normalized = _normalize_chatlog_items(items)
    await _append_missing_chatlog_talkers(config, normalized, _split_talkers(talkers))
    return list(normalized.values())


def _normalize_chatlog_items(items: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for item in items:
        name = item.get("name")
        if not name:
            continue
        normalized[name] = {
            "name": name,
            "display_name": item.get("remark") or item.get("nickName") or item.get("nickname") or name,
            "owner": item.get("owner"),
            "raw": item,
            "user_count": len(item.get("users") or []),
        }
    return normalized


async def _append_missing_chatlog_talkers(
    config: Dict[str, Any],
    normalized: Dict[str, Dict[str, Any]],
    talkers: Sequence[str],
) -> None:
    async with httpx.AsyncClient(timeout=config["timeout_sec"]) as client:
        for talker in talkers:
            if talker in normalized:
                continue
            try:
                response = await client.get(
                    f"{config['base_url']}/api/v1/chatroom",
                    params={"format": "json", "limit": 20, "keyword": talker},
                )
                response.raise_for_status()
                items = response.json().get("items", [])
                match = next((item for item in _normalize_chatlog_items(items).values() if item["name"] == talker), None)
                normalized[talker] = match or _fallback_chatroom(talker)
            except Exception:
                normalized[talker] = _fallback_chatroom(talker)


async def _fetch_weflow_chatrooms(
    config: weflow.WeFlowConfig,
    *,
    keyword: Optional[str],
    limit: int,
    talkers: Optional[str],
) -> List[Dict[str, Any]]:
    sessions = await weflow.list_sessions(config, keyword=keyword, limit=limit)
    normalized: Dict[str, Dict[str, Any]] = {}
    for session in sessions:
        username = session.get("username") or session.get("id")
        if not username or not str(username).endswith("@chatroom"):
            continue
        normalized[username] = {
            "name": username,
            "display_name": session.get("displayName") or session.get("name") or username,
            "owner": None,
            "raw": session,
            "user_count": 0,
        }
    for talker in _split_talkers(talkers):
        if talker in normalized:
            continue
        try:
            found = await weflow.list_sessions(config, keyword=talker, limit=20)
            match = next((item for item in found if (item.get("username") or item.get("id")) == talker), None)
            if match:
                normalized[talker] = {
                    "name": talker,
                    "display_name": match.get("displayName") or match.get("name") or talker,
                    "owner": None,
                    "raw": match,
                    "user_count": 0,
                }
            else:
                normalized[talker] = _fallback_chatroom(talker)
        except Exception:
            normalized[talker] = _fallback_chatroom(talker)
    return list(normalized.values())


async def _collect_chatlog_messages(config: Dict[str, Any], talkers: List[str], time_window: dict, telemetry: Optional[dict] = None) -> str:
    talker_param = ",".join(talkers)
    buffer: List[str] = []
    end_dt = time_window.get("end")
    time_param = _chatlog_time_param(time_window)
    try:
        if config["decrypt_before_fetch"]:
            if isinstance(end_dt, datetime):
                buffer_sec = config["decrypt_cache_buffer_sec"] if config["decrypt_cache_enabled"] else 0
                decrypt_result = await chatlog.ensure_decrypted(
                    end_dt,
                    buffer_sec=buffer_sec,
                    timeout=config["decrypt_timeout_sec"],
                    base_url=config["base_url"],
                )
                if telemetry is not None:
                    telemetry["chatlog_decrypt"] = decrypt_result
                    telemetry["chatlog_work_dir"] = config.get("work_dir")
                logger.info(
                    "Chatlog decrypt check finished: status={} required_until={} last_message_at={}",
                    decrypt_result.get("status"),
                    decrypt_result.get("required_until"),
                    decrypt_result.get("last_decrypted_message_at"),
                )
                if decrypt_result.get("status") == "failed":
                    raise RuntimeError(decrypt_result.get("reason") or "chatlog 解密失败")
            else:
                logger.warning("Chatlog decrypt skipped because time window end is unavailable: %s", time_window)
        async for line in chatlog.stream_chatlog(
            talker_param,
            time_param,
            timeout=config["timeout_sec"],
            base_url=config["base_url"],
        ):
            buffer.append(line)
    except httpx.HTTPError as exc:
        raise ChatRecordError(f"chatlog 解密或拉取失败：{exc}") from exc
    return "\n".join(buffer)


async def _collect_weflow_messages(config: weflow.WeFlowConfig, talkers: List[str], time_window: dict) -> str:
    start_dt = time_window.get("start")
    end_dt = time_window.get("end")
    all_messages: List[Dict[str, Any]] = []
    member_names: Dict[str, str] = {}
    for talker in talkers:
        try:
            member_names.update(await weflow.list_group_members(config, talker))
        except Exception as exc:
            logger.warning("WeFlow group member lookup failed: talker={} error={}", talker, exc)
        all_messages.extend(
            await weflow.fetch_messages(
                config,
                talker=talker,
                start=start_dt if isinstance(start_dt, datetime) else None,
                end=end_dt if isinstance(end_dt, datetime) else None,
            )
        )
    return weflow.messages_to_chatlog_text(all_messages, member_names=member_names)


def _chatlog_time_param(time_window: dict) -> str:
    start_dt = time_window.get("start")
    end_dt = time_window.get("end")
    if start_dt and end_dt:
        start_str = start_dt.strftime("%Y-%m-%d/%H:%M")
        end_str = end_dt.strftime("%Y-%m-%d/%H:%M")
        return f"{start_str}~{end_str}"
    return time_window["time_str"]


def _split_talkers(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [value.strip() for value in raw.split(",") if value.strip()]


def _fallback_chatroom(talker: str) -> Dict[str, Any]:
    return {
        "name": talker,
        "display_name": talker,
        "owner": None,
        "raw": None,
        "user_count": 0,
    }
