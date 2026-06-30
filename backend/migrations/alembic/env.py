"""Alembic 环境配置 - 异步 SQLAlchemy

支持：
- SQLite（开发环境）
- PostgreSQL（Supabase 生产环境）
- 自动从 .env 读取 DATABASE_URL
- 自动 import 所有模型（autogenerate 可识别）
"""
import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# 让 alembic 能 import app.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import Base  # noqa: E402

# 自动 import 所有模型，确保 autogenerate 能检测到
import app.models  # noqa: F401, E402

config = context.config

# 覆盖 sqlalchemy.url（从 settings 动态读取）
# 同步 URL 用于 alembic 内部（alembic 1.13 仍以 sync 模式跑 migration）
# 但我们用 async 模式：使用 async_engine_from_config
db_url = settings.db_url
# alembic 用同步模式，需要把 async driver 换成 sync driver
sync_url = db_url
if "+asyncpg" in sync_url:
    # 优先用 psycopg2（Postgres 同步驱动），fallback 到 psycopg
    try:
        import psycopg2  # noqa: F401
        sync_url = sync_url.replace("+asyncpg", "+psycopg2")
    except ImportError:
        try:
            import psycopg  # noqa: F401
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        except ImportError:
            # 没有同步驱动，回退到 async 模式（用 run_sync）
            pass
elif "+aiosqlite" in sync_url:
    # SQLite 同步驱动是 sqlite3
    sync_url = sync_url.replace("+aiosqlite", "")

config.set_main_option("sqlalchemy.url", sync_url)

# 解释日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本不执行
    用法：alembic upgrade head --sql > migration.sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite ALTER TABLE 限制
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite 兼容
        compare_type=True,    # 检测列类型变化
        compare_server_default=True,  # 检测默认值变化
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    """异步模式：用 async engine（不需要 psycopg2）"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """入口：自动选择离线/异步模式"""
    # 检查是否有同步驱动，否则用异步模式
    has_sync_pg = False
    try:
        import psycopg2  # noqa: F401
        has_sync_pg = True
    except ImportError:
        try:
            import psycopg  # noqa: F401
            has_sync_pg = True
        except ImportError:
            has_sync_pg = False

    # 如果是 Postgres 且没有 sync 驱动，用异步
    if "postgresql" in sync_url and not has_sync_pg:
        asyncio.run(run_migrations_online_async())
    else:
        # SQLite 或 有同步驱动时，用标准同步模式
        from sqlalchemy import engine_from_config
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
