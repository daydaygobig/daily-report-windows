"""IMA sync record entity."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class ImaSyncRecord(BaseModel):
    __tablename__ = "ima_sync_records"

    batch_id = Column(String(64), nullable=True, index=True)
    trigger_type = Column(String(32), nullable=False)
    source_type = Column(String(32), nullable=False)
    source_path = Column(Text, nullable=True)
    source_name = Column(String(255), nullable=True)
    source_size = Column(Integer, nullable=True)
    source_mtime = Column(DateTime, nullable=True)
    ima_account_id = Column(Integer, ForeignKey("ima_accounts.id", ondelete="SET NULL"), nullable=True)
    ima_account_name = Column(String(255), nullable=True)
    sync_job_id = Column(Integer, ForeignKey("ima_sync_jobs.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    execution_id = Column(Integer, ForeignKey("executions.id", ondelete="SET NULL"), nullable=True)
    target_type = Column(String(32), nullable=False)
    note_folder_id = Column(String(255), nullable=True)
    note_folder_name = Column(String(255), nullable=True)
    knowledge_base_id = Column(String(255), nullable=True)
    knowledge_base_name = Column(String(255), nullable=True)
    knowledge_folder_id = Column(String(255), nullable=True)
    knowledge_folder_name = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False)
    skip_reason = Column(String(64), nullable=True)
    error_code = Column(Integer, nullable=True)
    error_explanation = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    remote_doc_id = Column(String(255), nullable=True)
    remote_media_id = Column(String(255), nullable=True)

    ima_account = relationship("ImaAccount", foreign_keys=[ima_account_id])
    sync_job = relationship("ImaSyncJob", foreign_keys=[sync_job_id])
    task = relationship("Task", foreign_keys=[task_id])
    job = relationship("Job", foreign_keys=[job_id])
    execution = relationship("Execution", foreign_keys=[execution_id])
