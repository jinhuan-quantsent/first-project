"""
因子历史数据存储与查询
V4.0：从 sqlite3 直连改为 SQLAlchemy async session
延迟初始化 + async context（A1 决策）
"""
from datetime import date, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import select, func as sa_func, text, Insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.models.factor_history import FactorHistory

# 反向因子：值越高越恐慌 → 得分 = 100 - percentile
REVERSE_FACTORS = {"波动率", "RSI"}

# 倒U型因子：适中最好 → 用偏差映射
INVERTED_U_FACTORS = {"换手率", "融资融券"}

DEFAULT_LOOKBACK = 750


def _normalize_code(code: str) -> str:
    """Convert between API format (SH000001) and tushare format (000001.SH)"""
    if code.startswith("SH") and "." not in code:
        return code[2:] + ".SH"
    if code.startswith("SZ") and "." not in code:
        return code[2:] + ".SZ"
    return code


class FactorHistoryStore:
    """因子历史数据存储与查询（async ORM 版）"""

    def __init__(self) -> None:
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """延迟初始化（A1 决策）"""
        if self._initialized:
            return
        # 导入时触发模型注册，确保 Base.metadata 包含 FactorHistory
        from app.models.factor_history import FactorHistory  # noqa: F401
        self._initialized = True

    async def insert(
        self,
        session: AsyncSession,
        index_code: str,
        factor_name: str,
        trade_date: str,
        raw_value: float,
    ) -> bool:
        """插入单条历史记录，唯一约束防重复"""
        try:
            values = dict(
                index_code=index_code,
                factor_name=factor_name,
                trade_date=trade_date,
                raw_value=round(raw_value, 4),
            )
            if settings.USE_POSTGRES:
                # PG 模式：pg_insert + on_conflict_do_nothing（利用 uq_factor_history 唯一约束）
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(FactorHistory).values(**values).on_conflict_do_nothing(
                    constraint="uq_factor_history",
                )
            else:
                # SQLite 模式：INSERT OR IGNORE（语义等价，同样利用唯一约束去重）
                stmt = Insert(FactorHistory).prefix_with("OR IGNORE").values(**values)
            await session.execute(stmt)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            print(f"⚠️ factor_history insert error: {e}")
            return False

    async def insert_batch(
        self,
        session: AsyncSession,
        records: list[tuple[str, str, str, float]],
    ) -> int:
        """批量插入 [(index_code, factor_name, trade_date, raw_value), ...]"""
        count = 0
        try:
            for rec in records:
                values = dict(
                    index_code=rec[0],
                    factor_name=rec[1],
                    trade_date=rec[2],
                    raw_value=round(rec[3], 4),
                )
                if settings.USE_POSTGRES:
                    # PG 模式：pg_insert + on_conflict_do_nothing
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(FactorHistory).values(**values).on_conflict_do_nothing(
                        constraint="uq_factor_history",
                    )
                else:
                    # SQLite 模式：INSERT OR IGNORE
                    stmt = Insert(FactorHistory).prefix_with("OR IGNORE").values(**values)
                await session.execute(stmt)
                count += 1
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"⚠️ factor_history batch insert error: {e}")
        return count

    async def get_series(
        self,
        session: AsyncSession,
        index_code: str,
        factor_name: str,
        lookback_days: int = DEFAULT_LOOKBACK,
    ) -> list[float]:
        """获取历史序列，按日期升序"""
        try:
            cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
            stmt = (
                select(FactorHistory.raw_value)
                .where(
                    FactorHistory.index_code == _normalize_code(index_code),
                    FactorHistory.factor_name == factor_name,
                    FactorHistory.trade_date >= cutoff,
                )
                .order_by(FactorHistory.trade_date.asc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            print(f"⚠️ factor_history get_series error: {e}")
            return []

    async def get_percentile(
        self,
        session: AsyncSession,
        index_code: str,
        factor_name: str,
        raw_value: float,
        lookback_days: int = DEFAULT_LOOKBACK,
    ) -> Optional[float]:
        """
        计算分位数：当前值在历史序列中处于什么位置
        返回 0-100 的百分位，数据不足时返回 None
        """
        series = await self.get_series(session, index_code, factor_name, lookback_days)
        if len(series) < 60:
            return None
        try:
            from scipy import stats
            return stats.percentileofscore(series, raw_value, kind="rank")
        except Exception as e:
            print(f"⚠️ percentileofscore error: {e}")
            return None

    async def get_series_count(
        self,
        session: AsyncSession,
        index_code: str,
        factor_name: str,
    ) -> int:
        """获取某因子某指数的历史数据天数"""
        try:
            stmt = (
                select(sa_func.count())
                .where(
                    FactorHistory.index_code == _normalize_code(index_code),
                    FactorHistory.factor_name == factor_name,
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        except Exception:
            return 0

    async def backfill_from_tushare(
        self,
        session: AsyncSession,
        index_code: str,
        tushare_pro,
        lookback_days: int = DEFAULT_LOOKBACK,
    ) -> int:
        """从 Tushare 回填某指数的历史因子数据"""
        import pandas as pd

        end_date = date.today().isoformat().replace("-", "")
        start_date = (date.today() - timedelta(days=lookback_days + 100)).isoformat().replace("-", "")

        try:
            df = tushare_pro.index_daily(
                ts_code=index_code,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                print(f"⚠️ Tushare index_daily 返回空: {index_code}")
                return 0

            df = df.sort_values("trade_date").reset_index(drop=True)
            closes = df["close"].values
            trade_dates = df["trade_date"].values

            records: list[tuple[str, str, str, float]] = []
            for i in range(len(closes)):
                td = trade_dates[i]
                if i < 60:
                    continue

                window = closes[max(0, i - 60) : i + 1]

                # 波动率（年化）
                returns = np.diff(window) / window[:-1]
                volatility = float(np.std(returns) * np.sqrt(252) * 100)

                # RSI 14日
                if i >= 14:
                    rsi_window = closes[i - 14 : i + 1]
                    diffs = np.diff(rsi_window)
                    gains = np.sum(diffs[diffs > 0]) if np.any(diffs > 0) else 0
                    losses = abs(np.sum(diffs[diffs < 0])) if np.any(diffs < 0) else 0
                    rs = gains / losses if losses > 0 else 100
                    rsi = float(100 - 100 / (1 + rs))
                else:
                    rsi = 50.0

                # 新高占比
                high_60 = float(np.max(window))
                current = float(closes[i])
                new_high_ratio = (
                    round((current / high_60) * 20, 1)
                    if current >= high_60 * 0.95
                    else round((current / high_60) * 10, 1)
                )

                records.append((index_code, "波动率", td, volatility))
                records.append((index_code, "RSI", td, rsi))
                records.append((index_code, "新高占比", td, new_high_ratio))

            count = await self.insert_batch(session, records)
            print(f"✅ {index_code} 回填完成: {count} 条记录 (波动率/RSI/新高占比)")
            return count

        except Exception as e:
            print(f"⚠️ backfill_from_tushare error for {index_code}: {e}")
            return 0


# 全局单例（延迟初始化）
factor_history = FactorHistoryStore()
