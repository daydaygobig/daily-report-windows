"""Alert entity."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from .base import BaseModel


class Alert(BaseModel):
    __tablename__ = "alerts"

    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    execution_id = Column(Integer, ForeignKey("executions.id", ondelete="SET NULL"), nullable=True)
    level = Column(String(30), nullable=False, default="error")
    category = Column(String(60), nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(Text, nullable=True)
    acknowledged = Column(Boolean, default=False, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
