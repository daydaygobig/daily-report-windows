"""Pydantic schemas for prompt templates."""

from typing import Optional

from pydantic import BaseModel, Field

from .base import ORMBase


class PromptTemplateBase(BaseModel):
    name: str = Field(..., max_length=120)
    content: str
    description: Optional[str] = None


class PromptTemplateCreate(PromptTemplateBase):
    pass


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    content: Optional[str] = None
    description: Optional[str] = None


class PromptTemplateOut(ORMBase):
    name: str
    content: str
    description: Optional[str]
