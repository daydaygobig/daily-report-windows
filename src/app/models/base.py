"""Base ORM model with helper mixins."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer

from ..db import Base


class BaseModel(Base):
    """Base mixin providing id and timestamps."""

    __abstract__ = True

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
