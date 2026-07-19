"""Repository for IMA accounts."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.ima_account import ImaAccount
from .base import CRUDRepository


class ImaAccountRepository(CRUDRepository[ImaAccount]):
    def __init__(self) -> None:
        super().__init__(ImaAccount)

    def list_all(self, db: Session) -> List[ImaAccount]:
        return db.query(ImaAccount).order_by(ImaAccount.created_at.desc(), ImaAccount.id.desc()).all()

    def list_enabled(self, db: Session) -> List[ImaAccount]:
        return (
            db.query(ImaAccount)
            .filter(ImaAccount.is_enabled.is_(True))
            .order_by(ImaAccount.is_default.desc(), ImaAccount.id.asc())
            .all()
        )

    def get_default(self, db: Session) -> Optional[ImaAccount]:
        return (
            db.query(ImaAccount)
            .filter(ImaAccount.is_default.is_(True))
            .order_by(ImaAccount.id.asc())
            .first()
        )

    def clear_default(self, db: Session) -> None:
        db.query(ImaAccount).filter(ImaAccount.is_default.is_(True)).update(
            {"is_default": False},
            synchronize_session=False,
        )
        db.flush()
