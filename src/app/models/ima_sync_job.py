"""IMA auto sync job entity."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class ImaSyncJob(BaseModel):
    __tablename__ = "ima_sync_jobs"

    name = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    ima_account_id = Column(Integer, ForeignKey("ima_accounts.id", ondelete="SET NULL"), nullable=True)
    target_type = Column(String(32), nullable=False, default="knowledge_base")
    note_folder_id = Column(String(255), nullable=True)
    note_folder_name = Column(String(255), nullable=True)
    knowledge_base_id = Column(String(255), nullable=True)
    knowledge_base_name = Column(String(255), nullable=True)
    knowledge_folder_id = Column(String(255), nullable=True)
    knowledge_folder_name = Column(String(255), nullable=True)
    local_sync_path = Column(Text, nullable=False)
    recursive_enabled = Column(Boolean, nullable=False, default=True)
    allowed_extensions = Column(Text, nullable=True)
    schedule_frequency = Column(String(16), nullable=False, default="daily")
    schedule_weekday = Column(Integer, nullable=True)
    schedule_time = Column(String(5), nullable=False, default="08:00")
    webhook_id = Column(Integer, ForeignKey("webhooks.id", ondelete="SET NULL"), nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(32), nullable=True)
    last_sync_summary = Column(Text, nullable=True)

    ima_account = relationship("ImaAccount", foreign_keys=[ima_account_id])
    webhook = relationship("Webhook", foreign_keys=[webhook_id])
