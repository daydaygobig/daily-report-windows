"""Task entity."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class Task(BaseModel):
    __tablename__ = "tasks"

    name = Column(Text, nullable=False, unique=True)
    task_type = Column(Text, nullable=False, default="report")
    prompt = Column(Text, nullable=False)
    model_id = Column(Integer, ForeignKey("models.id", ondelete="SET NULL"), nullable=True)
    image_model_id = Column(Integer, ForeignKey("models.id", ondelete="SET NULL"), nullable=True)
    # Legacy compatibility fields. Image split settings now live on jobs, but
    # older databases still require these task columns during INSERT.
    image_split_enabled = Column(Boolean, default=False, nullable=False)
    image_split_prompt = Column(Text, nullable=True)
    model_sequence = Column(Text, nullable=True)
    prompt_template_id = Column(Integer, ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True)
    talkers = Column(Text, nullable=False, default="[]")
    talker_names = Column(Text, nullable=True)
    push_webhook_ids = Column(Text, nullable=False, default="[]")
    alert_webhook_ids = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    store_local_results = Column(Boolean, default=True, nullable=False)
    store_chatlog = Column(Boolean, default=False, nullable=False)
    system_prompt_custom_enabled = Column(Boolean, default=False, nullable=False)
    system_prompt_template = Column(Text, nullable=True)
    system_prompt_include_message_count = Column(Boolean, default=False, nullable=False)
    topic_style_config = Column(Text, nullable=True)
    model = relationship("Model", foreign_keys=[model_id])
    image_model = relationship("Model", foreign_keys=[image_model_id])
    prompt_template = relationship("PromptTemplate")
    jobs = relationship("Job", back_populates="task", cascade="all, delete-orphan", order_by="Job.display_order")
