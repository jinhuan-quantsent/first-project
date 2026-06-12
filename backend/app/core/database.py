"""
数据库引擎配置
SQLAlchemy 2.0 异步引擎 + Session
自动检测环境，支持 PostgreSQL 和 SQLite
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy Base Model"""
    pass


# 全局引擎和会话工厂
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker | None = None


async def init_db() -> None:
    """初始化数据库引擎和表结构"""
    global _engine, _async_session_factory

    db_url = settings.db_url

    # 确保 SQLite 目录存在
    if "sqlite" in db_url:
        sqlite_path = settings.SQLITE_PATH
        os.makedirs(os.path.dirname(os.path.abspath(sqlite_path)), exist_ok=True)

    _engine = create_async_engine(
        db_url,
        echo=settings.DEBUG,
        pool_size=5 if settings.USE_POSTGRES else 1,
        max_overflow=10 if settings.USE_POSTGRES else 0,
        pool_pre_ping=True,
    )

    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # 自动建表（开发模式）
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"✅ 数据库连接成功: {'PostgreSQL' if settings.USE_POSTGRES else 'SQLite'}")


async def close_db() -> None:
    """关闭数据库连接"""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        print("🔌 数据库连接已关闭")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（依赖注入）"""
    if _async_session_factory is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
