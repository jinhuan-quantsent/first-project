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


# ============================================================
# V5.0 新增：11因子元数据配置
# ============================================================
V5_FACTOR_META: list[dict] = [
    {"name": "VOL",  "label": "波动率", "direction": "fear", "weight": 0.12, "source": "index_daily"},
    {"name": "ADR",  "label": "涨跌比", "direction": "greed", "weight": 0.12, "source": "limit_list_d"},
    {"name": "ERP",  "label": "股债性价比", "direction": "fear", "weight": 0.12, "source": "index_dailybasic+bond"},
    {"name": "FLOW", "label": "资金流", "direction": "greed", "weight": 0.10, "source": "fund_daily"},
    {"name": "ETF",  "label": "ETF份额", "direction": "greed", "weight": 0.08, "source": "fund_daily"},
    {"name": "NHNL", "label": "新高占比", "direction": "greed", "weight": 0.08, "source": "index_daily"},
    {"name": "TURN", "label": "换手率", "direction": "fear", "weight": 0.08, "source": "index_dailybasic"},
    {"name": "POS",  "label": "基金仓位", "direction": "greed", "weight": 0.08, "source": "fund_portfolio"},
    {"name": "NBF",  "label": "北向资金", "direction": "greed", "weight": 0.06, "source": "moneyflow_hsgt"},
    {"name": "PCR",  "label": "认沽认购比", "direction": "fear", "weight": 0.04, "source": "opt_daily"},
    {"name": "NEWF", "label": "新发基金热度", "direction": "greed", "weight": 0.04, "source": "fund_basic"},
]


def get_factor_meta(factor_name: str) -> dict | None:
    """根据因子名获取元数据"""
    for meta in V5_FACTOR_META:
        if meta["name"] == factor_name:
            return meta
    return None


def get_all_factor_names() -> list[str]:
    """获取全部11因子名称"""
    return [m["name"] for m in V5_FACTOR_META]


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
        """
        从 Tushare 回填某指数的历史因子数据（V5.0 升级版）
        支持11个V5因子 + COMPOSITE + CLOSE
        """
        import pandas as pd

        end_date = date.today().isoformat().replace("-", "")
        start_date = (date.today() - timedelta(days=lookback_days + 100)).isoformat().replace("-", "")
        ts_code = _normalize_code(index_code)

        try:
            # 1. 获取指数日线数据
            df = tushare_pro.index_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                print(f"⚠️ Tushare index_daily 返回空: {ts_code}")
                return 0

            df = df.sort_values("trade_date").reset_index(drop=True)
            closes = df["close"].values.astype(float)
            volumes = df["vol"].values.astype(float) if "vol" in df.columns else np.ones(len(closes))
            trade_dates = df["trade_date"].values

            # 2. 获取指数基本面数据（换手率、PE等）
            df_basic = None
            try:
                df_basic = tushare_pro.index_dailybasic(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as e:
                print(f"⚠️ index_dailybasic 失败: {e}")

            turnover_map = {}
            pe_map = {}
            if df_basic is not None and not df_basic.empty:
                for _, row in df_basic.iterrows():
                    td = str(row.get("trade_date", ""))
                    turnover_map[td] = float(row.get("turnover_rate", 0))
                    pe_val = row.get("pe")
                    pe_map[td] = float(pe_val) if pe_val else 0

            # 3. 获取融资融券数据
            df_margin = None
            try:
                df_margin = tushare_pro.margin(
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                pass

            margin_map = {}
            if df_margin is not None and not df_margin.empty:
                for _, row in df_margin.iterrows():
                    td = str(row.get("trade_date", ""))
                    margin_map[td] = float(row.get("rzye", 0))

            # 4. 获取北向资金数据
            df_flow = None
            try:
                df_flow = tushare_pro.moneyflow_hsgt(
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception:
                pass

            flow_map = {}
            if df_flow is not None and not df_flow.empty:
                for _, row in df_flow.iterrows():
                    td = str(row.get("trade_date", ""))
                    flow_map[td] = float(row.get("north_money", 0))

            # 5. 逐日计算因子
            records: list[tuple[str, str, str, float]] = []

            for i in range(len(closes)):
                td = str(trade_dates[i])

                # CLOSE: 始终存储
                records.append((ts_code, "CLOSE", td, float(closes[i])))

                if i < 60:
                    continue

                window = closes[max(0, i - 60): i + 1]

                # --- A类因子 ---

                # VOL: 波动率（年化）
                returns = np.diff(window) / window[:-1]
                volatility = float(np.std(returns) * np.sqrt(252) * 100)

                # ADR: 涨跌比（近20日涨/跌天数比）
                if i >= 21:
                    recent_closes = closes[i-20:i+1]  # 21 values
                    recent_returns = np.diff(recent_closes) / recent_closes[:-1]  # 20 returns
                    adv = max(float(np.sum(recent_returns > 0)), 1.0)
                    dec = max(float(np.sum(recent_returns <= 0)), 1.0)
                    adr = round(adv / dec, 4)
                else:
                    adr = 1.0

                # NHNL: 新高占比（收盘价相对60日高点的比例×100）
                high_60 = float(np.max(window))
                current = float(closes[i])
                new_high_ratio = round((current / high_60) * 100, 2)

                # TURN: 换手率
                turnover = turnover_map.get(td, 0.0)

                # ERP: 股债性价比
                pe = pe_map.get(td, 0.0)
                if pe > 0:
                    earnings_yield = 100.0 / pe
                    bond_yield = 2.8  # 近似国债收益率
                    erp = round(earnings_yield - bond_yield, 4)
                else:
                    erp = 0.0

                # --- B类因子 ---

                # FLOW: 北向资金净流入（亿）
                north_flow = flow_map.get(td, 0.0)

                # NBF: 融资余额（万→亿）
                margin_bal = margin_map.get(td, 0.0) / 10000.0

                # --- 组装记录 ---
                records.append((ts_code, "VOL", td, volatility))
                records.append((ts_code, "ADR", td, adr))
                records.append((ts_code, "NHNL", td, new_high_ratio))
                records.append((ts_code, "TURN", td, turnover))
                records.append((ts_code, "ERP", td, erp))
                records.append((ts_code, "FLOW", td, north_flow))
                records.append((ts_code, "NBF", td, margin_bal))

            # 6. 批量插入
            count = await self.insert_batch(session, records)
            print(f"✅ {ts_code} 回填完成: {count} 条记录 (V5.0 7因子+CLOSE)")
            return count

        except Exception as e:
            print(f"⚠️ backfill_from_tushare error for {ts_code}: {e}")
            import traceback
            traceback.print_exc()
            return 0


# 全局单例（延迟初始化）
factor_history = FactorHistoryStore()
