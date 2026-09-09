"""Alembic 版本管理接入的特征测试。

覆盖三条路径：空库 upgrade head 建全量 schema；存量库 stamp baseline；已版本化库重复同步幂等。
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401 —— 注册 ORM 模型
from app.db import Base
from app.db_migrations import sync_alembic_version

REPO_ROOT = Path(__file__).resolve().parents[1]


def _config(url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _version(engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def test_upgrade_head_builds_full_schema_on_empty_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    command.upgrade(_config(str(engine.url)), "head")

    tables = set(inspect(engine).get_table_names())
    assert {"jobs", "tasks", "executions", "webhooks", "alerts", "models", "github_configs"} <= tables
    # 关键索引与存量库对齐（ensure_schema 时代手工建的 idx_* 也必须在 baseline 里）
    index_names = {
        idx["name"]
        for table in tables
        for idx in inspect(engine).get_indexes(table)
    }
    assert "idx_jobs_ima_account_id" in index_names
    assert "idx_ima_sync_records_batch_id" in index_names

    # 重复 upgrade 是 no-op
    command.upgrade(_config(str(engine.url)), "head")
    engine.dispose()


def test_sync_stamps_unversioned_existing_db(tmp_path):
    """存量库（有表、无 alembic_version）：stamp 到 baseline，不重建表。"""
    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    Base.metadata.create_all(engine)

    sync_alembic_version(engine)

    assert _version(engine)
    # 数据未被破坏
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar() == 0
    engine.dispose()


def test_sync_is_idempotent_for_versioned_db(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'versioned.db').as_posix()}")
    Base.metadata.create_all(engine)

    sync_alembic_version(engine)
    first = _version(engine)
    sync_alembic_version(engine)

    assert _version(engine) == first
    engine.dispose()
