"""Repository for chat record source settings."""

from typing import Optional

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.chat_record_setting import ChatRecordSetting
from .base import CRUDRepository


class ChatRecordSettingRepository(CRUDRepository[ChatRecordSetting]):
    def __init__(self) -> None:
        super().__init__(ChatRecordSetting)

    def get_singleton(self, db: Session) -> Optional[ChatRecordSetting]:
        return db.query(ChatRecordSetting).order_by(ChatRecordSetting.id.asc()).first()

    def create_default(self, db: Session) -> ChatRecordSetting:
        settings = get_settings()
        return self.create(
            db,
            obj_in={
                "provider": "chatlog",
                "chatlog_base_url": settings.chatlog_base_url,
                "chatlog_timeout_sec": settings.chatlog_timeout_sec,
                "chatlog_decrypt_before_fetch": settings.chatlog_decrypt_before_fetch,
                "chatlog_decrypt_timeout_sec": settings.chatlog_decrypt_timeout_sec,
                "chatlog_decrypt_cache_enabled": settings.chatlog_decrypt_cache_enabled,
                "chatlog_decrypt_cache_buffer_sec": settings.chatlog_decrypt_cache_buffer_sec,
                "chatlog_work_dir": settings.chatlog_work_dir,
                "weflow_base_url": settings.weflow_base_url,
                "weflow_page_limit": settings.weflow_page_limit,
                "weflow_page_timeout_sec": settings.weflow_page_timeout_sec,
                "weflow_empty_page_retry": settings.weflow_empty_page_retry,
                "weflow_include_media": False,
            },
        )

    def update_settings(self, db: Session, *, entity: ChatRecordSetting, obj_in: dict) -> ChatRecordSetting:
        return super().update(db, entity=entity, obj_in=obj_in)
