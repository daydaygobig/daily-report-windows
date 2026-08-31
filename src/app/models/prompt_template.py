"""Prompt template entity."""

from sqlalchemy import Boolean, Column, String, Text

from .base import BaseModel


class PromptTemplate(BaseModel):
    __tablename__ = "prompt_templates"

    name = Column(String(120), nullable=False, unique=True)
    content = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    template_type = Column(String(20), nullable=False, default="regular")
    image_split_enabled = Column(Boolean, nullable=False, default=False)
    image_split_prompt = Column(Text, nullable=True)
