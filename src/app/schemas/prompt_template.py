"""Pydantic schemas for prompt templates."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .base import ORMBase


class PromptTemplateBase(BaseModel):
    name: str = Field(..., max_length=120)
    content: str
    description: Optional[str] = None
    template_type: Literal["regular", "image"] = "regular"
    image_split_enabled: bool = False
    image_split_prompt: Optional[str] = None

    @model_validator(mode="after")
    def validate_image_split(self):
        self.image_split_enabled = False
        self.image_split_prompt = None
        return self


class PromptTemplateCreate(PromptTemplateBase):
    pass


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    content: Optional[str] = None
    description: Optional[str] = None
    template_type: Optional[Literal["regular", "image"]] = None
    image_split_enabled: Optional[bool] = None
    image_split_prompt: Optional[str] = None


class PromptTemplateOut(ORMBase):
    name: str
    content: str
    description: Optional[str]
    template_type: Literal["regular", "image"] = "regular"
    image_split_enabled: bool = False
    image_split_prompt: Optional[str] = None

    @model_validator(mode="after")
    def hide_legacy_image_split(self):
        self.image_split_enabled = False
        self.image_split_prompt = None
        return self
