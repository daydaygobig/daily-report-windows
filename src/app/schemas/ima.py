"""Pydantic schemas for IMA sync."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .base import ORMBase

ImaTargetType = Literal["note", "knowledge_base"]
ImaSyncStatus = Literal["success", "failed", "skipped", "partial", "none"]
ImaTriggerType = Literal["manual", "auto", "job"]
ImaSyncScope = Literal["daily_report_job", "ima_sync_job"]


class ImaOption(BaseModel):
    label: str
    value: str


class ImaFolderOption(BaseModel):
    label: str
    value: str


class ImaCredentialPreview(BaseModel):
    client_id: str = ""
    api_key: str = ""


class ImaKnowledgeFolderPreview(ImaCredentialPreview):
    knowledge_base_id: str


class ImaAccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    client_id: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=1)
    is_enabled: bool = True
    is_default: bool = False
    remark: Optional[str] = None
    default_target_type: ImaTargetType = "knowledge_base"
    default_note_folder_id: Optional[str] = None
    default_note_folder_name: Optional[str] = None
    default_knowledge_base_id: Optional[str] = None
    default_knowledge_base_name: Optional[str] = None
    default_knowledge_folder_id: Optional[str] = None
    default_knowledge_folder_name: Optional[str] = None


class ImaAccountCreate(ImaAccountBase):
    pass


class ImaAccountUpdate(ImaAccountBase):
    pass


class ImaAccountOut(ORMBase):
    name: str
    client_id: str
    api_key: str = ""
    client_id_masked: str
    is_enabled: bool
    is_default: bool
    remark: Optional[str] = None
    default_target_type: ImaTargetType = "knowledge_base"
    default_note_folder_id: Optional[str] = None
    default_note_folder_name: Optional[str] = None
    default_knowledge_base_id: Optional[str] = None
    default_knowledge_base_name: Optional[str] = None
    default_knowledge_folder_id: Optional[str] = None
    default_knowledge_folder_name: Optional[str] = None
    last_test_at: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_test_message: Optional[str] = None


class ImaSyncSettingsUpdate(BaseModel):
    default_account_id: Optional[int] = Field(default=None, ge=1)


class ImaSyncSettingsOut(ORMBase):
    default_account_id: Optional[int] = None
    default_account_name: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_summary: Optional[str] = None
    next_run_at: Optional[datetime] = None


class ImaSyncSettingsTestResult(BaseModel):
    ok: bool
    message: str


class ImaSyncJobBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    is_enabled: bool = True
    ima_account_id: int = Field(ge=1)
    target_type: ImaTargetType = "knowledge_base"
    note_folder_id: Optional[str] = None
    note_folder_name: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    knowledge_base_name: Optional[str] = None
    knowledge_folder_id: Optional[str] = None
    knowledge_folder_name: Optional[str] = None
    local_sync_path: str = Field(min_length=1)
    recursive_enabled: bool = True
    allowed_extensions: List[Literal["md", "txt"]] = Field(default_factory=lambda: ["md", "txt"])
    schedule_frequency: Literal["daily", "weekly"] = "daily"
    schedule_weekday: Optional[int] = Field(default=0, ge=0, le=6)
    schedule_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    webhook_id: Optional[int] = None


class ImaSyncJobCreate(ImaSyncJobBase):
    pass


class ImaSyncJobUpdate(ImaSyncJobBase):
    pass


class ImaSyncJobOut(ORMBase):
    name: str
    is_enabled: bool
    ima_account_id: Optional[int] = None
    ima_account_name: Optional[str] = None
    target_type: ImaTargetType
    note_folder_id: Optional[str] = None
    note_folder_name: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    knowledge_base_name: Optional[str] = None
    knowledge_folder_id: Optional[str] = None
    knowledge_folder_name: Optional[str] = None
    local_sync_path: str
    recursive_enabled: bool
    allowed_extensions: List[str] = Field(default_factory=list)
    schedule_frequency: Literal["daily", "weekly"]
    schedule_weekday: Optional[int] = 0
    schedule_time: str
    webhook_id: Optional[int] = None
    webhook_name: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_summary: Optional[str] = None
    next_run_at: Optional[datetime] = None


class ImaSyncRecordOut(ORMBase):
    batch_id: Optional[str] = None
    trigger_type: str
    source_type: str
    source_path: Optional[str] = None
    source_name: Optional[str] = None
    source_size: Optional[int] = None
    source_mtime: Optional[datetime] = None
    ima_account_id: Optional[int] = None
    ima_account_name: Optional[str] = None
    sync_job_id: Optional[int] = None
    sync_job_name: Optional[str] = None
    sync_scope: ImaSyncScope
    task_id: Optional[int] = None
    task_name: Optional[str] = None
    job_id: Optional[int] = None
    job_name: Optional[str] = None
    execution_id: Optional[int] = None
    target_type: str
    note_folder_id: Optional[str] = None
    note_folder_name: Optional[str] = None
    knowledge_base_id: Optional[str] = None
    knowledge_base_name: Optional[str] = None
    knowledge_folder_id: Optional[str] = None
    knowledge_folder_name: Optional[str] = None
    status: str
    skip_reason: Optional[str] = None
    error_code: Optional[int] = None
    error_explanation: Optional[str] = None
    error_message: Optional[str] = None
    remote_doc_id: Optional[str] = None
    remote_media_id: Optional[str] = None


class ImaSyncRecordPage(BaseModel):
    items: List[ImaSyncRecordOut]
    total: int
    page: int
    page_size: int


class ImaSyncBatchOut(BaseModel):
    batch_id: str
    created_at: datetime
    trigger_type: ImaTriggerType
    sync_scope: ImaSyncScope
    ima_account_id: Optional[int] = None
    ima_account_name: Optional[str] = None
    sync_job_id: Optional[int] = None
    sync_job_name: Optional[str] = None
    task_id: Optional[int] = None
    task_name: Optional[str] = None
    job_id: Optional[int] = None
    job_name: Optional[str] = None
    execution_id: Optional[int] = None
    target_type: ImaTargetType
    target_display: str
    total_count: int
    success_count: int
    skipped_count: int
    failed_count: int
    status: ImaSyncStatus
    summary: str


class ImaSyncBatchPage(BaseModel):
    items: List[ImaSyncBatchOut]
    total: int
    page: int
    page_size: int


class ImaManualSyncResult(BaseModel):
    batch_id: str
    scanned_count: int
    success_count: int
    skipped_count: int
    failed_count: int
    message: str
