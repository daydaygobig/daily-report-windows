"""Repository for LLM models."""

import json
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from ..integrations.security import encrypt_value
from ..models.model import Model
from .base import CRUDRepository


class ModelRepository(CRUDRepository[Model]):
    def __init__(self) -> None:
        super().__init__(Model)

    def create_with_secret(self, db: Session, *, obj_in: dict) -> Model:
        obj_in = obj_in.copy()
        obj_in = self._prepare_payload(obj_in)
        return super().create(db, obj_in=obj_in)

    def update_with_secret(self, db: Session, *, entity: Model, obj_in: dict) -> Model:
        payload = self._prepare_payload(obj_in, allow_missing=True)
        return super().update(db, entity=entity, obj_in=payload)

    def get_by_provider(self, db: Session, provider: str) -> Model | None:
        return db.query(Model).filter(Model.provider == provider).first()

    def get_by_provider_list(self, db: Session, providers: Iterable[str]) -> Model | None:
        items: List[str] = [value for value in providers if value]
        if not items:
            return None
        return db.query(Model).filter(Model.provider.in_(items)).first()

    def get_by_base_url_contains(self, db: Session, substring: str) -> Model | None:
        if not substring:
            return None
        return db.query(Model).filter(Model.base_url.contains(substring)).first()

    @staticmethod
    def _prepare_payload(obj_in: dict, allow_missing: bool = False) -> dict:
        payload = obj_in.copy()
        if "api_key" in payload:
            api_key = payload["api_key"]
            if api_key is None and allow_missing:
                payload.pop("api_key")
            else:
                payload.pop("api_key")
                payload["api_key_cipher"] = encrypt_value(api_key or "")
        if "extra" in payload and payload["extra"] is not None:
            payload["extra"] = json.dumps(payload["extra"], ensure_ascii=False)
        elif "extra" in payload and payload["extra"] is None:
            payload["extra"] = None
        if "request_standard" in payload:
            value = payload["request_standard"]
            if value is None and allow_missing:
                payload.pop("request_standard")
            else:
                payload["request_standard"] = (value or "openai").lower()
        elif not allow_missing:
            payload["request_standard"] = "openai"
        return payload
