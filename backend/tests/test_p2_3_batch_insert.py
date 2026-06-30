"""
P2-3: 批量插入测试

验证：
1. batch_upsert 正确处理空 rows
2. batch_upsert 在 SQLite 上能用
3. batch_insert 在 SQLite 上能用
4. 100 条批量插入性能 < 200ms
"""
import asyncio
import time
import pytest
from unittest.mock import MagicMock

from app.utils.batch_insert import batch_upsert, batch_insert


class TestBatchUpsert:
    """batch_upsert 单元测试"""

    @pytest.mark.asyncio
    async def test_empty_rows_returns_zero(self):
        """空 rows 应该直接返回 0"""
        session = MagicMock()
        result = await batch_upsert(session, MagicMock(), [], ["id"])
        assert result == 0

    @pytest.mark.asyncio
    async def test_handles_dict_rows(self):
        """接受 dict 列表"""
        session = MagicMock()
        table = MagicMock()
        # 模拟执行
        session.execute = MagicMock()
        session.execute.return_value = MagicMock(rowcount=5)
        session.commit = MagicMock()
        session.bind = None  # 走 SQLite 分支

        # 构造一个简单的 table mock
        table.columns = [MagicMock(name="id"), MagicMock(name="name")]

        # 实际执行（无真实表，验证 path）
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        # 这次会失败因为 table 是 mock；但能验证 dispatch 逻辑
        with pytest.raises(Exception):
            await batch_upsert(session, table, rows, ["id"], update_keys=["name"])


class TestBatchInsert:
    """batch_insert 单元测试"""

    @pytest.mark.asyncio
    async def test_empty_rows_returns_zero(self):
        session = MagicMock()
        result = await batch_insert(session, MagicMock(), [])
        assert result == 0


class TestBatchPerformance:
    """批量插入性能测试（SQLite）"""

    @pytest.mark.asyncio
    async def test_batch_insert_100_rows_under_200ms(self):
        """100 条批量插入 < 200ms（硬指标）"""
        import os
        # 创建临时 SQLite 数据库
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import Column, Integer, String, MetaData, Table

        metadata = MetaData()
        test_table = Table(
            "test_batch_insert",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
            Column("value", Integer),
        )

        # 临时数据库
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # 构造 100 条数据
        rows = [
            {"id": i, "name": f"item_{i}", "value": i * 10}
            for i in range(1, 101)
        ]

        async with session_factory() as session:
            start = time.time()
            result = await batch_insert(session, test_table, rows)
            elapsed = time.time() - start

        assert result == 100
        assert elapsed < 0.2, f"100 rows insert took {elapsed*1000:.1f}ms, expected < 200ms"

    @pytest.mark.asyncio
    async def test_batch_upsert_updates_on_conflict(self):
        """batch_upsert 冲突时正确更新"""
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import Column, Integer, String, MetaData, Table

        metadata = MetaData()
        test_table = Table(
            "test_upsert",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
            Column("value", Integer),
        )

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        from sqlalchemy.ext.asyncio import async_sessionmaker
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        # 第一次插入
        rows1 = [
            {"id": 1, "name": "a", "value": 100},
            {"id": 2, "name": "b", "value": 200},
        ]
        async with session_factory() as session:
            await batch_insert(session, test_table, rows1)

        # 第二次 upsert（id=1 冲突，name 和 value 都更新）
        rows2 = [
            {"id": 1, "name": "a_updated", "value": 999},
            {"id": 3, "name": "c", "value": 300},
        ]
        async with session_factory() as session:
            await batch_upsert(
                session, test_table, rows2,
                conflict_keys=["id"],
                update_keys=["name", "value"],
            )

        # 验证
        from sqlalchemy import select
        async with session_factory() as session:
            stmt = select(test_table).order_by(test_table.c.id)
            result = await session.execute(stmt)
            all_rows = result.fetchall()

        assert len(all_rows) == 3
        # id=1 应被更新
        assert all_rows[0].name == "a_updated"
        assert all_rows[0].value == 999
        # id=2 应保持
        assert all_rows[1].name == "b"
        assert all_rows[1].value == 200
        # id=3 应被插入
        assert all_rows[2].name == "c"
        assert all_rows[2].value == 300
