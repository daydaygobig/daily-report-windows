"""LLM model configuration entity."""

from sqlalchemy import Column, Float, Integer, String, Text

from .base import BaseModel


class Model(BaseModel):
    __tablename__ = "models"

    name = Column(String(100), nullable=False, unique=True)
    provider = Column(String(50), nullable=False)
    base_url = Column(String(255), nullable=True)
    api_key_cipher = Column(Text, nullable=False)
    max_tokens = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    top_p = Column(Float, nullable=True)
    extra = Column(Text, nullable=True)
    request_standard = Column(String(20), nullable=False, default="openai")
    model_type = Column(String(20), nullable=False, default="text")
