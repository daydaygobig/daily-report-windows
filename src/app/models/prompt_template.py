"""Prompt template entity."""

from sqlalchemy import Column, String, Text

from .base import BaseModel


class PromptTemplate(BaseModel):
    __tablename__ = "prompt_templates"

    name = Column(String(120), nullable=False, unique=True)
    content = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
