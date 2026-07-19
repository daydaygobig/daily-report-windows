"""Repository for prompt templates."""

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.prompt_template import PromptTemplate
from .base import CRUDRepository


class PromptTemplateRepository(CRUDRepository[PromptTemplate]):
    def __init__(self) -> None:
        super().__init__(PromptTemplate)

    def list_all(self, db: Session) -> List[PromptTemplate]:
        return db.query(PromptTemplate).order_by(PromptTemplate.updated_at.desc()).all()

    def get_by_name(self, db: Session, name: str) -> Optional[PromptTemplate]:
        return db.query(PromptTemplate).filter(PromptTemplate.name == name).first()
