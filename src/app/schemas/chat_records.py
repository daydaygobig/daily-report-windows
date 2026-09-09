"""Schemas for chat record source settings and API responses."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .base import ORMBase

ChatRecordProvider = Literal["chatlog", "weflow"]


class ChatRecordSettingsBase(BaseModel):
    provider: ChatRecordProvider = "chatlog"
    chatlog_base_url: str = "http://127.0.0.1:5030"
    chatlog_timeout_sec: int = Field(default=60, ge=1)
    chatlog_decrypt_before_fetch: bool = True
    chatlog_decrypt_cache_enabled: bool = True
    chatlog_decrypt_timeout_sec: int = Field(default=300, ge=1)
    chatlog_decrypt_cache_buffer_sec: int = Field(default=0, ge=0)
    chatlog_work_dir: str = ""
    weflow_base_url: str = "http://127.0.0.1:5031"
    weflow_token: Optional[str] = None
    weflow_page_limit: int = Field(default=1000, ge=1, le=10000)
    weflow_page_timeout_sec: int = Field(default=180, ge=1)
    weflow_empty_page_retry: int = Field(default=2, ge=0, le=10)


class ChatRecordSettingsUpdate(ChatRecordSettingsBase):
    pass


class ChatRecordSettingsOut(ORMBase):
    provider: ChatRecordProvider
    chatlog_base_url: str
    chatlog_timeout_sec: int
    chatlog_decrypt_before_fetch: bool
    chatlog_decrypt_cache_enabled: bool
    chatlog_decrypt_timeout_sec: int
    chatlog_decrypt_cache_buffer_sec: int
    chatlog_work_dir: str
    weflow_base_url: str
    has_weflow_token: bool = False
    weflow_page_limit: int
    weflow_page_timeout_sec: int
    weflow_empty_page_retry: int
    weflow_include_media: bool = False


class ChatRecordStatus(BaseModel):
    provider: ChatRecordProvider
    status: Literal["ok", "unreachable", "invalid_token", "unknown"]
    message: str


class ChatRecordTestResult(BaseModel):
    ok: bool
    provider: ChatRecordProvider
    status: str
    message: str
