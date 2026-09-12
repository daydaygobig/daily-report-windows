"""OpenAI Images-compatible image generation client."""

import asyncio
import base64
import binascii
import json
import struct
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..config import get_settings
from .security import decrypt_value

settings = get_settings()
DEFAULT_IMAGE_BASE_URL = "https://api.openai.com/v1/images/generations"
IMAGE_ENDPOINT_SUFFIX = "/v1/images/generations"
IMAGE_TASK_POLL_INTERVAL_SEC = 3.0
IMAGE_TASK_MAX_WAIT_SEC = 600.0


class ImageGenerationError(Exception):
    """Raised when an image provider request cannot return image bytes."""


def is_connect_failure(exc: BaseException | None) -> bool:
    """判断异常链上是否存在 TCP 连接类失败（本机网络/系统代理瞬断的典型签名）。

    generate_image 把 httpx 异常包装成 ImageGenerationError 并保留 __cause__，
    这里沿因果链向下找 httpx.ConnectError / ConnectTimeout，供上层做退避重试。
    """

    depth = 0
    while exc is not None and depth < 8:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return True
        exc = exc.__cause__
        depth += 1
    return False


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    mime_type: str = "image/png"
    revised_prompt: str | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.content)


def detect_image_dimensions(content: bytes, mime_type: str | None = None) -> tuple[int, int] | None:
    """Read pixel dimensions from image bytes without decoding the whole image."""

    if len(content) >= 24 and content.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = struct.unpack(">II", content[16:24])
        return (width, height) if width > 0 and height > 0 else None
    if len(content) >= 10 and content[:2] == b"\xff\xd8":
        offset = 2
        while offset + 9 < len(content):
            if content[offset] != 0xFF:
                offset += 1
                continue
            marker = content[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(content):
                break
            segment_length = int.from_bytes(content[offset : offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(content):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height = int.from_bytes(content[offset + 3 : offset + 5], "big")
                width = int.from_bytes(content[offset + 5 : offset + 7], "big")
                return (width, height) if width > 0 and height > 0 else None
            offset += segment_length
    return None


def normalize_image_base_url(base_url: str | None) -> str:
    """Return one complete OpenAI Images-compatible endpoint."""

    value = (base_url or "").strip()
    if not value:
        return DEFAULT_IMAGE_BASE_URL

    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    lowered = path.lower()
    while lowered.endswith(IMAGE_ENDPOINT_SUFFIX):
        path = path[: -len(IMAGE_ENDPOINT_SUFFIX)].rstrip("/")
        lowered = path.lower()

    if lowered.endswith("/images/generations"):
        normalized_path = path
    elif lowered.endswith("/v1"):
        normalized_path = f"{path}/images/generations"
    else:
        normalized_path = f"{path}{IMAGE_ENDPOINT_SUFFIX}"

    return urlunsplit(
        (parts.scheme, parts.netloc, normalized_path, parts.query, parts.fragment)
    )


async def generate_image(
    model,
    *,
    prompt: str,
    size: str = "auto",
    quality: str | None = None,
    timeout: int | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> GeneratedImage:
    api_key = decrypt_value(model.api_key_cipher)
    base_url = normalize_image_base_url(getattr(model, "base_url", None))
    extra_config = _load_extra_config(model, extra_payload)
    overrides = extra_config.get("payload")
    payload: dict[str, Any] = dict(overrides) if isinstance(overrides, dict) else {}
    payload.update({
        "model": model.provider,
        "prompt": prompt,
        "n": 1,
        "size": size or "auto",
        "output_format": "png",
    })
    if quality:
        payload["quality"] = quality
    # gpt-image 系支持 background 参数：强制不透明，避免模型输出透明底 PNG
    # （模板要求整卡铺满主背景色，透明底即版式违规）。其他模型不认识该参数
    # 会直接报错，因此只在 gpt-image 系上发送，且不覆盖额外 payload 里显式
    # 配置的 background
    if "gpt-image" in str(model.provider or "").lower() and "background" not in payload:
        payload["background"] = "opaque"

    auth_header = str(extra_config.get("auth_header") or "Authorization")
    headers = {"Content-Type": "application/json"}
    if auth_header.lower() == "authorization":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers[auth_header] = api_key
    additional_headers = extra_config.get("headers")
    if isinstance(additional_headers, dict):
        headers.update(
            {str(key): str(value) for key, value in additional_headers.items()}
        )

    request_timeout = timeout or settings.llm_timeout_sec
    try:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.post(base_url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        raise ImageGenerationError(
            f"图片模型响应异常: {exc.response.status_code} {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ImageGenerationError(f"图片模型请求失败: {exc}") from exc

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise ImageGenerationError("图片模型返回了非 JSON 响应") from exc
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ImageGenerationError("图片模型没有返回图片数据")
    item = items[0]
    task_id = item.get("task_id")
    if (
        isinstance(task_id, str)
        and task_id.strip()
        and not item.get("b64_json")
        and not item.get("url")
    ):
        # 异步任务式接口（如 APIMart）：提交后返回 task_id，需要轮询任务结果
        return await _await_async_image_task(
            base_url=base_url,
            headers=headers,
            task_id=task_id.strip(),
            timeout=request_timeout,
        )
    encoded = item.get("b64_json")
    if not isinstance(encoded, str) or not encoded.strip():
        if item.get("url"):
            if payload.get("response_format") == "b64_json":
                raise ImageGenerationError(
                    "已要求代理返回 b64_json，但接口仍只返回图片 URL；"
                    "请确认该代理支持 response_format 参数"
                )
            raise ImageGenerationError(
                "图片模型只返回了图片 URL；请在模型配置中开启“兼容代理接口”后重试"
            )
        raise ImageGenerationError("图片模型没有返回 b64_json 图片数据")
    mime_type = "image/png"
    if encoded.startswith("data:"):
        header, separator, encoded = encoded.partition(",")
        if not separator or ";base64" not in header:
            raise ImageGenerationError("图片模型返回的数据地址格式不正确")
        mime_type = header[5:].split(";", 1)[0] or mime_type
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageGenerationError("图片模型返回的 base64 图片无法解码") from exc
    if not image_bytes:
        raise ImageGenerationError("图片模型返回的图片为空")
    return GeneratedImage(
        content=image_bytes,
        mime_type=mime_type,
        revised_prompt=(
            item.get("revised_prompt")
            if isinstance(item.get("revised_prompt"), str)
            else None
        ),
    )


def _load_extra_config(model, extra_payload: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(extra_payload, dict):
        return extra_payload
    raw = getattr(model, "extra", None)
    if not raw:
        return {}
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def image_task_query_base(base_url: str) -> str:
    """从 images/generations 端点推导任务查询端点（.../v1/tasks）。"""

    parts = urlsplit(base_url)
    path = parts.path
    lowered = path.lower()
    while lowered.endswith("/images/generations"):
        path = path[: -len("/images/generations")].rstrip("/")
        lowered = path.lower()
    if not lowered.endswith("/v1"):
        path = path.rstrip("/") + "/v1"
    return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/") + "/tasks", "", ""))


async def _await_async_image_task(
    *,
    base_url: str,
    headers: dict,
    task_id: str,
    timeout: int | None,
) -> GeneratedImage:
    query_url = f"{image_task_query_base(base_url)}/{task_id}"
    deadline = time.monotonic() + IMAGE_TASK_MAX_WAIT_SEC
    request_timeout = timeout or settings.llm_timeout_sec
    while True:
        if time.monotonic() >= deadline:
            raise ImageGenerationError(f"图片任务超时未完成（task_id={task_id}）")
        await asyncio.sleep(IMAGE_TASK_POLL_INTERVAL_SEC)
        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.get(query_url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ImageGenerationError(
                f"图片任务查询失败: {exc.response.status_code} {exc.response.text.strip()}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageGenerationError(f"图片任务查询失败: {exc}") from exc
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ImageGenerationError("图片任务查询返回了非 JSON 响应") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        status = str(data.get("status") or "").lower()
        if status == "completed":
            return await _download_task_image(data, request_timeout)
        if status == "failed":
            error = data.get("error") if isinstance(data.get("error"), dict) else {}
            message = str(error.get("message") or data.get("error") or "未知原因")
            raise ImageGenerationError(f"图片任务失败：{message}")


async def _download_task_image(data: dict, timeout: int | None) -> GeneratedImage:
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    images = result.get("images") if isinstance(result.get("images"), list) else []
    first = images[0] if images and isinstance(images[0], dict) else {}
    raw_url = first.get("url")
    image_url = ""
    if isinstance(raw_url, list):
        image_url = str(raw_url[0]) if raw_url else ""
    elif isinstance(raw_url, str):
        image_url = raw_url
    if not image_url:
        raise ImageGenerationError("图片任务完成但没有返回图片地址")
    request_timeout = timeout or settings.llm_timeout_sec
    try:
        async with httpx.AsyncClient(timeout=request_timeout, follow_redirects=True) as client:
            response = await client.get(image_url)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ImageGenerationError(f"图片下载失败: {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ImageGenerationError(f"图片下载失败: {exc}") from exc
    content = response.content
    if not content:
        raise ImageGenerationError("下载到的图片为空")
    mime_type = "image/png"
    lowered = image_url.lower()
    if lowered.endswith((".jpg", ".jpeg")):
        mime_type = "image/jpeg"
    elif lowered.endswith(".webp"):
        mime_type = "image/webp"
    return GeneratedImage(content=content, mime_type=mime_type)
