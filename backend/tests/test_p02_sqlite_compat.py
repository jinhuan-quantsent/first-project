"""
P0-2 复检：factor_history.py SQLite 兼容性 & 原有功能回归
验证 USE_POSTGRES=False 分支下 INSERT OR IGNORE 语义正确，以及核心查询逻辑无损
"""
import asyncio
from datetime import date, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.factor_history import FactorHistoryStore, _normalize_code
from app.models.factor_history import FactorHistory


# ---------------------------------------------------------------------------
# 辅助：生成距今 N 天前的日期字符串
# ---------------------------------------------------------------------------
def _days_ago(n: int) -> str:
    """返回距今 n 天前的 ISO 日期字符串"""
    return (date.today() - timedelta(days=n)).isoformat()


# ============================================================
# P0-2：SQLite 兼容性测试
# ============================================================

class TestSQLiteCompatibility:
    """验证 SQLite 模式（USE_POSTGRES=False）下所有方法不抛异常"""

    @pytest.mark.asyncio
    async def test_insert_sqlite_mode(self, session: AsyncSession, store: FactorHistoryStore):
        """SQLite 模式下 insert() 不抛异常"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            result = await store.insert(
                session,
                index_code="000001.SH",
                factor_name="波动率",
                trade_date=_days_ago(10),
                raw_value=18.5,
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_insert_batch_sqlite_mode(self, session: AsyncSession, store: FactorHistoryStore):
        """SQLite 模式下 insert_batch() 不抛异常"""
        records = [
            ("000001.SH", "波动率", _days_ago(10), 18.5),
            ("000001.SH", "RSI", _days_ago(10), 55.0),
            ("000001.SH", "新高占比", _days_ago(10), 12.0),
        ]
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            count = await store.insert_batch(session, records)
        assert count == 3

    @pytest.mark.asyncio
    async def test_get_series_sqlite_mode(self, session: AsyncSession, store: FactorHistoryStore):
        """SQLite 模式下 get_series() 不抛异常且返回正确数据"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            await store.insert(session, "000001.SH", "波动率", _days_ago(10), 18.5)
            await store.insert(session, "000001.SH", "波动率", _days_ago(5), 19.2)

            series = await store.get_series(session, "000001.SH", "波动率")
        assert isinstance(series, list)
        assert len(series) >= 2

    @pytest.mark.asyncio
    async def test_get_percentile_sqlite_mode(self, session: AsyncSession, store: FactorHistoryStore):
        """SQLite 模式下 get_percentile() 不抛异常"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            for i in range(70):
                await store.insert(
                    session, "000001.SH", "波动率",
                    _days_ago(200 - i), 10.0 + i * 0.5,
                )

            result = await store.get_percentile(
                session, "000001.SH", "波动率", raw_value=35.0,
            )
        assert result is not None
        assert 0 <= result <= 100

    @pytest.mark.asyncio
    async def test_insert_or_ignore_semantics(self, session: AsyncSession, store: FactorHistoryStore):
        """重复插入同一条记录时不报错（OR IGNORE 语义）"""
        td = _days_ago(10)
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            # 第一次插入
            r1 = await store.insert(
                session, "000001.SH", "波动率", td, 18.5,
            )
            assert r1 is True

            # 重复插入相同记录（唯一约束: index_code + factor_name + trade_date）
            r2 = await store.insert(
                session, "000001.SH", "波动率", td, 18.5,
            )
            # OR IGNORE 语义：不报异常，返回 True（因未抛异常即 commit 成功）
            assert r2 is True

            # 验证只有一条记录
            stmt = select(sa_func.count()).select_from(FactorHistory).where(
                FactorHistory.index_code == "000001.SH",
                FactorHistory.factor_name == "波动率",
                FactorHistory.trade_date == td,
            )
            result = await session.execute(stmt)
            count = result.scalar()
            assert count == 1

    @pytest.mark.asyncio
    async def test_batch_insert_or_ignore_semantics(self, session: AsyncSession, store: FactorHistoryStore):
        """批量插入中含重复记录，OR IGNORE 语义正确"""
        td1 = _days_ago(10)
        td2 = _days_ago(9)
        records = [
            ("000001.SH", "波动率", td1, 18.5),
            ("000001.SH", "RSI", td2, 55.0),
        ]
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            # 第一次批量插入
            c1 = await store.insert_batch(session, records)
            assert c1 == 2

            # 第二次批量插入（完全重复）
            c2 = await store.insert_batch(session, records)
            # batch 方法逐条执行，即使 OR IGNORE，count 仍递增
            assert c2 == 2

            # 验证实际只有 2 条记录（去重后）
            stmt = select(sa_func.count()).select_from(FactorHistory)
            result = await session.execute(stmt)
            total = result.scalar()
            assert total == 2


# ============================================================
# 原有功能回归测试
# ============================================================

class TestRegression:
    """确认修复没有破坏已有查询逻辑"""

    @pytest.mark.asyncio
    async def test_get_series_returns_ascending(self, session: AsyncSession, store: FactorHistoryStore):
        """get_series() 返回按日期升序的序列"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            # 故意乱序插入（使用距今较近的日期，确保在 lookback 窗口内）
            await store.insert(session, "000001.SH", "波动率", _days_ago(5), 30.0)
            await store.insert(session, "000001.SH", "波动率", _days_ago(50), 10.0)
            await store.insert(session, "000001.SH", "波动率", _days_ago(20), 20.0)

            series = await store.get_series(session, "000001.SH", "波动率")

        assert series == [10.0, 20.0, 30.0], f"序列应按日期升序排列，实际: {series}"

    @pytest.mark.asyncio
    async def test_get_percentile_correctness(self, session: AsyncSession, store: FactorHistoryStore):
        """get_percentile() 返回正确的百分位值"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            # 插入 100 条数据，值从 1.0 到 100.0
            for i in range(1, 101):
                await store.insert(
                    session, "000001.SH", "波动率",
                    _days_ago(200 - i), float(i),
                )

            # 值 50.0 应大约在 50% 百分位
            p50 = await store.get_percentile(
                session, "000001.SH", "波动率", raw_value=50.0,
            )
            assert p50 is not None
            assert 45 <= p50 <= 55, f"50th percentile should be ~50, got {p50}"

            # 值 90.0 应大约在 90% 百分位
            p90 = await store.get_percentile(
                session, "000001.SH", "波动率", raw_value=90.0,
            )
            assert p90 is not None
            assert 85 <= p90 <= 95, f"90th percentile should be ~90, got {p90}"

    @pytest.mark.asyncio
    async def test_get_series_count_correctness(self, session: AsyncSession, store: FactorHistoryStore):
        """get_series_count() 返回正确的记录数"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            # 插入 5 条同一因子数据
            for i in range(5):
                await store.insert(
                    session, "000001.SH", "波动率",
                    _days_ago(10 + i), 10.0 + i,
                )

            # 插入 3 条另一因子数据
            for i in range(3):
                await store.insert(
                    session, "000001.SH", "RSI",
                    _days_ago(10 + i), 50.0 + i,
                )

            count_vol = await store.get_series_count(session, "000001.SH", "波动率")
            count_rsi = await store.get_series_count(session, "000001.SH", "RSI")
            count_other = await store.get_series_count(session, "000001.SH", "换手率")

        assert count_vol == 5, f"波动率记录数应为 5，实际 {count_vol}"
        assert count_rsi == 3, f"RSI 记录数应为 3，实际 {count_rsi}"
        assert count_other == 0, f"换手率记录数应为 0，实际 {count_other}"

    @pytest.mark.asyncio
    async def test_get_series_insufficient_data(self, session: AsyncSession, store: FactorHistoryStore):
        """数据不足 60 条时，get_percentile() 返回 None"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            for i in range(30):
                await store.insert(
                    session, "000001.SH", "波动率",
                    _days_ago(30 - i), 10.0 + i,
                )

            result = await store.get_percentile(
                session, "000001.SH", "波动率", raw_value=25.0,
            )

        assert result is None, "数据不足 60 条时应返回 None"

    @pytest.mark.asyncio
    async def test_get_series_empty(self, session: AsyncSession, store: FactorHistoryStore):
        """无数据时 get_series() 返回空列表"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            series = await store.get_series(session, "999999.SH", "波动率")
        assert series == []

    @pytest.mark.asyncio
    async def test_raw_value_rounded(self, session: AsyncSession, store: FactorHistoryStore):
        """insert() 对 raw_value 做 round(value, 4)"""
        with patch("app.engine.factor_history.settings.USE_POSTGRES", False):
            await store.insert(
                session, "000001.SH", "波动率",
                _days_ago(10), 18.5123456,
            )
            series = await store.get_series(session, "000001.SH", "波动率")

        assert len(series) == 1
        assert series[0] == 18.5123, f"raw_value 应为 18.5123（4位小数），实际 {series[0]}"


# ============================================================
# 辅助函数 _normalize_code 回归
# ============================================================

class TestNormalizeCode:
    """_normalize_code 格式转换回归"""

    def test_sh_prefix_to_tushare(self):
        assert _normalize_code("SH000001") == "000001.SH"

    def test_sz_prefix_to_tushare(self):
        assert _normalize_code("SZ399001") == "399001.SZ"

    def test_already_tushare_format(self):
        assert _normalize_code("000001.SH") == "000001.SH"

    def test_unknown_format_passthrough(self):
        assert _normalize_code("ABC123") == "ABC123"
