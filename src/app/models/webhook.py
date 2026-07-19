"""Webhook configuration entity."""

from sqlalchemy import Boolean, Column, String, Text

from .base import BaseModel


class Webhook(BaseModel):
    __tablename__ = "webhooks"

    name = Column(String(120), nullable=False, unique=True)
    url_cipher = Column(Text, nullable=False)
    headers = Column(Text, nullable=True)
    card_mode = Column(String(20), nullable=False, default="markdown")
    card_header_enabled = Column(Boolean, nullable=False, default=False)
    card_header_title = Column(Text, nullable=True)
    card_header_subtitle = Column(Text, nullable=True)
    card_header_color = Column(String(20), nullable=True)
    image_render_engine = Column(String(20), nullable=False, default="satori")
    feishu_app_id = Column(String(120), nullable=True)
    feishu_app_secret_cipher = Column(Text, nullable=True)
