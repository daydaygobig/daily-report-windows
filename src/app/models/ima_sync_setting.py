"""IMA sync settings entity."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .base import BaseModel


class ImaSyncSetting(BaseModel):
    __tablename__ = "ima_sync_settings"

    default_account_id = Column(Integer, ForeignKey("ima_accounts.id", ondelete="SET NULL"), nullable=True)
    client_id = Column(String(255), nullable=True)
    api_key_cipher = Column(Text, nullable=True)
    default_target_type = Column(String(32), nullable=False, default="knowledge_base")
    default_note_folder_id = Column(String(255), nullable=True)
    default_note_folder_name = Column(String(255), nullable=True)
    default_knowledge_base_id = Column(String(255), nullable=True)
    default_knowledge_base_name = Column(String(255), nullable=True)
    default_knowledge_folder_id = Column(String(255), nullable=True)
    default_knowledge_folder_name = Column(String(255), nullable=True)
    auto_sync_enabled = Column(Boolean, nullable=False, default=False)
    auto_sync_frequency = Column(String(16), nullable=False, default="daily")
    auto_sync_weekday = Column(Integer, nullable=True)
    auto_sync_time = Column(String(5), nullable=False, default="08:00")
    local_sync_path = Column(Text, nullable=True)
    recursive_enabled = Column(Boolean, nullable=False, default=True)
    allowed_extensions = Column(Text, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    last_sync_summary = Column(Text, nullable=True)
