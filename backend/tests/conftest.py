"""
QA P0 复检 - 公共 fixtures
"""
import asyncio
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.factor_history import FactorHistory  # noqa: F401 – ensure model registered
from app.engine.factor_history import FactorHistoryStore

# ---------------------------------------------------------------------------
# 内存 SQLite 引擎（每个测试函数独立）
# StaticPool 确保 in-memory SQLite 同一连接，避免数据不可见问题
# ---------------------------------------------------------------------------
SQLITE_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def engine():
    """创建内存 SQLite 异步引擎，测试结束后销毁"""
    eng = create_async_engine(
        SQLITE_URL,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    """创建一个绑定到内存 SQLite 的 AsyncSession"""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest_asyncio.fixture
def store():
    """FactorHistoryStore 实例"""
    return FactorHistoryStore()
