"""Routes for LLM models."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import get_settings
from ..dependencies import get_db
from ..integrations import image_generation, llm
from ..integrations.security import decrypt_value, encrypt_value
from ..schemas.model import ModelCreate, ModelTestRequest, ModelUpdate, RemoteModelsRequest
from ..services import model_service
from ..utils.responses import success_response

router = APIRouter(prefix="/models", tags=["models"])
settings = get_settings()
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


@router.get("/", response_model=dict)
def list_models(db: Session = Depends(get_db)):
    models = model_service.list_models(db)
    return success_response([model.model_dump() for model in models])


@router.post("/", response_model=dict)
def create_model(payload: ModelCreate, db: Session = Depends(get_db)):
    model = model_service.create_model(db, payload)
    return success_response(model.model_dump(), message="模型创建成功")


@router.put("/{model_id}", response_model=dict)
def update_model(model_id: int, payload: ModelUpdate, db: Session = Depends(get_db)):
    try:
        model = model_service.update_model(db, model_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    return success_response(model.model_dump(), message="模型更新成功")


@router.delete("/{model_id}", response_model=dict)
def delete_model(model_id: int, db: Session = Depends(get_db)):
    try:
        model_service.delete_model(db, model_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": str(exc)}) from exc
    return success_response(message="模型已删除")


@router.post("/fetch-remote-models", response_model=dict)
async def fetch_remote_models(payload: RemoteModelsRequest, db: Session = Depends(get_db)):
    base_url = payload.base_url
    api_key = payload.api_key
    if payload.model_id and not api_key:
        entity = model_service.get_model_entity(db, payload.model_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "模型不存在"})
        base_url = base_url or entity.base_url
        api_key = decrypt_value(entity.api_key_cipher)

    if not base_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "请先填写 Base URL"})
    if not api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "请先填写 API Key"})

    list_url = _derive_models_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=settings.llm_timeout_sec) as client:
        try:
            response = await client.get(list_url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail={"code": 1, "message": f"该厂商不支持自动拉取，请手填模型ID: {exc.response.text}"},
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": 1, "message": f"该厂商不支持自动拉取，请手填模型ID: {exc}"},
            ) from exc

    response_payload = response.json()
    data = response_payload.get("data") or response_payload.get("models") or []
    models = _extract_model_ids(data)

    return success_response({"models": models})


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


@router.post("/test-connection", response_model=dict)
async def test_model_connection(payload: ModelTestRequest, db: Session = Depends(get_db)):
    resolved = await _build_test_model(payload, db)
    default_base_url = (
        "https://api.openai.com/v1/images/generations"
        if resolved.get("model_type") == "image"
        else "https://api.openai.com/v1/chat/completions"
    )
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
            return success_response({"ok": True, "preview": preview})
        stream = llm.stream_completion(
            temp_model,
            prompt=payload.prompt or "这是一条连通性测试请求",
            timeout=payload.timeout or settings.llm_timeout_sec,
            extra_payload=resolved["override_payload"],
        )
        async for _chunk in stream:
            break
    except llm.LLMError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    except image_generation.ImageGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": str(exc)}) from exc

    return success_response({"ok": True})


async def _build_test_model(payload: ModelTestRequest, db: Session) -> Dict[str, Any]:
    base_extra: Optional[Dict[str, Any]] = payload.extra if payload.extra is not None else None
    override_payload = payload.extra if payload.extra is not None else None
    request_standard = (payload.request_standard or "openai").lower()
    model_type = payload.model_type or "text"

    if payload.model_id:
        entity = model_service.get_model_entity(db, payload.model_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 404, "message": "模型不存在"})
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "未提供 API Key"})
        provider = payload.provider
        base_url = payload.base_url
        api_key_cipher = encrypt_value(payload.api_key)
        max_tokens = payload.max_tokens
        temperature = payload.temperature
        top_p = payload.top_p

    if not provider:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": 1, "message": "提供方不能为空"})

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
