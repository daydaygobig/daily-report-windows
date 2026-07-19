"""Repository for alerts."""

from typing import List

from sqlalchemy.orm import Session

from ..models.alert import Alert
from .base import CRUDRepository


class AlertRepository(CRUDRepository[Alert]):
    def __init__(self) -> None:
        super().__init__(Alert)

    def list_unacknowledged(self, db: Session, *, limit: int = 100) -> List[Alert]:
        return (
            db.query(Alert)
            .filter(Alert.acknowledged.is_(False))
            .order_by(Alert.created_at.desc())
            .limit(limit)
            .all()
        )
