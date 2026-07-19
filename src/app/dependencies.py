"""Reusable FastAPI dependencies."""

from typing import Generator

from sqlalchemy.orm import Session

from .db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
