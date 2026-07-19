"""IMA account entity."""

from sqlalchemy import Boolean, Column, DateTime, String, Text

from .base import BaseModel


class ImaAccount(BaseModel):
    __tablename__ = "ima_accounts"

    name = Column(String(255), nullable=False)
    client_id = Column(String(255), nullable=False)
    api_key_cipher = Column(Text, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    remark = Column(Text, nullable=True)
    default_target_type = Column(String(32), nullable=False, default="knowledge_base")
    default_note_folder_id = Column(String(255), nullable=True)
    default_note_folder_name = Column(String(255), nullable=True)
    default_knowledge_base_id = Column(String(255), nullable=True)
    default_knowledge_base_name = Column(String(255), nullable=True)
    default_knowledge_folder_id = Column(String(255), nullable=True)
    default_knowledge_folder_name = Column(String(255), nullable=True)
    last_test_at = Column(DateTime, nullable=True)
    last_test_status = Column(String(32), nullable=True)
    last_test_message = Column(Text, nullable=True)
