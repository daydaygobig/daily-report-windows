"""Feishu webhook integration."""

import asyncio
import base64
import json
from typing import Dict, Iterable, Optional

import httpx

from loguru import logger

from ..integrations.security import decrypt_value
from ..models.webhook import Webhook


def _clip_plain_text(value: str, limit: int = 80) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


async def send_markdown(
    webhook: Webhook,
    *,
    title: str,
    content: str,
    subtitle: str | None = None,
    template: str = "blue",
    max_retries: int = 3,
    retry_interval: float = 2.0,
) -> None:
    url = decrypt_value(webhook.url_cipher)
    headers: Optional[Dict[str, str]] = None
    if webhook.headers:
        try:
            decrypted = decrypt_value(webhook.headers)
            headers = json.loads(decrypted)
        except ValueError:
            headers = None
    resolved_title = _clip_plain_text(title or "")
    header = {
        "template": template or "blue",
        "title": {"tag": "plain_text", "content": resolved_title or "通知"},
    }
    if subtitle:
        header["subtitle"] = {"tag": "plain_text", "content": _clip_plain_text(subtitle)}
    card = {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": header,
        "body": {
            "direction": "vertical",
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                }
            ],
        },
    }
    payload = {
        "msg_type": "interactive",
        "card": card,
    }
    logger.info("Feishu webhook={} 即将推送标题={}", getattr(webhook, "id", None), resolved_title or "通知")

    attempt = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            attempt += 1
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                _ensure_webhook_accepted(response)
                return
            except Exception:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(retry_interval)


def _ensure_webhook_accepted(response: httpx.Response) -> None:
    """飞书 webhook 失败时仍返回 HTTP 200，必须检查响应体里的业务码。"""
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"飞书 webhook 返回了非 JSON 响应：{response.text[:200]}")
    code = data.get("code")
    if code not in (None, 0):
        raise RuntimeError(f"飞书 webhook 拒绝消息（code={code}）：{data.get('msg')}")


async def broadcast_markdown(
    webhooks: Iterable[Webhook],
    *,
    title: str,
    content: str,
    subtitle: str | None = None,
    template: str = "blue",
    max_retries: int = 3,
    retry_interval: float = 2.0,
):
    for webhook in webhooks:
        await send_markdown(
            webhook,
            title=title,
            content=content,
            subtitle=subtitle,
            template=template,
            max_retries=max_retries,
            retry_interval=retry_interval,
        )


async def get_tenant_access_token(*, app_id: str, app_secret: str) -> str:
    payload = {"app_id": app_id, "app_secret": app_secret}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        response.raise_for_status()
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(data.get("msg") or "获取 tenant_access_token 失败")
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError("飞书未返回 tenant_access_token")
    return token


async def upload_image(*, app_id: str, app_secret: str, image_bytes: bytes, filename: str = "topic-card.png") -> str:
    token = await get_tenant_access_token(app_id=app_id, app_secret=app_secret)
    files = {"image": (filename, image_bytes, "image/png")}
    data = {"image_type": "message"}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data=data,
            files=files,
        )
        response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or "上传飞书图片失败")
    image_key = (payload.get("data") or {}).get("image_key")
    if not image_key:
        raise RuntimeError("飞书上传成功但未返回 image_key")
    return image_key


async def send_image(
    webhook: Webhook,
    *,
    image_key: str,
    max_retries: int = 3,
    retry_interval: float = 2.0,
) -> None:
    url = decrypt_value(webhook.url_cipher)
    headers: Optional[Dict[str, str]] = None
    if webhook.headers:
        try:
            decrypted = decrypt_value(webhook.headers)
            headers = json.loads(decrypted)
        except ValueError:
            headers = None
    payload = {
        "msg_type": "image",
        "content": {"image_key": image_key},
    }
    attempt = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            attempt += 1
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                _ensure_webhook_accepted(response)
                return
            except Exception:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(retry_interval)


def _ensure_webhook_accepted(response: httpx.Response) -> None:
    """飞书 webhook 失败时仍返回 HTTP 200，必须检查响应体里的业务码。"""
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"飞书 webhook 返回了非 JSON 响应：{response.text[:200]}")
    code = data.get("code")
    if code not in (None, 0):
        raise RuntimeError(f"飞书 webhook 拒绝消息（code={code}）：{data.get('msg')}")


def build_test_png() -> bytes:
    # 1x1 transparent PNG, enough to verify Feishu image upload credentials.
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
