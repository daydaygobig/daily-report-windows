"""Repository for IMA sync settings."""

from typing import Optional

from sqlalchemy.orm import Session

from ..models.ima_sync_setting import ImaSyncSetting
from ..repositories.base import CRUDRepository
from ..utils.converters import serialize_list


class ImaSyncSettingRepository(CRUDRepository[ImaSyncSetting]):
    def __init__(self) -> None:
        super().__init__(ImaSyncSetting)

    def get_singleton(self, db: Session) -> Optional[ImaSyncSetting]:
        return db.query(ImaSyncSetting).order_by(ImaSyncSetting.id.asc()).first()

    def create_default(self, db: Session) -> ImaSyncSetting:
        return self.create(
            db,
            obj_in={
                "default_account_id": None,
                "client_id": "",
                "api_key_cipher": None,
                "default_target_type": "knowledge_base",
                "auto_sync_enabled": False,
                "auto_sync_frequency": "daily",
                "auto_sync_weekday": 0,
                "auto_sync_time": "08:00",
                "recursive_enabled": True,
                "allowed_extensions": serialize_list(["md", "txt"]),
            },
        )

    def update_settings(self, db: Session, *, entity: ImaSyncSetting, obj_in: dict) -> ImaSyncSetting:
        payload = obj_in.copy()
        if "allowed_extensions" in payload and payload["allowed_extensions"] is not None:
            payload["allowed_extensions"] = serialize_list(payload["allowed_extensions"])
        return super().update(db, entity=entity, obj_in=payload)
