"""Business logic for LLM model management."""

import json
from typing import Iterable, List

from sqlalchemy.orm import Session

from ..integrations.image_generation import normalize_image_base_url
from ..integrations.security import decrypt_value
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
        raise ValueError("模型不存在")
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
        raise ValueError("模型不存在")
    model_repo.delete(db, entity=entity)


def get_model_entity_by_provider(db: Session, provider: str):
    return model_repo.get_by_provider(db, provider)


def get_model_entity(db: Session, model_id: int):
    return model_repo.get(db, model_id)


def get_model_entity_by_providers(db: Session, providers: Iterable[str]):
    return model_repo.get_by_provider_list(db, providers)


def get_model_entity_by_base_url_contains(db: Session, substring: str):
    return model_repo.get_by_base_url_contains(db, substring)
