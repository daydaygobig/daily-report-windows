"""Application package initialization."""

import os

# Alembic 的 env.py 只需要 ORM 元数据；若在这里导入 main 会执行 create_app()，
# 进而在 alembic 运行期间嵌套触发建库与迁移同步（alembic 全局状态会被打爆）。
if not os.environ.get("ALEMBIC_MIGRATION_ENV"):
    from .main import create_app  # noqa: F401
