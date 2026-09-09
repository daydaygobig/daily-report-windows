"""Business logic for LLM model management."""

import base64
import json
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..errors import AppError, NotFoundError
from ..integrations import image_generation, llm
from ..integrations.image_generation import normalize_image_base_url
from ..integrations.security import decrypt_value, encrypt_value
from ..repositories.model_repo import ModelRepository
from ..schemas.model import ModelCreate, ModelOut, ModelUpdate

model_repo = ModelRepository()


def _model_to_dict(model) -> dict:
    return {
        "id": model.id,
        "name": model.name,
        "provider": model.provider,
        "base_url": model.base_url,
        "api_key": decrypt_value(model.api_key_cipher) if model.api_key_cipher else None,
        "max_tokens": model.max_tokens,
        "temperature": model.temperature,
        "top_p": model.top_p,
        "extra": json.loads(model.extra) if model.extra else None,
        "request_standard": model.request_standard,
        "model_type": getattr(model, "model_type", "text") or "text",
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


def list_models(db: Session) -> List[ModelOut]:
    models = model_repo.list(db)
    return [ModelOut.model_validate(_model_to_dict(model)) for model in models]


def create_model(db: Session, payload: ModelCreate) -> ModelOut:
    data = payload.model_dump()
    if data.get("model_type") == "image":
        data["request_standard"] = "openai_images"
        data["base_url"] = normalize_image_base_url(data.get("base_url"))
    model = model_repo.create_with_secret(db, obj_in=data)
    return ModelOut.model_validate(_model_to_dict(model))


def update_model(db: Session, model_id: int, payload: ModelUpdate) -> ModelOut:
    entity = model_repo.get(db, model_id)
    if not entity:
        raise NotFoundError("模型不存在")
    obj_in = {k: v for k, v in payload.model_dump().items() if v is not None}
    target_type = obj_in.get("model_type", getattr(entity, "model_type", "text") or "text")
    if target_type == "image":
        obj_in["request_standard"] = "openai_images"
        obj_in["base_url"] = normalize_image_base_url(
            obj_in.get("base_url", getattr(entity, "base_url", None))
        )
    elif getattr(entity, "request_standard", "openai") == "openai_images" and "request_standard" not in obj_in:
        obj_in["request_standard"] = "openai"
    model = model_repo.update_with_secret(db, entity=entity, obj_in=obj_in)
    return ModelOut.model_validate(_model_to_dict(model))


def delete_model(db: Session, model_id: int) -> None:
    entity = model_repo.get(db, model_id)
    if not entity:
        raise NotFoundError("模型不存在")
    model_repo.delete(db, entity=entity)


def get_model_entity_by_provider(db: Session, provider: str):
    return model_repo.get_by_provider(db, provider)


def get_model_entity(db: Session, model_id: int):
    return model_repo.get(db, model_id)


def get_model_entity_by_providers(db: Session, providers: Iterable[str]):
    return model_repo.get_by_provider_list(db, providers)


def get_model_entity_by_base_url_contains(db: Session, substring: str):
    return model_repo.get_by_base_url_contains(db, substring)


_IMAGE_TEST_FIXED_PAYLOAD_KEYS = {
    "model",
    "prompt",
    "n",
    "size",
    "quality",
    "output_format",
}


def _safe_image_test_extra(extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep compatibility settings without allowing a costly test override."""

    config = dict(extra) if isinstance(extra, dict) else {}
    payload = config.get("payload")
    if isinstance(payload, dict):
        config["payload"] = {
            key: value
            for key, value in payload.items()
            if key not in _IMAGE_TEST_FIXED_PAYLOAD_KEYS
        }
    return config


def _derive_models_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    path = parsed.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = f"{path[: -len('/chat/completions')]}/models"
    elif not path.endswith("/models"):
        path = f"{path}/models" if path else "/models"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _extract_model_ids(data: Any) -> List[str]:
    if not isinstance(data, list):
        return []
    models: List[str] = []
    for item in data:
        if isinstance(item, str):
            models.append(item)
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or item.get("model")
            if isinstance(model_id, str):
                models.append(model_id)
    return models


async def fetch_remote_model_ids(base_url: Optional[str], api_key: Optional[str]) -> List[str]:
    """拉取厂商可用模型 ID 列表；业务错误以 AppError/NotFoundError 表达。"""
    if not base_url:
        raise AppError("请先填写 Base URL")
    if not api_key:
        raise AppError("请先填写 API Key")

    list_url = _derive_models_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.llm_timeout_sec) as client:
        try:
            response = await client.get(list_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AppError(f"该厂商不支持自动拉取，请手填模型ID: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise AppError(f"该厂商不支持自动拉取，请手填模型ID: {exc}") from exc

    response_payload = response.json()
    data = response_payload.get("data") or response_payload.get("models") or []
    return _extract_model_ids(data)


def _build_test_model(payload, db: Session) -> Dict[str, Any]:
    base_extra: Optional[Dict[str, Any]] = payload.extra if payload.extra is not None else None
    override_payload = payload.extra if payload.extra is not None else None
    request_standard = (payload.request_standard or "openai").lower()
    model_type = payload.model_type or "text"

    if payload.model_id:
        entity = get_model_entity(db, payload.model_id)
        if not entity:
            raise NotFoundError("模型不存在")
        provider = payload.provider or entity.provider
        base_url = payload.base_url or entity.base_url
        api_key_cipher = entity.api_key_cipher
        max_tokens = payload.max_tokens if payload.max_tokens is not None else entity.max_tokens
        temperature = payload.temperature if payload.temperature is not None else entity.temperature
        top_p = payload.top_p if payload.top_p is not None else entity.top_p
        if base_extra is None:
            base_extra = json.loads(entity.extra) if entity.extra else None
        if not payload.request_standard:
            request_standard = getattr(entity, "request_standard", "openai") or "openai"
        if not payload.model_type:
            model_type = getattr(entity, "model_type", "text") or "text"
    else:
        if not payload.api_key:
            raise AppError("未提供 API Key")
        provider = payload.provider
        base_url = payload.base_url
        api_key_cipher = encrypt_value(payload.api_key)
        max_tokens = payload.max_tokens
        temperature = payload.temperature
        top_p = payload.top_p

    if not provider:
        raise AppError("提供方不能为空")

    return {
        "provider": provider,
        "base_url": base_url,
        "api_key_cipher": api_key_cipher,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "extra": base_extra,
        "request_standard": request_standard,
        "model_type": model_type,
        "override_payload": override_payload,
    }


async def test_model_connection(payload, db: Session) -> Dict[str, Any]:
    """连通性测试：图片模型生成一张测试图（返回预览 data URI），文本模型流式取首个分片即成功。"""
    resolved = _build_test_model(payload, db)
    settings = get_settings()
    default_base_url = (
        "https://api.openai.com/v1/images/generations"
        if resolved.get("model_type") == "image"
        else "https://api.openai.com/v1/chat/completions"
    )
    # 连通性测试针对未落库的临时配置，用轻量命名空间对象承载模型参数
    temp_model = SimpleNamespace(
        provider=resolved["provider"],
        base_url=resolved.get("base_url") or default_base_url,
        api_key_cipher=resolved["api_key_cipher"],
        max_tokens=resolved.get("max_tokens"),
        temperature=resolved.get("temperature"),
        top_p=resolved.get("top_p"),
        extra=json.dumps(resolved["extra"], ensure_ascii=False) if resolved["extra"] is not None else None,
        request_standard=resolved.get("request_standard", "openai"),
        model_type=resolved.get("model_type", "text"),
    )

    try:
        if resolved.get("model_type") == "image":
            generated = await image_generation.generate_image(
                temp_model,
                prompt="A small simple blue circle centered on a plain white background, no text.",
                size="1024x1024",
                quality="low",
                timeout=payload.timeout or settings.llm_timeout_sec,
                extra_payload=_safe_image_test_extra(resolved.get("extra")),
            )
            preview = f"data:{generated.mime_type};base64,{base64.b64encode(generated.content).decode('ascii')}"
            return {"ok": True, "preview": preview}
        stream = llm.stream_completion(
            temp_model,
            prompt=payload.prompt or "这是一条连通性测试请求",
            timeout=payload.timeout or settings.llm_timeout_sec,
            extra_payload=resolved["override_payload"],
        )
        async for _chunk in stream:
            break
    except llm.LLMError as exc:
        raise AppError(str(exc)) from exc
    except image_generation.ImageGenerationError as exc:
        raise AppError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise AppError(str(exc)) from exc

    return {"ok": True}
