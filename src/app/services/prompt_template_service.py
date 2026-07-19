"""Business logic for prompt templates."""

from sqlalchemy.orm import Session

from ..models.prompt_template import PromptTemplate
from ..repositories.prompt_template_repo import PromptTemplateRepository
from ..repositories.task_repo import TaskRepository
from ..schemas.prompt_template import PromptTemplateCreate, PromptTemplateUpdate

template_repo = PromptTemplateRepository()
task_repo = TaskRepository()


def list_templates(db: Session):
    return template_repo.list_all(db)


def create_template(db: Session, payload: PromptTemplateCreate) -> PromptTemplate:
    data = payload.model_dump()
    existing = template_repo.get_by_name(db, data["name"])
    if existing:
        raise ValueError("提示词名称已存在")
    return template_repo.create(db, obj_in=data)


def update_template(db: Session, template_id: int, payload: PromptTemplateUpdate) -> PromptTemplate:
    entity = template_repo.get(db, template_id)
    if not entity:
        raise ValueError("提示词不存在")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "name" in data:
        conflict = template_repo.get_by_name(db, data["name"])
        if conflict and conflict.id != entity.id:
            raise ValueError("提示词名称已存在")
    updated = template_repo.update(db, entity=entity, obj_in=data)
    if "content" in data:
        task_repo.sync_prompt_template(db, template_id, updated.content)
    return updated


def delete_template(db: Session, template_id: int) -> None:
    entity = template_repo.get(db, template_id)
    if not entity:
        raise ValueError("提示词不存在")
    task_repo.clear_prompt_template(db, template_id)
    template_repo.delete(db, entity=entity)
