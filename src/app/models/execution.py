"""Execution history entity."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class Execution(BaseModel):
    __tablename__ = "executions"

    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(30), nullable=False, default="pending")
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    prompt_chars = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    llm_model_name = Column(String(120), nullable=True)
    summary_md = Column(Text, nullable=True)
    summary_path = Column(Text, nullable=True)
    chatlog_path = Column(Text, nullable=True)
    html_backup_path = Column(Text, nullable=True)
    deploy_status = Column(String(20), nullable=False, default="none")
    deploy_url = Column(Text, nullable=True)
    deploy_error = Column(Text, nullable=True)
    github_config_id = Column(Integer, ForeignKey("github_configs.id", ondelete="SET NULL"), nullable=True)
    ima_sync_status = Column(String(20), nullable=False, default="none")
    ima_sync_error = Column(Text, nullable=True)
    ima_sync_batch_id = Column(String(64), nullable=True)
    raw_request = Column(Text, nullable=True)
    raw_response = Column(Text, nullable=True)
    error_msg = Column(Text, nullable=True)
    is_manual = Column(Boolean, nullable=False, default=False)
    prompt_usage = Column(Text, nullable=True)
    exported_files = Column(Text, nullable=True)

    job = relationship("Job", back_populates="executions")
    github_config = relationship("GithubConfig")
    deploy_records = relationship(
        "GithubDeployment",
        back_populates="execution",
        foreign_keys="GithubDeployment.execution_id",
        order_by="GithubDeployment.id",
    )

    @property
    def deploy_record(self):
        for record in self.deploy_records:
            if record.artifact_type in (None, "html_report"):
                return record
        return self.deploy_records[0] if self.deploy_records else None
