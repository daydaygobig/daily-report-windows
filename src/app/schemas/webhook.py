"""Pydantic schemas for Webhook entity."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .base import ORMBase

CARD_COLOR_OPTIONS = {
    "blue",
    "wathet",
    "turquoise",
    "green",
    "yellow",
    "orange",
    "red",
    "carmine",
    "violet",
    "purple",
    "indigo",
    "grey",
    "default",
}

CardMode = Literal["markdown", "template", "custom_json"]
ImageRenderEngine = Literal["satori", "svg", "typst"]


class WebhookBase(BaseModel):
    name: str = Field(..., max_length=120)
    headers: Optional[dict] = None
    card_mode: CardMode = "markdown"
    card_header_enabled: bool = False
    card_header_title: Optional[str] = Field(default=None, max_length=200)
    card_header_subtitle: Optional[str] = Field(default=None, max_length=200)
    card_header_color: Optional[str] = Field(default="blue", max_length=20)
    image_render_engine: ImageRenderEngine = "satori"
    feishu_app_id: Optional[str] = Field(default=None, max_length=120)
    feishu_app_secret: Optional[str] = None

    @model_validator(mode="after")
    def validate_color(cls, values: "WebhookBase"):
        color = values.card_header_color
        if color and color not in CARD_COLOR_OPTIONS:
            raise ValueError("卡片主题色不在允许范围内")
        return values


class WebhookCreate(WebhookBase):
    url: str


class WebhookUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    url: Optional[str] = None
    headers: Optional[dict] = None
    card_mode: Optional[CardMode] = None
    card_header_enabled: Optional[bool] = None
    card_header_title: Optional[str] = Field(default=None, max_length=200)
    card_header_subtitle: Optional[str] = Field(default=None, max_length=200)
    card_header_color: Optional[str] = Field(default=None, max_length=20)
    image_render_engine: Optional[ImageRenderEngine] = None
    feishu_app_id: Optional[str] = Field(default=None, max_length=120)
    feishu_app_secret: Optional[str] = None

    @model_validator(mode="after")
    def validate_color(cls, values: "WebhookUpdate"):
        color = values.card_header_color
        if color and color not in CARD_COLOR_OPTIONS:
            raise ValueError("卡片主题色不在允许范围内")
        return values


class WebhookOut(ORMBase):
    name: str
    headers: Optional[dict]
    card_mode: CardMode
    card_header_enabled: bool
    card_header_title: Optional[str]
    card_header_subtitle: Optional[str]
    card_header_color: Optional[str]
    image_render_engine: ImageRenderEngine = "satori"
    feishu_app_id: Optional[str] = None
    has_feishu_app_secret: bool = False


class WebhookImageTestPayload(BaseModel):
    app_id: Optional[str] = Field(default=None, max_length=120)
    app_secret: Optional[str] = None
    send_image: bool = False


class WebhookImageTestResult(BaseModel):
    ok: bool
    message: str
    image_key: Optional[str] = None
