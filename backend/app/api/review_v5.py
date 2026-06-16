"""
回测接口 — V5.0 扩展版
策略回测 + 绩效评估 + 5类参数 + 风控统计

数据源：
- 指数日线：Tushare index_daily
- 信号等级：factor_history + V5引擎实时计算

方案持久化：数据库（backtest_strategy 表），V5.0 Phase1 迁移自 JSON 文件
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.core.redis_client import cache_get, cache_set
from app.engine.backtest import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    BacktestMetrics,
    ActionRule,
    RiskParams,
)
from app.models.factor_history import FactorHistory
from app.models.market_sentiment import MarketSentiment
from app.models.backtest_strategy import BacktestStrategy
from app.utils.data_source import data_source
from app.utils.code_format import to_tushare, to_display, INDEX_REGISTRY
import json


router = APIRouter(prefix="/api/v5/backtest")




# ============================================================
# Pydantic 模型
# ============================================================

class ActionMappingItem(BaseModel):
    """行动映射单项"""
    type: str = "hold"
    mult: float = 0.0
    label: str = ""

class BacktestRequest(BaseModel):
    """回测请求 — 5类参数"""
    # 基础参数
    index_code: str = "SH000300"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 100000.0
    signal_strategy: str = "v5_signal"

    # 基金回测参数（可选）
    fund_code: Optional[str] = None  # 如果提供，使用基金净值作为价格数据

    # 逐日追踪模式
    daily_tracking: bool = False  # 是否启用逐日追踪模式

    # Category 1: Signal Mapping
    signal_boundaries: list[float] = [12.0, 25.0, 38.0, 52.0, 65.0, 80.0]
    signal_lag_days: int = 1

    # Category 2: Factor Weights
    factor_weights: dict[str, float] = {}
    factor_enabled: dict[str, bool] = {}

    # Category 3: Action Mapping
    action_mapping: dict[str, ActionMappingItem] = {}

    # Category 4: Factor Engine
    quantile_window: int = 252
    sigmoid_k: float = 3.0
    composite_method: str = "weighted_sum"
    neutral_score: float = 50.0

    # Category 5: Position & Risk
    risk_params: dict = {}

    # 向后兼容
    buy_signals: list[str] = ["S+", "S", "A"]
    sell_signals: list[str] = ["D", "E"]
    hold_signals: list[str] = ["B", "C"]


# ============================================================
# 数据获取：真实数据优先，Mock降级
# ============================================================

# 指数代码映射 — 已迁移至 app.utils.code_format
# _INDEX_CODE_MAP 保留为兼容变量，数据来源统一从 INDEX_REGISTRY 生成
_INDEX_CODE_MAP = {to_display(k): k for k in INDEX_REGISTRY}


async def _get_real_price_data(
    index_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """从Tushare获取真实指数日线数据"""
    ts_code = to_tushare(index_code)

    try:
        if not data_source._tushare_pro:
            return []

        start_dt = start_date.replace("-", "")
        end_dt = end_date.replace("-", "")

        df = data_source._tushare_pro.index_daily(
            ts_code=ts_code,
            start_date=start_dt,
            end_date=end_dt,
        )
        if df is None or df.empty:
            return []

        df = df.sort_values("trade_date", ascending=True)

        result = []
        for _, row in df.iterrows():
            result.append({
                "date": str(row["trade_date"]),
                "close": float(row["close"]),
                "pct_chg": float(row.get("pct_chg", 0) or 0),
                "volume": float(row.get("vol", 0) or 0),
                "signal_level": "B",
            })

        return result

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Tushare指数日线获取失败(%s): %s", ts_code, e)
        return []


async def _get_real_signal_data(
    index_code: str,
    start_date: str,
    end_date: str,
    session: AsyncSession,
) -> dict[str, str]:
    """从factor_history获取V5信号等级"""
    # 统一转换为 Tushare 格式（数据库存储格式）
    ts_index_code = to_tushare(index_code)
    # 转换日期格式：MarketSentiment.trade_date 是 DATE 类型，需传 date 对象
    # FactorHistory.trade_date 是 VARCHAR 类型，需传字符串
    try:
        from datetime import date as date_type
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        start_str = start_date.replace("-", "")
        end_str = end_date.replace("-", "")
    except Exception:
        start_dt = start_date
        end_dt = end_date
        start_str = start_date.replace("-", "") if "-" in start_date else start_date
        end_str = end_date.replace("-", "") if "-" in end_date else end_date

    try:
        stmt = select(
            MarketSentiment.trade_date,
            MarketSentiment.signal_level,
        ).where(
            and_(
                MarketSentiment.index_code == ts_index_code,
                MarketSentiment.trade_date >= start_dt,
                MarketSentiment.trade_date <= end_dt,
            )
        ).order_by(MarketSentiment.trade_date)

        result = await session.execute(stmt)
        rows = result.all()

        if rows:
            return {str(row[0]): str(row[1]) for row in rows if row[1]}

        # 降级：从factor_history的COMPOSITE因子推算
        stmt2 = select(
            FactorHistory.trade_date,
            FactorHistory.raw_value,
        ).where(
            and_(
                FactorHistory.index_code == ts_index_code,
                FactorHistory.factor_name == "COMPOSITE",
                FactorHistory.trade_date >= start_str,
                FactorHistory.trade_date <= end_str,
            )
        ).order_by(FactorHistory.trade_date)

        result2 = await session.execute(stmt2)
        rows2 = result2.all()

        if not rows2:
            return {}

        def score_to_signal(score: float) -> str:
            if score >= 90: return "S+"
            elif score >= 80: return "S"
            elif score >= 65: return "A"
            elif score >= 40: return "B"
            elif score >= 25: return "C"
            elif score >= 10: return "D"
            else: return "E"

        return {str(row[0]): score_to_signal(float(row[1])) for row in rows2}

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("factor_history信号获取失败(%s): %s", index_code, e)
        return {}


async def _get_fund_price_data(
    fund_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """从Tushare获取基金净值作为价格数据（用于单基金回测）
    
    使用Tushare fund_nav直接按日期范围查询，支持历史回测
    """
    ts_code = _convert_fund_code(fund_code)

    start_dt_str = start_date.replace("-", "")
    end_dt_str = end_date.replace("-", "")

    try:
        if not data_source._tushare_pro:
            return []

        # 尝试不同后缀（场外.OF / 场内.SH/.SZ）
        base_code = ts_code.split(".")[0] if "." in ts_code else ts_code
        suffix = ts_code.split(".")[-1] if "." in ts_code else "OF"
        suffixes = [suffix]
        if suffix == "OF":
            suffixes.extend(["SH", "SZ"])
        elif suffix in ("SH", "SZ"):
            suffixes.append("OF")

        for suf in suffixes:
            try_code = f"{base_code}.{suf}"
            try:
                # 直接用日期范围查询，不受"最近N天"限制
                df = data_source._tushare_pro.fund_nav(
                    ts_code=try_code,
                    start_date=start_dt_str,
                    end_date=end_dt_str,
                )
                if df is None or df.empty:
                    continue

                df = df.sort_values("nav_date", ascending=True)

                result = []
                for _, row in df.iterrows():
                    unit_nav = float(row.get("unit_nav", 0) or 0)
                    adj_nav = float(row.get("adj_nav", 0) or 0)
                    nav_date = str(row.get("nav_date", ""))

                    # 计算日收益率
                    daily_ret = 0.0
                    if len(result) > 0 and adj_nav > 0 and result[-1].get("_adj_nav", 0) > 0:
                        prev_adj = result[-1]["_adj_nav"]
                        daily_ret = round((adj_nav / prev_adj - 1) * 100, 2)

                    # 使用复权净值作为close（更准确反映收益）
                    close_val = adj_nav if adj_nav > 0 else unit_nav
                    if close_val <= 0:
                        continue

                    result.append({
                        "date": nav_date,
                        "close": close_val,
                        "pct_chg": daily_ret,
                        "volume": 0,
                        "signal_level": "B",
                        "_adj_nav": adj_nav,  # 内部用，计算收益率
                    })

                # 清理内部字段
                for item in result:
                    item.pop("_adj_nav", None)

                return result

            except Exception as e:
                import logging
                logging.getLogger(__name__).debug("fund_nav %s 尝试失败: %s", try_code, e)
                continue

        return []

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("基金净值获取失败(%s): %s", ts_code, e)
        return []


def _convert_fund_code(code: str) -> str:
    """6位基金代码 → Tushare格式（委托给 code_format.to_tushare）"""
    return to_tushare(code)


def _generate_mock_price_data(
    index_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """生成 Mock 价格数据"""
    import random

    random.seed(hash(index_code))
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    data = []
    price = 3000.0
    current = start
    signal_levels = ["S+", "S", "A", "B", "C", "D", "E"]
    signal = "B"

    while current <= end:
        if current.weekday() < 5:
            change = (random.random() - 0.48) * 2.0
            price *= (1 + change / 100)
            price = max(price * 0.95, price)

            if random.random() < 0.1:
                idx = signal_levels.index(signal)
                delta = random.choice([-1, 0, 1])
                new_idx = max(0, min(6, idx + delta))
                signal = signal_levels[new_idx]

            data.append({
                "date": current.strftime("%Y-%m-%d"),
                "close": round(price, 2),
                "signal_level": signal,
            })

        current += timedelta(days=1)

    return data


# ============================================================
# 逐日追踪回测辅助函数
# ============================================================

async def _compute_signals_from_index(
    index_code: str,
    start_date: str,
    end_date: str,
    factor_weights: dict[str, float] | None = None,
    factor_enabled: dict[str, bool] | None = None,
    signal_boundaries: list[float] | None = None,
) -> dict[str, dict]:
    """
    从指数历史日线实时计算信号（当数据库无历史信号时使用）

    计算逻辑（基于价格动量的简化信号）：
    1. RSI(14): 标准RSI → 反转映射（低RSI=恐惧=高分数）
    2. 近20日涨跌幅: 涨多=贪婪=低分数
    3. 近20日波动率: 高波动=恐惧=高分数
    三因子加权 → 综合分数 → 7级信号

    支持自定义因子权重和信号边界。
    """

    # 因子权重映射：前端11因子 → 后端5个计算因子权重
    # 返回值: (rsi_w, ret20_w, vol_w, mom_w, dd_w, trend_w)
    def _map_weights(fw: dict[str, float] | None, fe: dict[str, bool] | None):
        if not fw:
            return 0.20, 0.20, 0.10, 0.15, 0.25, 0.10
        # 映射表：前端因子名 → 后端计算因子索引
        mapping = {
            "RSI": 0, "VOL": 2, "ADR": 1, "NHNL": 4,
            "TURN": 2, "FLOW": 5, "ETF": 3, "ERP": 4,
            "POS": 1, "NBF": 0, "PCR": 4, "NEWF": 5,
        }
        raw = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for fname, fweight in fw.items():
            idx = mapping.get(fname, -1)
            if idx >= 0 and (not fe or fe.get(fname, True)):
                raw[idx] += fweight
        total = sum(raw)
        if total > 0:
            return tuple(x / total for x in raw)
        return 0.20, 0.20, 0.10, 0.15, 0.25, 0.10

    ts_code = to_tushare(index_code)

    try:
        if not data_source._tushare_pro:
            return {}

        # 需要额外的历史数据做RSI/波动率计算，往前多取30天
        extended_start_dt = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=45)).strftime("%Y%m%d")
        end_dt = end_date.replace("-", "")

        df = data_source._tushare_pro.index_daily(
            ts_code=ts_code,
            start_date=extended_start_dt,
            end_date=end_dt,
        )
        if df is None or df.empty:
            return {}

        df = df.sort_values("trade_date", ascending=True)
        closes = df["close"].tolist()
        dates = df["trade_date"].tolist()
        pct_chgs = df.get("pct_chg", df["close"].pct_change() * 100).tolist()

        # 计算RSI(14)
        def calc_rsi(changes: list[float], period: int = 14) -> list[float]:
            rsi_values = []
            for i in range(len(changes)):
                if i < period:
                    rsi_values.append(50.0)  # 默认中性
                    continue
                gains = [c for c in changes[i-period:i] if c > 0]
                losses = [-c for c in changes[i-period:i] if c < 0]
                avg_gain = sum(gains) / period if gains else 0
                avg_loss = sum(losses) / period if losses else 0.0001
                rs = avg_gain / avg_loss
                rsi_values.append(100 - 100 / (1 + rs))
            return rsi_values

        rsi_list = calc_rsi(pct_chgs)

        # 计算近20日涨跌幅和波动率
        def calc_20day_metrics(closes_list: list[float], dates_list: list[str],
                               start_dt_str: str) -> dict[str, dict]:
            result = {}
            for i in range(len(closes_list)):
                date_str = str(dates_list[i])
                if date_str < start_dt_str:
                    continue

                # 近20日涨跌幅
                if i >= 20:
                    ret_20 = (closes_list[i] / closes_list[i-20] - 1) * 100
                else:
                    ret_20 = 0.0

                # 近20日波动率（日收益率标准差 * sqrt(252))
                if i >= 20:
                    recent_returns = [(closes_list[j] / closes_list[j-1] - 1) for j in range(i-19, i+1)]
                    vol_20 = (sum(r**2 for r in recent_returns) / len(recent_returns) ** 0.5) * (252 ** 0.5) * 100
                else:
                    vol_20 = 20.0  # 默认中等波动

                # 近5日涨跌幅（短期动量）
                if i >= 5:
                    ret_5 = (closes_list[i] / closes_list[i-5] - 1) * 100
                else:
                    ret_5 = 0.0

                rsi = rsi_list[i] if i < len(rsi_list) else 50.0

                # 距60日峰值跌幅: 如果价格远低于近期高点 → 恐惧加剧
                peak_60 = max(closes_list[max(0, i-59):i+1]) if i > 0 else closes_list[i]
                drawdown_from_peak = (closes_list[i] / peak_60 - 1) * 100 if peak_60 > 0 else 0.0

                result[date_str] = {
                    "rsi": rsi,
                    "ret_20": ret_20,
                    "ret_5": ret_5,
                    "vol_20": vol_20,
                    "drawdown": drawdown_from_peak,
                }
            return result

        start_dt_str = start_date.replace("-", "")
        metrics = calc_20day_metrics(closes, dates, start_dt_str)

        # 综合分数计算（5因子+趋势+回撤，高灵敏度）
        # 恐惧(高分数) = 低RSI + 跌得多 + 高波动 + 价格低于均线 + 距峰值远
        # 贪婪(低分数) = 高RSI + 涨得多 + 低波动 + 价格高于均线 + 创新高
        signals = {}
        for date_str, m in metrics.items():
            # 1. RSI反转: 放大偏离度2x → 更灵敏
            rsi_dev = (m["rsi"] - 50) * 2.0
            rsi_score = max(0, min(100, 50 - rsi_dev))

            # 2. 近20日涨跌幅: 7x灵敏度
            # -7%→99(恐惧), +7%→1(贪婪), 0%→50(中性)
            ret_score = max(0, min(100, 50 - m["ret_20"] * 7))

            # 3. 波动率: 15%→50, 25%→75, 35%→100
            vol_score = max(0, min(100, 50 + (m["vol_20"] - 15) * 2.5))

            # 4. 近5日动量: 10x灵敏度（日度波动更敏感）
            mom_score = max(0, min(100, 50 - m["ret_5"] * 10))

            # 5. 距60日峰值回撤: 跌5%→60分(偏恐), 跌10%→80分(恐), 跌15%→95分(极恐)
            # 创新高→15分(极贪)
            dd_score = max(0, min(100, 50 - m["drawdown"] * 3))

            # 趋势检测: 价格与20日均线的关系
            date_idx = dates.index(date_str) if date_str in dates else -1
            trend_bonus = 0
            if date_idx >= 20:
                ma20 = sum(closes[date_idx-19:date_idx+1]) / 20
                current_close = closes[date_idx]
                dev_pct = (current_close / ma20 - 1) * 100
                trend_bonus = max(-20, min(20, -dev_pct * 3))

            # 加权聚合: 使用自定义因子权重（如提供）
            w_rsi, w_ret, w_vol, w_mom, w_dd, w_trend = _map_weights(factor_weights, factor_enabled)
            raw_composite = rsi_score * w_rsi + ret_score * w_ret + vol_score * w_vol + mom_score * w_mom + dd_score * w_dd + trend_bonus * w_trend
            composite = raw_composite

            # 分数→信号等级（支持自定义边界）
            def _score_to_signal(s: float) -> str:
                # signal_boundaries: [B_upper, A_upper, S_upper, S+_upper, C_upper, D_upper]
                # 实际含义: E≤D_upper<D_upper<C_upper≤B_upper≤A_upper≤S_upper≤S+_upper
                # 简化: boundaries = [E_max, D_max, C_max, B_max, A_max, S_max]
                # 分数 >= threshold 时返回对应信号
                b = signal_boundaries if signal_boundaries and len(signal_boundaries) >= 6 else [12.0, 25.0, 38.0, 52.0, 65.0, 82.0]
                if s >= b[5]: return "S+"
                elif s >= b[4]: return "S"
                elif s >= b[3]: return "A"
                elif s >= b[2]: return "B"
                elif s >= b[1]: return "C"
                elif s >= b[0]: return "D"
                else: return "E"

            signal_level = _score_to_signal(composite)
            signals[date_str] = {
                "signal_level": signal_level,
                "composite_score": round(composite, 1),
                "_source": "computed",  # 标记为计算而非数据库
            }

        return signals

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("实时信号计算失败(%s): %s", index_code, e)
        return {}

def _generate_daily_action(
    signal_level: Optional[str],
    score: Optional[float],
    current_cash: float,
    current_position: float,
    initial_capital: float,
    custom_action_map: dict[str, dict] | None = None,
) -> tuple[str, int, str]:
    """
    根据因子信号生成操作建议 — 完全由因子驱动，无人为干预

    核心规则:
    - buy金额 = current_cash × ratio，根据手上现金决定加仓力度
      - 现金不够 → 全部买入（买到底）
      - 没钱了 → hold，不买
    - sell金额 = current_position × ratio，按剩余仓位比例卖出
    - C级映射sell而非hold（与backtest.py DEFAULT_ACTION_MAPPING对齐）
    - E级 = 清仓，策略结束
    - 亏完或清仓 → 策略结束，不重建仓位

    支持自定义 action_mapping（来自前端因子方案）。
    """
    # 信号→操作映射: (action, pct_ratio, is_clear)
    # buy: ratio相对于current_cash（根据手上现金决定加仓多少）
    # sell: ratio相对于current_position（按剩余仓位比例减仓）
    # E: 清仓
    default_map: dict[str, tuple[str, float, bool]] = {
        "S+": ("buy",  0.30, False),
        "S":  ("buy",  0.20, False),
        "A":  ("buy",  0.10, False),
        "B":  ("hold", 0,    False),
        "C":  ("sell", 0.10, False),
        "D":  ("sell", 0.20, False),
        "E":  ("sell", 1.00, True),
    }

    # 使用自定义映射（如提供）
    if custom_action_map:
        # 前端格式: {level: ActionMappingItem} → 后端格式: {level: (action, ratio, is_clear)}
        # ActionMappingItem 是 Pydantic 模型，用 .type/.mult 属性访问，不是 dict.get()
        action_map: dict[str, tuple[str, float, bool]] = {}
        for level, item in custom_action_map.items():
            # 兼容 dict 和 Pydantic 模型两种格式
            if hasattr(item, 'type'):
                action_type = item.type
                mult = item.mult
            elif isinstance(item, dict):
                action_type = item.get("type", "hold")
                mult = item.get("mult", 0)
            else:
                action_type = "hold"
                mult = 0
            is_clear = (action_type == "sell_all" or mult >= 1.0)
            ratio = mult if action_type == "buy" else (mult if 0 < mult < 1 else (1.0 if is_clear else 0.1))
            action_map[level] = (action_type if action_type != "sell_all" else "sell", ratio, is_clear)
        # 确保所有7级都有映射
        for level in ["S+", "S", "A", "B", "C", "D", "E"]:
            if level not in action_map:
                action_map[level] = default_map[level]
    else:
        action_map = default_map

    default_action = ("hold", 0, False)
    result = action_map.get(signal_level or "", default_action)
    if signal_level and signal_level not in action_map:
        result = default_action
    action, ratio, is_clear = result

    safe_score = score if score is not None else 50.0

    signal_meanings: dict[str, str] = {
        "S+": "极度恐惧", "S": "恐惧", "A": "偏恐惧",
        "B": "中性", "C": "偏贪婪", "D": "贪婪", "E": "极度贪婪",
    }
    meaning = signal_meanings.get(signal_level or "", "未知")

    amount = 0
    reason = f"{signal_level}级({meaning})分数{safe_score} → 持有"  # 默认，保证所有分支都能 return

    if action == "hold":
        reason = f"{signal_level}级({meaning})分数{safe_score} → 持有"

    elif action == "buy":
        # 加仓金额 = current_cash × ratio（根据手上现金决定）
        target_amount = round(current_cash * ratio)
        if current_cash <= 0:
            # 没钱了，不买
            action = "hold"
            amount = 0
            reason = f"{signal_level}级({meaning})分数{safe_score} → 建议加仓，现金已耗尽，持有"
        elif target_amount <= 0:
            # 金额太小（现金极少），全部买入
            amount = round(current_cash)
            if amount <= 0:
                action = "hold"
                amount = 0
                reason = f"{signal_level}级({meaning})分数{safe_score} → 建议加仓，现金不足，持有"
            else:
                reason = f"{signal_level}级({meaning})分数{safe_score} → 现金不足，全部买入{amount}元"
        else:
            amount = target_amount
            reason = f"{signal_level}级({meaning})分数{safe_score} → 加仓{amount}元({ratio*100:.0f}%现金)"

    elif action == "sell":
        if is_clear:
            # E级清仓
            amount = round(current_position)
            if amount <= 0:
                action = "hold"
                amount = 0
                reason = f"{signal_level}级({meaning})分数{safe_score} → 建议清仓，持仓已空，策略结束"
            else:
                reason = f"{signal_level}级({meaning})分数{safe_score} → 清仓{amount}元，策略结束"
        else:
            # C/D级减仓 = position × ratio
            amount = round(current_position * ratio)
            if amount <= 0 or current_position <= 0:
                action = "hold"
                amount = 0
                reason = f"{signal_level}级({meaning})分数{safe_score} → 建议减仓，持仓已空，持有"
            else:
                reason = f"{signal_level}级({meaning})分数{safe_score} → 减仓{amount}元({ratio*100:.0f}%仓位)"

    return action, amount, reason


async def _get_signal_for_date(
    date_str: str,
    index_code: str,
    session: AsyncSession,
) -> dict:
    """
    获取指定日期的情绪信号

    优先从 market_sentiment 表精确查询，
    查不到就返回最近一天的数据（前向填充），
    都没有则返回默认中性信号。
    """
    import logging
    _logger = logging.getLogger(__name__)

    # 统一转换为 Tushare 格式（数据库存储格式）
    ts_index_code = to_tushare(index_code)
    # 转换日期：MarketSentiment.trade_date 是 DATE，FactorHistory.trade_date 是 VARCHAR
    date_str_clean = date_str.replace("-", "")
    try:
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date() if "-" in date_str else datetime.strptime(date_str, "%Y%m%d").date()
    except Exception:
        query_date = date_str

    # 1. 尝试从 market_sentiment 表精确查询
    try:
        stmt = select(
            MarketSentiment.signal_level,
            MarketSentiment.composite_score,
        ).where(
            and_(
                MarketSentiment.index_code == ts_index_code,
                MarketSentiment.trade_date == query_date,
            )
        )
        result = await session.execute(stmt)
        row = result.first()
        if row and row[0]:
            return {"signal_level": str(row[0]), "composite_score": float(row[1]) if row[1] else 50.0}
    except Exception as e:
        _logger.debug("market_sentiment精确查询失败(%s): %s", date_str, e)

    # 2. 尝试 factor_history 表（COMPOSITE因子）
    try:
        stmt2 = select(
            FactorHistory.raw_value,
        ).where(
            and_(
                FactorHistory.index_code == ts_index_code,
                FactorHistory.factor_name == "COMPOSITE",
                FactorHistory.trade_date == date_str_clean,
            )
        )
        result2 = await session.execute(stmt2)
        row2 = result2.first()
        if row2 and row2[0] is not None:
            score = float(row2[0])
            def _score_to_signal(s: float) -> str:
                if s >= 90: return "S+"
                elif s >= 80: return "S"
                elif s >= 65: return "A"
                elif s >= 40: return "B"
                elif s >= 25: return "C"
                elif s >= 10: return "D"
                else: return "E"
            return {"signal_level": _score_to_signal(score), "composite_score": score}
    except Exception as e:
        _logger.debug("factor_history精确查询失败(%s): %s", date_str, e)

    # 3. 前向填充：查最近一天的数据
    try:
        stmt3 = select(
            MarketSentiment.trade_date,
            MarketSentiment.signal_level,
            MarketSentiment.composite_score,
        ).where(
            and_(
                MarketSentiment.index_code == ts_index_code,
                MarketSentiment.trade_date < query_date,
            )
        ).order_by(MarketSentiment.trade_date.desc()).limit(1)
        result3 = await session.execute(stmt3)
        row3 = result3.first()
        if row3 and row3[1]:
            return {"signal_level": str(row3[1]), "composite_score": float(row3[2]) if row3[2] else 50.0}
    except Exception as e:
        _logger.debug("前向填充查询失败(%s): %s", date_str, e)

    # 4. 降级返回中性信号
    return {"signal_level": "B", "composite_score": 50.0}


async def _run_daily_tracking_backtest(
    req: BacktestRequest,
    session: AsyncSession,
) -> dict:
    """
    逐日持仓追踪回测

    逻辑:
    1. 获取基金历史日线净值（从start_date到end_date）
    2. 预计算整个回测区间的市场信号（数据库优先 → 实时计算降级）
    3. 对每一天(除第一天外)，根据信号生成操作建议
    4. 计算每日持仓市值 = 前日持仓市值 * (1 + 日收益率) + 当日操作金额
    5. 返回完整的每日日志
    """
    import logging
    _logger = logging.getLogger(__name__)

    # Step 1: 获取基金净值历史
    nav_data_raw = await _get_fund_price_data(req.fund_code or "", req.start_date, req.end_date)
    if not nav_data_raw or len(nav_data_raw) < 5:
        # 降级使用指数数据
        nav_data_raw = await _get_real_price_data(req.index_code, req.start_date, req.end_date)
    if not nav_data_raw or len(nav_data_raw) < 5:
        return {
            "code": 400,
            "data": None,
            "message": "基金历史数据不足5天，无法进行逐日回测",
        }

    # 构建净值列表
    nav_data = []
    for item in nav_data_raw:
        nav_data.append({
            "date": item["date"],
            "nav": float(item.get("close", 0)),
            "pct_chg": float(item.get("pct_chg", 0) or 0),
        })

    # Step 2: 预计算信号 — 数据库优先，实时计算降级
    signal_index_code = "SH000300"  # 基金回测始终使用沪深300信号

    # 2a. 先尝试从数据库批量获取信号（快）
    signal_map_db = await _get_real_signal_data(signal_index_code, req.start_date, req.end_date, session)

    # 2b. 如果数据库信号覆盖率 < 50%，则用实时计算补充/替代（避免全是B/50.0）
    signal_map = {}
    nav_dates = set(item["date"] for item in nav_data)
    db_coverage = len(set(signal_map_db.keys()) & nav_dates) / max(len(nav_dates), 1) if signal_map_db else 0

    if db_coverage >= 0.5:
        # 数据库覆盖率足够，使用数据库信号
        signal_map = signal_map_db
        _logger.info("回测信号: 数据库覆盖率 %.0f%%，使用数据库信号", db_coverage * 100)
    else:
        # 数据库覆盖率不足，实时计算信号
        signal_map = await _compute_signals_from_index(
            signal_index_code, req.start_date, req.end_date,
            req.factor_weights or None, req.factor_enabled or None, req.signal_boundaries or None,
        )
        _logger.info("回测信号: 数据库覆盖率 %.0f%%不足，使用实时计算信号(%d天)", db_coverage * 100, len(signal_map))
        # 如果实时计算也失败，仍然尝试数据库（即使覆盖率低，也比全是B好）
        if not signal_map and signal_map_db:
            signal_map = signal_map_db

    # Step 3: 逐日计算 — cash + position 双轨制
    # Day1建仓50% of initial，剩余50%留作加仓弹药
    initial_position = round(req.initial_capital * 0.50)
    initial_cash = req.initial_capital - initial_position

    cash = initial_cash
    position_value = initial_position  # 持仓市值（随净值涨跌）
    portfolio_value = cash + position_value
    daily_records = []
    strategy_ended = False  # 清仓/亏完 → 策略结束标记

    # 基准线（买入不动）
    benchmark_nav_start = nav_data[0]["nav"] if nav_data else 1.0

    for i, day in enumerate(nav_data):
        date = day["date"]
        nav = day["nav"]

        if i == 0:
            # Day 1: 建仓50%
            action = "buy"
            action_amount = initial_position
            signal_level = "B"
            signal_score = 50.0
            daily_return_pct = 0.0
            reason = f"建仓日：投入{initial_position}元(50%)，预留{initial_cash}元作加仓弹药"
            # state: cash=initial_cash, position=initial_position
        elif strategy_ended:
            # 策略已结束（清仓或亏完），后续只记录空仓状态
            signal_level = "—"
            signal_score = None
            action = "hold"
            action_amount = 0
            daily_return_pct = 0.0
            reason = "策略已结束"
            portfolio_value = cash + position_value
        else:
            # 获取当天信号
            date_key = date.replace("-", "") if "-" in date else date
            signal_info = signal_map.get(date_key, {"signal_level": "B", "composite_score": 50.0})
            signal_level = signal_info.get("signal_level")
            signal_score = signal_info.get("composite_score")

            # 计算日收益率（基于净值变化）→ 持仓市值随涨跌
            prev_nav = nav_data[i - 1]["nav"]
            if prev_nav > 0 and nav > 0:
                daily_return_pct = round((nav / prev_nav - 1) * 100, 2)
            else:
                daily_return_pct = 0.0

            # 持仓市值随净值涨跌
            position_value = position_value * (1 + daily_return_pct / 100.0)
            portfolio_value = cash + position_value

            # 根据因子信号生成操作建议
            action, action_amount, reason = _generate_daily_action(
                signal_level, signal_score, cash, position_value, req.initial_capital,
                req.action_mapping or None,
            )

            # 执行操作，更新cash和position
            if action == "buy" and action_amount > 0:
                actual_buy = min(action_amount, round(cash))  # 不能超过现金
                cash -= actual_buy
                position_value += actual_buy
                action_amount = actual_buy  # 记录实际买入金额
                portfolio_value = cash + position_value
            elif action == "sell" and action_amount > 0:
                actual_sell = min(action_amount, round(position_value))  # 不能超过持仓
                cash += actual_sell
                position_value -= actual_sell
                position_value = max(position_value, 0)
                action_amount = actual_sell  # 记录实际卖出金额
                portfolio_value = cash + position_value

                # E级清仓 → 策略结束
                if signal_level == "E":
                    strategy_ended = True

            # 检查策略是否自然结束（亏完）
            if position_value <= 1 and cash <= 1:
                strategy_ended = True
                # 修正金额为0
                position_value = max(position_value, 0)
                cash = max(cash, 0)
                portfolio_value = cash + position_value

        daily_records.append({
            "date": date,
            "signal_level": signal_level,
            "signal_score": signal_score,
            "action": action,
            "action_amount": action_amount if action not in ("hold", "none") else 0,
            "nav": nav,
            "portfolio_value": round(portfolio_value, 2),
            "cash": round(cash, 2),
            "position_value": round(position_value, 2),
            "daily_return_pct": daily_return_pct,
            "reason": reason,
        })

    # 计算汇总
    final_portfolio = round(portfolio_value, 2)
    total_return_pct = round((portfolio_value / req.initial_capital - 1) * 100, 2)

    # 操作统计
    buy_count = sum(1 for r in daily_records if r["action"] == "buy")
    sell_count = sum(1 for r in daily_records if r["action"] == "sell")
    hold_count = sum(1 for r in daily_records if r["action"] == "hold")
    none_count = sum(1 for r in daily_records if r["action"] == "none")
    action_count = buy_count + sell_count

    # 基准收益
    if len(nav_data) >= 2 and benchmark_nav_start > 0:
        benchmark_final_nav = nav_data[-1]["nav"]
        benchmark_return_pct = round((benchmark_final_nav / benchmark_nav_start - 1) * 100, 2)
    else:
        benchmark_return_pct = 0.0

    # 构建权益曲线
    equity_curve = [
        {
            "date": r["date"],
            "value": r["portfolio_value"],
            "signal_level": r["signal_level"],
        }
        for r in daily_records
    ]

    # 构建基准曲线（买入不动）
    benchmark_curve = []
    if len(nav_data) >= 2 and benchmark_nav_start > 0:
        for i, day in enumerate(nav_data):
            bench_value = req.initial_capital * (day["nav"] / benchmark_nav_start)
            benchmark_curve.append({
                "date": day["date"],
                "value": round(bench_value, 2),
            })

    # 操作汇总文字
    summary_parts = [f"共执行{action_count}次操作"]
    if buy_count > 0:
        summary_parts.append(f"加仓{buy_count}次")
    if sell_count > 0:
        summary_parts.append(f"减仓{sell_count}次")
    if hold_count > 0:
        summary_parts.append(f"持有{hold_count}次")

    # 找最大操作
    max_buy = max((r for r in daily_records if r["action"] == "buy"), key=lambda r: r["action_amount"], default=None)
    max_sell = max((r for r in daily_records if r["action"] == "sell"), key=lambda r: r["action_amount"], default=None)
    if max_buy:
        summary_parts.append(f"最大单日加仓+{max_buy['action_amount']}元发生在{max_buy['date'][:4]}-{max_buy['date'][4:6]}-{max_buy['date'][6:8]}({max_buy['signal_level']}级信号)")
    if max_sell:
        summary_parts.append(f"最大单日减仓-{max_sell['action_amount']}元发生在{max_sell['date'][:4]}-{max_sell['date'][4:6]}-{max_sell['date'][6:8]}({max_sell['signal_level']}级信号)")

    summary_parts.append(f"整体策略偏向'恐惧加仓、贪婪减仓'的逆向操作，最终收益{total_return_pct:+.1f}%")
    summary_text = "，".join(summary_parts)

    return {
        "code": 0,
        "data": {
            "total_return": total_return_pct,
            "annual_return": 0.0,  # 逐日模式暂不计算年化
            "max_drawdown": 0.0,   # 逐日模式暂不计算回撤
            "sharpe_ratio": 0.0,
            "win_rate": 0.0,
            "benchmark_return": benchmark_return_pct,
            "signal_accuracy": 0.0,
            "equity_curve": equity_curve,
            "benchmark_curve": benchmark_curve,
            "trades": [],
            "daily_log": [],
            "risk_stats": None,
            "summary_text": summary_text,
            "_data_source": "daily_tracking",
            "index_code": req.index_code,
            "start_date": req.start_date,
            "end_date": req.end_date,
            # 逐日追踪特有字段
            "daily_tracking": daily_records,
            "initial_capital": req.initial_capital,
            "final_portfolio_value": final_portfolio,
            "tracking_total_return_pct": total_return_pct,
            "tracking_action_count": action_count,
        },
        "message": "ok",
    }


# ============================================================
# API 接口
# ============================================================

@router.post("/run")
async def run_backtest(
    req: BacktestRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    运行策略回测 — 支持5类参数

    数据源降级链：Tushare真实日线 + factor_history信号 → Mock
    """
    # 检查缓存（包含 action_mapping 的 hash，避免参数变化但命中旧缓存）
    import hashlib
    action_hash = hashlib.md5(str(req.action_mapping).encode()).hexdigest()[:8]
    cache_k = f"backtest:{req.index_code}:{req.fund_code or ''}:{req.start_date}:{req.end_date}:{req.signal_strategy}:{action_hash}:{hash(str(req.risk_params))}"
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    # 日期格式验证：start_date 不能大于 end_date
    if req.start_date > req.end_date:
        return {
            "code": 400,
            "data": None,
            "message": f"开始日期({req.start_date})不能晚于结束日期({req.end_date})",
        }

    # 逐日追踪模式：当 daily_tracking=True 且 fund_code 存在时
    if req.daily_tracking and req.fund_code:
        return await _run_daily_tracking_backtest(req, session)

    # 基金代码验证：如果不在已知映射中，给出警告但不阻断
    import logging
    _logger = logging.getLogger(__name__)
    if req.index_code not in _INDEX_CODE_MAP:
        _logger.warning("回测使用未知指数代码: %s，将尝试直接转换", req.index_code)

    # 1. 获取价格数据：如果 fund_code 存在，使用基金净值；否则使用指数日线
    if req.fund_code:
        price_data = await _get_fund_price_data(req.fund_code, req.start_date, req.end_date)
    else:
        price_data = await _get_real_price_data(req.index_code, req.start_date, req.end_date)

    # 2. 获取信号数据：基金回测时使用沪深300的市场情绪（基金没有自己的信号等级）
    signal_index_code = "SH000300" if req.fund_code else req.index_code
    signal_map = await _get_real_signal_data(signal_index_code, req.start_date, req.end_date, session)

    # 3. 合并信号到价格数据
    if price_data and signal_map:
        for item in price_data:
            date_key = item["date"].replace("-", "")
            if date_key in signal_map:
                item["signal_level"] = signal_map[date_key]
    elif not price_data:
        price_data = _generate_mock_price_data(req.index_code, req.start_date, req.end_date)

    # 4. 构建行动映射（空请求 → 使用默认映射）
    from app.engine.backtest import DEFAULT_ACTION_MAPPING
    action_mapping = {k: ActionRule(**v) for k, v in DEFAULT_ACTION_MAPPING.items()}
    for signal, item in req.action_mapping.items():
        action_mapping[signal] = ActionRule(
            action_type=item.type,
            multiplier=item.mult,
            label=item.label,
        )

    # 5. 构建风控参数
    rp = req.risk_params
    risk_params = RiskParams(
        max_position=rp.get("max_position", 0.95),
        min_position=rp.get("min_position", 0.05),
        pullback_add=rp.get("pullback_add", -0.10),
        pullback_add_pct=rp.get("pullback_add_pct", 0.20),
        take_profit=rp.get("take_profit", 0.20),
        take_profit_drawdown=rp.get("take_profit_drawdown", 0.08),
        overheat_days=rp.get("overheat_days", 10),
        overheat_factor=rp.get("overheat_factor", 0.7),
        pullback_lower=rp.get("pullback_lower", -0.08),
        pullback_buy_mult=rp.get("pullback_buy_mult", 0.5),
        position_dev_lower=rp.get("position_dev_lower", -0.05),
        position_dev_buy_mult=rp.get("position_dev_buy_mult", 0.3),
        base_buy_amount=rp.get("base_buy_amount", 10000.0),
    )

    # 6. 构建配置
    config = BacktestConfig(
        index_code=req.index_code,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        signal_strategy=req.signal_strategy,
        signal_boundaries=req.signal_boundaries,
        signal_lag_days=req.signal_lag_days,
        buy_signals=req.buy_signals,
        sell_signals=req.sell_signals,
        hold_signals=req.hold_signals,
        action_mapping=action_mapping,
        risk_params=risk_params,
    )

    # 7. 运行回测
    engine = BacktestEngine(config)
    result = engine.run(price_data)

    # 8. 组装响应
    equity_curve = [
        {
            "date": pt.date,
            "value": pt.equity,
            "position_pct": pt.position_pct,
            "signal_level": pt.signal_level,
            "action_text": pt.action_text,
            "reason": pt.reason,
            "is_risk_action": pt.is_risk_action,
        }
        for pt in result.equity_curve
    ]

    benchmark_curve = [
        {"date": pt.date, "value": pt.equity}
        for pt in result.benchmark_curve
    ]

    trades = [
        {
            "date": t.trade_date,
            "type": t.trade_type,
            "signal": t.signal_level,
            "price": t.price,
            "shares": t.shares,
            "amount": t.amount,
            "reason": t.reason,
        }
        for t in result.trades
    ]

    # daily_log 最多返回最近60条
    daily_log = result.daily_log[-60:] if result.daily_log else []

    data_source_tag = "real" if price_data and signal_map else "mock"
    if req.fund_code and price_data:
        data_source_tag = "fund_real"

    # 操作汇总
    buy_count = sum(1 for t in result.trades if t.trade_type == "buy")
    sell_count = sum(1 for t in result.trades if t.trade_type == "sell")
    risk_count = sum(1 for t in result.trades if t.trade_type == "risk_sell")

    summary_text = f"加仓{buy_count}次·减仓{sell_count}次·风控{risk_count}次"
    if result.risk_stats:
        summary_text += f"·回调加仓{result.risk_stats.get('pullback_buys',0)}次·偏离加仓{result.risk_stats.get('deviation_buys',0)}次"

    response = {
        "code": 0,
        "data": {
            "total_return": result.metrics.total_return,
            "annual_return": result.metrics.annual_return,
            "max_drawdown": result.metrics.max_drawdown,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "win_rate": result.metrics.win_rate,
            "total_trades": result.metrics.total_trades,
            "signal_accuracy": result.metrics.signal_accuracy,
            "benchmark_return": round((result.benchmark_curve[-1].equity / config.initial_capital - 1) * 100, 2) if result.benchmark_curve else 0,
            "equity_curve": equity_curve,
            "benchmark_curve": benchmark_curve,
            "trades": trades,
            "daily_log": daily_log,
            "risk_stats": result.risk_stats,
            "summary_text": summary_text,
            "_data_source": data_source_tag,
            "index_code": req.index_code,
            "start_date": req.start_date,
            "end_date": req.end_date,
        },
        "message": "ok",
    }

    # 缓存5分钟
    await cache_set(cache_k, response, ttl=300)
    return response


@router.get("/signal-performance")
async def get_signal_performance(
    index_code: str = Query(default="SH000300"),
    days: int = Query(default=60, description="回看天数"),
    forward_days: int = Query(default=0, description="前瞻天数(0=不计算, 1/5/20分别计算1/5/20日胜率)"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """信号绩效统计（支持前瞻收益验证）

    当 forward_days > 0 时，为每个信号计算 N 日后的实际涨跌幅，
    并返回按信号等级分组的胜率、平均收益、最大/最小收益。
    """
    ts_index_code = to_tushare(index_code)

    cache_k = f"signal_perf:{ts_index_code}:{days}:{forward_days}"
    if forward_days == 0:
        cached = await cache_get(cache_k)
        if cached is not None:
            return cached

    end_date = datetime.now().date()
    start_date = (datetime.now() - timedelta(days=days + max(forward_days, 10) + 5)).date()

    stmt = select(MarketSentiment).where(
        and_(
            MarketSentiment.index_code == ts_index_code,
            MarketSentiment.trade_date >= start_date,
            MarketSentiment.trade_date <= end_date,
        )
    ).order_by(MarketSentiment.trade_date.asc())

    result = await session.execute(stmt)
    records = result.scalars().all()

    if not records:
        return {
            "code": 0,
            "data": {
                "index_code": index_code,
                "total_signals": 0,
                "signals": [],
                "_data_source": "empty",
            },
            "message": "ok",
        }

    signal_counts: dict[str, int] = {}
    signals = []

    # 如果需要前瞻收益，先加载 CLOSE 价格序列
    close_map: dict[date, float] = {}
    if forward_days > 0:
        from app.models.factor_history import FactorHistory
        # trade_date 在 DB 中是 "YYYYMMDD" 字符串格式
        cutoff_str = start_date.strftime("%Y%m%d")
        end_str = (end_date + timedelta(days=forward_days + 10)).strftime("%Y%m%d")
        price_stmt = (
            select(FactorHistory.raw_value, FactorHistory.trade_date)
            .where(
                and_(
                    FactorHistory.index_code == ts_index_code,
                    FactorHistory.factor_name == "CLOSE",
                    FactorHistory.trade_date >= cutoff_str,
                    FactorHistory.trade_date <= end_str,
                )
            )
            .order_by(FactorHistory.trade_date.asc())
        )
        price_result = await session.execute(price_stmt)
        for row in price_result:
            try:
                dt = datetime.strptime(row[1], "%Y%m%d").date()
                close_map[dt] = row[0]
            except (ValueError, IndexError):
                pass

    for r in records:
        sl = r.signal_level or "B"
        signal_counts[sl] = signal_counts.get(sl, 0) + 1
        sig_entry = {
            "date": r.trade_date.isoformat() if hasattr(r.trade_date, "isoformat") else str(r.trade_date),
            "signal_level": sl,
            "composite_score": round(r.composite_score, 1) if r.composite_score else None,
            "confidence": r.confidence_stars,
        }

        # 前瞻收益计算
        if forward_days > 0:
            sig_date = r.trade_date if isinstance(r.trade_date, date) else r.trade_date
            sig_close = close_map.get(sig_date)
            future_date = sig_date + timedelta(days=forward_days)

            # 找最近的下一个交易日价格
            future_close = None
            for offset in range(0, 5):  # 允许最多往后找5天
                check_date = future_date + timedelta(days=offset)
                if check_date in close_map:
                    future_close = close_map[check_date]
                    break

            if sig_close and future_close and sig_close > 0:
                forward_return = round((future_close - sig_close) / sig_close * 100, 2)
                sig_entry["forward_return"] = forward_return
                sig_entry["forward_days"] = forward_days
            else:
                sig_entry["forward_return"] = None

        signals.append(sig_entry)

    buy_count = sum(signal_counts.get(s, 0) for s in ["S+", "S", "A"])
    sell_count = sum(signal_counts.get(s, 0) for s in ["D", "E"])
    hold_count = sum(signal_counts.get(s, 0) for s in ["B", "C"])

    response_data: dict = {
        "index_code": index_code,
        "total_signals": len(records),
        "signal_distribution": signal_counts,
        "buy_signals": buy_count,
        "sell_signals": sell_count,
        "hold_signals": hold_count,
        "signals": signals[:20],
        "_data_source": "real",
    }

    # 前瞻收益按信号等级聚合
    if forward_days > 0:
        level_stats: dict[str, dict] = {}
        for sig in signals:
            sl = sig["signal_level"]
            fr = sig.get("forward_return")
            if fr is None:
                continue
            if sl not in level_stats:
                level_stats[sl] = {"returns": [], "wins": 0, "total": 0}
            level_stats[sl]["returns"].append(fr)
            level_stats[sl]["total"] += 1
            if fr > 0:
                level_stats[sl]["wins"] += 1

        accuracy: dict[str, dict] = {}
        for sl, stats in sorted(level_stats.items()):
            returns = stats["returns"]
            accuracy[sl] = {
                "count": stats["total"],
                "win_rate": round(stats["wins"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0,
                "avg_return": round(sum(returns) / len(returns), 2) if returns else 0,
                "max_return": round(max(returns), 2) if returns else 0,
                "min_return": round(min(returns), 2) if returns else 0,
                "forward_days": forward_days,
            }
        response_data["forward_accuracy"] = accuracy

    response = {
        "code": 0,
        "data": response_data,
        "message": "ok",
    }

    # 仅基础统计缓存
    if forward_days == 0:
        await cache_set(cache_k, response, ttl=300)
    return response


@router.get("/strategies")
async def get_strategies(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取可用回测策略列表"""
    strategies = [
        {
            "id": "v5_signal",
            "name": "V5.0 信号策略",
            "description": "基于11因子7级信号的仓位管理策略",
            "params": {
                "buy_signals": ["S+", "S", "A"],
                "sell_signals": ["D", "E"],
                "hold_signals": ["B", "C"],
            },
            "is_default": True,
        },
        {
            "id": "aggressive",
            "name": "激进策略",
            "description": "放宽买入条件，更早建仓",
            "params": {
                "buy_signals": ["S+", "S", "A", "B"],
                "sell_signals": ["E"],
                "hold_signals": ["C", "D"],
            },
            "is_default": False,
        },
        {
            "id": "conservative",
            "name": "保守策略",
            "description": "收紧买入条件，更晚建仓",
            "params": {
                "buy_signals": ["S+", "S"],
                "sell_signals": ["D", "E"],
                "hold_signals": ["A", "B", "C"],
            },
            "is_default": False,
        },
        {
            "id": "buy_hold",
            "name": "买入持有",
            "description": "满仓不动，作为基准对比",
            "params": {},
            "is_default": False,
        },
    ]

    return {
        "code": 0,
        "data": strategies,
        "message": "ok",
    }


@router.get("/history")
async def get_backtest_history(
    page: int = Query(default=1),
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取回测历史列表（Stub）"""
    return {
        "code": 0,
        "data": {
            "items": [],
            "total": 0,
        },
        "message": "ok",
    }


class SaveStrategyRequest(BaseModel):
    """保存方案请求"""
    name: str
    params_json: dict | str


@router.post("/strategy")
async def save_backtest_strategy(
    req: SaveStrategyRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """保存回测方案（数据库持久化，按用户隔离）"""
    params_str = req.params_json if isinstance(req.params_json, str) else json.dumps(req.params_json, ensure_ascii=False)

    # 查找同名方案
    stmt = select(BacktestStrategy).where(
        and_(
            BacktestStrategy.user_id == user_id,
            BacktestStrategy.name == req.name,
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.params_json = params_str
        existing.updated_at = datetime.now()
        await session.flush()
        await session.commit()
        strategy_id = existing.id
    else:
        new_strategy = BacktestStrategy(
            user_id=user_id,
            name=req.name,
            params_json=params_str,
            is_active=False,
        )
        session.add(new_strategy)
        await session.flush()
        await session.commit()
        strategy_id = new_strategy.id

    return {"code": 0, "data": {"id": strategy_id, "name": req.name}, "message": "保存成功"}


@router.get("/strategy")
async def get_backtest_strategies(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取方案列表（按用户隔离）"""
    stmt = select(BacktestStrategy).where(
        BacktestStrategy.user_id == user_id
    ).order_by(BacktestStrategy.created_at.desc())
    result = await session.execute(stmt)
    strategies = result.scalars().all()

    return {
        "code": 0,
        "data": {
            "strategies": [
                {
                    "id": s.id,
                    "name": s.name,
                    "params_json": s.params_json,
                    "is_active": s.is_active,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in strategies
            ]
        },
        "message": "ok",
    }


@router.delete("/strategy/{strategy_id}")
async def delete_backtest_strategy(
    strategy_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除回测方案（仅删除自己的）"""
    stmt = select(BacktestStrategy).where(
        and_(
            BacktestStrategy.id == strategy_id,
            BacktestStrategy.user_id == user_id,
        )
    )
    result = await session.execute(stmt)
    strategy = result.scalar_one_or_none()

    if not strategy:
        return {"code": 404, "data": None, "message": "方案不存在或无权删除"}

    await session.delete(strategy)
    return {"code": 0, "data": None, "message": "删除成功"}


@router.put("/strategy/{strategy_id}/activate")
async def activate_backtest_strategy(
    strategy_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """激活回测方案（同一用户仅一个活跃方案）"""
    # 先将该用户所有方案设为不活跃
    stmt_deactivate = (
        update(BacktestStrategy)
        .where(BacktestStrategy.user_id == user_id)
        .values(is_active=False)
    )
    await session.execute(stmt_deactivate)

    # 再激活目标方案
    stmt = select(BacktestStrategy).where(
        and_(
            BacktestStrategy.id == strategy_id,
            BacktestStrategy.user_id == user_id,
        )
    )
    result = await session.execute(stmt)
    strategy = result.scalar_one_or_none()

    if not strategy:
        return {"code": 404, "data": None, "message": "方案不存在或无权操作"}

    strategy.is_active = True
    await session.flush()
    await session.commit()

    # 将激活方案的参数写入本地 JSON（主系统读取入口）
    import json as _json
    from pathlib import Path as _Path
    _ACTIVE_CONFIG_PATH = _Path(__file__).parent.parent / "data" / "active_strategy.json"
    _ACTIVE_CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(_ACTIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
        _json.dump({
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "params": strategy.params_json if isinstance(strategy.params_json, dict) else _json.loads(strategy.params_json or "{}"),
            "activated_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    logger.info("已同步激活方案参数到主系统: %s → %s", strategy.name, _ACTIVE_CONFIG_PATH)

    return {"code": 0, "data": {"id": strategy.id, "name": strategy.name}, "message": "激活成功，主系统参数已同步"}
