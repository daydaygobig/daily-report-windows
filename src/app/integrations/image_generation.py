"""OpenAI Images-compatible image generation client."""

import base64
import binascii
import json
import struct
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..config import get_settings
from .security import decrypt_value

settings = get_settings()
DEFAULT_IMAGE_BASE_URL = "https://api.openai.com/v1/images/generations"
IMAGE_ENDPOINT_SUFFIX = "/v1/images/generations"


class ImageGenerationError(Exception):
    """Raised when an image provider request cannot return image bytes."""


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
    encoded = item.get("b64_json")
    if not isinstance(encoded, str) or not encoded.strip():
        if item.get("url"):
            raise ImageGenerationError(
                "图片模型只返回了图片 URL；请在高级配置中让接口返回 b64_json"
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
