"""Repository for tasks."""

import json
from typing import List, Optional

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models.task import Task
from ..utils import converters
from .base import CRUDRepository


class TaskRepository(CRUDRepository[Task]):
    def __init__(self) -> None:
        super().__init__(Task)

    @staticmethod
    def _prepare_payload(obj_in: dict) -> dict:
        payload = obj_in.copy()
        if "talkers" in payload and payload["talkers"] is not None:
            payload["talkers"] = converters.serialize_list(payload["talkers"])
        if "talker_names" in payload and payload["talker_names"] is not None:
            payload["talker_names"] = converters.serialize_list(payload["talker_names"])
        if "push_webhook_ids" in payload and payload["push_webhook_ids"] is not None:
            payload["push_webhook_ids"] = converters.serialize_list(payload["push_webhook_ids"])
        if "alert_webhook_ids" in payload and payload["alert_webhook_ids"] is not None:
            payload["alert_webhook_ids"] = converters.serialize_list(payload["alert_webhook_ids"])
        if "topic_style_config" in payload and payload["topic_style_config"] is not None and not isinstance(payload["topic_style_config"], str):
            payload["topic_style_config"] = json.dumps(payload["topic_style_config"], ensure_ascii=False)
        if "model_sequence" in payload and payload["model_sequence"] is not None and not isinstance(payload["model_sequence"], str):
            payload["model_sequence"] = json.dumps(payload["model_sequence"], ensure_ascii=False)
        if "image_model_sequence" in payload and payload["image_model_sequence"] is not None and not isinstance(payload["image_model_sequence"], str):
            payload["image_model_sequence"] = json.dumps(payload["image_model_sequence"], ensure_ascii=False)
        if "store_chatlog" in payload and payload["store_chatlog"] is None:
            payload.pop("store_chatlog")
        return payload

    def create_task(self, db: Session, *, obj_in: dict) -> Task:
        payload = self._prepare_payload(obj_in)
        return super().create(db, obj_in=payload)

    def update_task(self, db: Session, *, entity: Task, obj_in: dict) -> Task:
        payload = self._prepare_payload(obj_in)
        return super().update(db, entity=entity, obj_in=payload)

    def get_with_jobs(self, db: Session, task_id: int) -> Optional[Task]:
        return db.query(Task).filter(Task.id == task_id).first()

    def list_all(self, db: Session) -> List[Task]:
        return db.query(Task).all()

    def sync_prompt_template(self, db: Session, template_id: int, content: str) -> None:
        db.execute(
            update(Task)
                .where(Task.prompt_template_id == template_id)
                .values(prompt=content)
        )

    def clear_prompt_template(self, db: Session, template_id: int) -> None:
        db.execute(
            update(Task)
                .where(Task.prompt_template_id == template_id)
                .values(prompt_template_id=None)
        )
