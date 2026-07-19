"""Pydantic schemas for alerts."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from .base import ORMBase


class AlertCreate(BaseModel):
    task_id: Optional[int] = None
    job_id: Optional[int] = None
    level: str = "error"
    category: str
    message: str
    payload: Optional[dict] = None


class AlertUpdate(BaseModel):
    acknowledged: Optional[bool] = None


class AlertOut(ORMBase):
    task_id: Optional[int]
    job_id: Optional[int]
    execution_id: Optional[int] = None
    level: str
    category: str
    message: str
    payload: Optional[dict]
    acknowledged: bool
    acknowledged_at: Optional[datetime]
