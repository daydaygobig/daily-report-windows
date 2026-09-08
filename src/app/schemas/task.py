"""Pydantic schemas for Task entity."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .base import ORMBase
from .job import JobOut


TaskType = Literal["report", "export", "topic_card", "image_card"]
CardInputSource = Literal["chatlog", "report"]
TopicStyleConfig = Dict[str, Dict[str, str]]

DEFAULT_TOPIC_STYLE_CONFIG: TopicStyleConfig = {
    "industry_business": {"style_key": "style_a", "theme": "amber"},
    "work_methods": {"style_key": "style_b", "theme": "blue"},
    "career_growth": {"style_key": "style_c", "theme": "green"},
    "mind_wellbeing": {"style_key": "style_d", "theme": "neutral"},
}


class TaskModelConfig(BaseModel):
    model_id: int = Field(..., ge=1)
    max_attempts: int = Field(default=2, ge=1)


class TaskCreate(BaseModel):
    name: str = Field(..., max_length=200)
    task_type: TaskType = "report"
    prompt: str = ""
    model_id: Optional[int] = None
    image_model_id: Optional[int] = None
    upstream_task_id: Optional[int] = None
    card_input_source: CardInputSource = "chatlog"
    model_sequence: Optional[List[TaskModelConfig]] = None
    image_model_sequence: Optional[List[TaskModelConfig]] = None
    prompt_template_id: Optional[int] = None
    talkers: List[str] = Field(default_factory=list)
    talker_names: Optional[List[str]] = None
    push_webhook_ids: List[int] = Field(default_factory=list)
    alert_webhook_ids: Optional[List[int]] = None
    is_active: bool = True
    store_local_results: bool = True
    store_chatlog: bool = False
    system_prompt_custom_enabled: bool = False
    system_prompt_template: Optional[str] = None
    system_prompt_include_message_count: bool = False
    topic_style_config: TopicStyleConfig = Field(
        default_factory=lambda: {key: value.copy() for key, value in DEFAULT_TOPIC_STYLE_CONFIG.items()}
    )


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    task_type: Optional[TaskType] = None
    prompt: Optional[str] = None
    model_id: Optional[int] = None
    image_model_id: Optional[int] = None
    upstream_task_id: Optional[int] = None
    card_input_source: Optional[CardInputSource] = None
    model_sequence: Optional[List[TaskModelConfig]] = None
    image_model_sequence: Optional[List[TaskModelConfig]] = None
    prompt_template_id: Optional[int] = None
    talkers: Optional[List[str]] = None
    talker_names: Optional[List[str]] = None
    push_webhook_ids: Optional[List[int]] = None
    alert_webhook_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None
    store_local_results: Optional[bool] = None
    store_chatlog: Optional[bool] = None
    system_prompt_custom_enabled: Optional[bool] = None
    system_prompt_template: Optional[str] = None
    system_prompt_include_message_count: Optional[bool] = None
    topic_style_config: Optional[Dict[str, Any]] = None


class TaskOut(ORMBase):
    name: str
    task_type: TaskType = "report"
    prompt: str
    model_id: Optional[int]
    image_model_id: Optional[int]
    upstream_task_id: Optional[int] = None
    card_input_source: CardInputSource = "chatlog"
    model_sequence: List[TaskModelConfig] = Field(default_factory=list)
    image_model_sequence: List[TaskModelConfig] = Field(default_factory=list)
    prompt_template_id: Optional[int]
    talkers: List[str]
    talker_names: List[str] = Field(default_factory=list)
    push_webhook_ids: List[int]
    alert_webhook_ids: Optional[List[int]]
    is_active: bool
    store_local_results: bool
    store_chatlog: bool
    system_prompt_custom_enabled: bool
    system_prompt_template: Optional[str]
    system_prompt_include_message_count: bool
    topic_style_config: TopicStyleConfig
    jobs: List[JobOut] = Field(default_factory=list)
