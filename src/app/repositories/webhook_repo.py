"""Repository for webhooks."""

from typing import Iterable, List

from sqlalchemy.orm import Session

from ..integrations.security import encrypt_value
from ..models.webhook import Webhook
from .base import CRUDRepository


class WebhookRepository(CRUDRepository[Webhook]):
    def __init__(self) -> None:
        super().__init__(Webhook)

    def create_with_secret(self, db: Session, *, obj_in: dict) -> Webhook:
        obj_in = obj_in.copy()
        url = obj_in.pop("url")
        obj_in["url_cipher"] = encrypt_value(url)
        if headers := obj_in.get("headers"):
            obj_in["headers"] = encrypt_value(headers)
        if secret := obj_in.pop("feishu_app_secret", None):
            obj_in["feishu_app_secret_cipher"] = encrypt_value(secret)
        return super().create(db, obj_in=obj_in)

    def update_with_secret(self, db: Session, *, entity: Webhook, obj_in: dict) -> Webhook:
        obj_in = obj_in.copy()
        if "url" in obj_in and obj_in["url"] is not None:
            obj_in["url_cipher"] = encrypt_value(obj_in.pop("url"))
        if "headers" in obj_in and obj_in["headers"] is not None:
            obj_in["headers"] = encrypt_value(obj_in["headers"])
        if "feishu_app_secret" in obj_in:
            secret = obj_in.pop("feishu_app_secret")
            if secret:
                obj_in["feishu_app_secret_cipher"] = encrypt_value(secret)
        return super().update(db, entity=entity, obj_in=obj_in)

    def get_by_ids(self, db: Session, ids: Iterable[int]) -> List[Webhook]:
        return db.query(Webhook).filter(Webhook.id.in_(list(ids))).all()
