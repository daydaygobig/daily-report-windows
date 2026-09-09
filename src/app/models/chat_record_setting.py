"""Chat record source settings."""

from sqlalchemy import Boolean, Column, Integer, String, Text

from .base import BaseModel


class ChatRecordSetting(BaseModel):
    __tablename__ = "chat_record_settings"

    provider = Column(String(16), nullable=False, default="chatlog")
    chatlog_base_url = Column(Text, nullable=False, default="http://127.0.0.1:5030")
    chatlog_timeout_sec = Column(Integer, nullable=False, default=60)
    chatlog_decrypt_before_fetch = Column(Boolean, nullable=False, default=True)
    chatlog_decrypt_timeout_sec = Column(Integer, nullable=False, default=300)
    chatlog_decrypt_cache_enabled = Column(Boolean, nullable=False, default=True)
    chatlog_decrypt_cache_buffer_sec = Column(Integer, nullable=False, default=0)
    chatlog_work_dir = Column(Text, nullable=False, default="")
    weflow_base_url = Column(Text, nullable=False, default="http://127.0.0.1:5031")
    weflow_token_cipher = Column(Text, nullable=True)
    weflow_page_limit = Column(Integer, nullable=False, default=1000)
    weflow_page_timeout_sec = Column(Integer, nullable=False, default=180)
    weflow_empty_page_retry = Column(Integer, nullable=False, default=2)
    weflow_include_media = Column(Boolean, nullable=False, default=False)
