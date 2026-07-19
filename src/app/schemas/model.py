"""Pydantic schemas for LLM model entity."""

from typing import Optional

from pydantic import BaseModel, Field

from .base import ORMBase


class ModelCreate(BaseModel):
    name: str = Field(..., max_length=100)
    provider: str = Field(..., max_length=50)
    base_url: Optional[str] = None
    api_key: str
    max_tokens: Optional[int] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=100)
    top_p: Optional[float] = Field(default=None, ge=0, le=100)
    extra: Optional[dict] = None
    request_standard: Optional[str] = Field(default="openai", pattern=r"^(openai|gemini|anthropic)$")


class ModelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=50)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=100)
    top_p: Optional[float] = Field(default=None, ge=0, le=100)
    extra: Optional[dict] = None
    request_standard: Optional[str] = Field(default=None, pattern=r"^(openai|gemini|anthropic)$")


class ModelOut(ORMBase):
    name: str
    provider: str
    base_url: Optional[str]
    api_key: Optional[str] = None
    max_tokens: Optional[int]
    temperature: Optional[float]
    top_p: Optional[float]
    extra: Optional[dict]
    request_standard: str


class ModelTestRequest(BaseModel):
    provider: Optional[str] = Field(default=None, max_length=50)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = Field(default=None, ge=0, le=100)
    top_p: Optional[float] = Field(default=None, ge=0, le=100)
    extra: Optional[dict] = None
    timeout: Optional[int] = Field(default=None, ge=1)
    prompt: Optional[str] = None
    model_id: Optional[int] = Field(default=None, ge=1)
    request_standard: Optional[str] = Field(default=None, pattern=r"^(openai|gemini|anthropic)$")


class RemoteModelsRequest(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_id: Optional[int] = Field(default=None, ge=1)
