"""Generic CRUD repository helpers."""

from typing import Generic, Iterable, Optional, Type, TypeVar

from sqlalchemy.orm import Session

from ..db import Base

ModelType = TypeVar("ModelType", bound=Base)


class CRUDRepository(Generic[ModelType]):
    """Generic CRUD repository."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, entity_id: int) -> Optional[ModelType]:
        return db.query(self.model).get(entity_id)

    def list(self, db: Session, *, skip: int = 0, limit: int = 100) -> Iterable[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, *, obj_in: dict) -> ModelType:
        entity = self.model(**obj_in)
        db.add(entity)
        db.flush()
        return entity

    def update(self, db: Session, *, entity: ModelType, obj_in: dict) -> ModelType:
        for field, value in obj_in.items():
            setattr(entity, field, value)
        db.add(entity)
        db.flush()
        return entity

    def delete(self, db: Session, *, entity: ModelType) -> None:
        db.delete(entity)
