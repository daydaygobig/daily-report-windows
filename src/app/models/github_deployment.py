"""GitHub deployment execution records."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class GithubDeployment(BaseModel):
    __tablename__ = "github_deployments"

    execution_id = Column(Integer, ForeignKey("executions.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    github_config_id = Column(Integer, ForeignKey("github_configs.id", ondelete="SET NULL"), nullable=True)
    job_name = Column(String(120), nullable=True)
    task_name = Column(String(120), nullable=True)
    config_name = Column(String(120), nullable=True)
    artifact_type = Column(String(40), nullable=True)
    artifact_label = Column(String(120), nullable=True)
    repo_full_name = Column(String(255), nullable=True)
    branch = Column(String(80), nullable=True)
    repo_path = Column(Text, nullable=True)
    github_file_url = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="running")
    pages_url = Column(Text, nullable=True)
    error_msg = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    github_config = relationship("GithubConfig")
    job = relationship("Job")
    task = relationship("Task")
    execution = relationship("Execution", back_populates="deploy_records", foreign_keys=[execution_id])
