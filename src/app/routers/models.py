"""Routes for LLM models."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..errors import NotFoundError
from ..integrations.security import decrypt_value
from ..schemas.model import ModelCreate, ModelTestRequest, ModelUpdate, RemoteModelsRequest
from ..services import model_service
from ..utils.responses import success_response

router = APIRouter(prefix="/models", tags=["models"])


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
    model = model_service.update_model(db, model_id, payload)
    return success_response(model.model_dump(), message="模型更新成功")


@router.delete("/{model_id}", response_model=dict)
def delete_model(model_id: int, db: Session = Depends(get_db)):
    model_service.delete_model(db, model_id)
    return success_response(message="模型已删除")


@router.post("/fetch-remote-models", response_model=dict)
async def fetch_remote_models(payload: RemoteModelsRequest, db: Session = Depends(get_db)):
    base_url = payload.base_url
    api_key = payload.api_key
    if payload.model_id and not api_key:
        entity = model_service.get_model_entity(db, payload.model_id)
        if not entity:
            raise NotFoundError("模型不存在")
        base_url = base_url or entity.base_url
        api_key = decrypt_value(entity.api_key_cipher)

    models = await model_service.fetch_remote_model_ids(base_url, api_key)
    return success_response({"models": models})


@router.post("/test-connection", response_model=dict)
async def test_model_connection(payload: ModelTestRequest, db: Session = Depends(get_db)):
    result = await model_service.test_model_connection(payload, db)
    return success_response(result)
