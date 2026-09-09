"""共享测试夹具：每个测试使用独立的临时 sqlite 数据库。"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 —— 导入模型包以注册全部 ORM 映射（relationship 字符串解析依赖它）
from app.db import Base


@pytest.fixture()
def db_engine(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    factory = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
