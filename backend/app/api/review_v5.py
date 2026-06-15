"""
回测接口 — V5.0 扩展版
策略回测 + 绩效评估 + 5类参数 + 风控统计

数据源：
- 指数日线：Tushare index_daily
- 信号等级：factor_history + V5引擎实时计算
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, func
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
from app.utils.data_source import data_source

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

# 指数代码映射
_INDEX_CODE_MAP = {
    "SH000300": "000300.SH",
    "SH000001": "000001.SH",
    "SZ399006": "399006.SZ",
    "SH000016": "000016.SH",
}


async def _get_real_price_data(
    index_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """从Tushare获取真实指数日线数据"""
    ts_code = _INDEX_CODE_MAP.get(index_code, index_code.replace("SH", "").replace("SZ", "") + ".SH")

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
    try:
        stmt = select(
            MarketSentiment.trade_date,
            MarketSentiment.signal_level,
        ).where(
            and_(
                MarketSentiment.index_code == index_code,
                MarketSentiment.trade_date >= start_date.replace("-", ""),
                MarketSentiment.trade_date <= end_date.replace("-", ""),
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
                FactorHistory.index_code == index_code,
                FactorHistory.factor_name == "COMPOSITE",
                FactorHistory.trade_date >= start_date.replace("-", ""),
                FactorHistory.trade_date <= end_date.replace("-", ""),
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
    """从Tushare获取基金净值作为价格数据（用于单基金回测）"""
    from app.utils.eastmoney import code_to_tushare, get_fund_nav_history

    ts_code = code_to_tushare(fund_code)

    # 计算需要的天数（加10天缓冲）
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days + 10
    except Exception:
        days = 365

    # 确保最少取60天数据
    days = max(days, 60)

    nav_history = await get_fund_nav_history(ts_code, days=days)

    if not nav_history:
        return []

    # 将净值数据转换为回测引擎需要的格式
    start_dt_str = start_date.replace("-", "")
    end_dt_str = end_date.replace("-", "")

    result = []
    for h in nav_history:
        date_str = str(h.get("date", ""))
        if date_str >= start_dt_str and date_str <= end_dt_str:
            nav_val = float(h.get("nav", 0) or 0)
            daily_ret = float(h.get("daily_return", 0) or 0)
            if nav_val <= 0:
                continue
            result.append({
                "date": date_str,
                "close": nav_val,
                "pct_chg": daily_ret,
                "volume": 0,
                "signal_level": "B",  # 默认中性，后面会从市场情绪覆盖
            })

    return result


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

def _generate_daily_action(
    signal_level: Optional[str],
    score: Optional[float],
    current_portfolio: float,
    initial_capital: float,
) -> tuple[str, int, str]:
    """
    根据当天信号生成操作建议

    规则:
    - S+/S(极度恐惧/恐惧): 加仓，金额 = initial * 10%~20%
    - A(偏恐): 小幅加仓，金额 = initial * 5%~10%
    - B(中性偏多): 持有
    - C(中性偏空): 持有或小幅减仓 initial * 5%
    - D(贪婪): 减仓，金额 = initial * 10%~15%
    - E/F(极度贪婪): 大幅减仓，金额 = initial * 15%~20%

    具体金额根据 score 细分:
    - 同一信号等级内，score越高(越极端) → 操作力度越大
    - 单日最大操作不超过当前持仓的20%
    """
    # 信号→操作映射: (action, min_pct_of_initial, max_pct_of_initial)
    action_map: dict[str, tuple[str, float, float]] = {
        "S+": ("buy", 0.15, 0.20),   # 极度恐惧 → 加仓 15-20%
        "S":  ("buy", 0.10, 0.15),   # 恐惧 → 加仓 10-15%
        "A":  ("buy", 0.05, 0.10),   # 偏恐惧 → 加仓 5-10%
        "B":  ("hold", 0, 0),        # 中性偏多 → 持有
        "C":  ("hold", 0, 0.05),     # 中性偏空 → 持有或微减
        "D":  ("sell", 0.10, 0.15),  # 贪婪 → 减仓 10-15%
        "E":  ("sell", 0.15, 0.20),  # 极度贪婪 → 减仓 15-20%
        "F":  ("sell", 0.20, 0.25),  # 极端情况 → 减仓 20-25%
    }

    default_action = ("hold", 0, 0)
    action, min_pct, max_pct = action_map.get(signal_level or "", default_action)

    # 如果信号等级不在映射中，默认持有
    if signal_level and signal_level not in action_map:
        action, min_pct, max_pct = default_action

    safe_score = score if score is not None else 50.0

    if action == "hold":
        amount = 0
        if signal_level and signal_level in ("C",):
            # C级有概率小幅减仓
            if safe_score < 40:
                amount = round(initial_capital * 0.05)
                action = "sell"
                reason = f"{signal_level}级偏空信号({safe_score}分)，小幅减仓{amount}元控制风险"
            else:
                reason = f"信号{signal_level}({safe_score}分)，维持持有观察"
        else:
            reason = f"信号{signal_level or '未知'}({safe_score}分)，维持持有观察"
    elif action == "buy":
        # 根据 score 在 min-max 之间插值
        ratio = min_pct + (max_pct - min_pct) * min(safe_score / 100.0, 1.0)
        amount = round(initial_capital * ratio)
        # 单日加仓不超过当前持仓的20%
        amount = min(amount, round(current_portfolio * 0.20))
        reason = f"{signal_level}级恐惧信号({safe_score}分)，逆向加仓{amount}元"
    else:  # sell
        ratio = min_pct + (max_pct - min_pct) * min(safe_score / 100.0, 1.0)
        amount = round(min(initial_capital * ratio, current_portfolio * 0.20))  # 单日最多卖20%
        reason = f"{signal_level}级贪婪信号({safe_score}分)，减仓止盈{amount}元"

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

    # 1. 尝试从 market_sentiment 表精确查询
    try:
        stmt = select(
            MarketSentiment.signal_level,
            MarketSentiment.composite_score,
        ).where(
            and_(
                MarketSentiment.index_code == index_code,
                MarketSentiment.trade_date == date_str.replace("-", ""),
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
                FactorHistory.index_code == index_code,
                FactorHistory.factor_name == "COMPOSITE",
                FactorHistory.trade_date == date_str.replace("-", ""),
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
                MarketSentiment.index_code == index_code,
                MarketSentiment.trade_date < date_str.replace("-", ""),
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
    2. 对每一天(除第一天外)，查询当天的市场情绪信号
    3. 根据信号 + 仓位模型生成当日操作建议
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

    # Step 2: 逐日计算
    signal_index_code = "SH000300"  # 基金回测始终使用沪深300信号
    portfolio_value = req.initial_capital
    daily_records = []

    # 基准线（买入不动）
    benchmark_nav_start = nav_data[0]["nav"] if nav_data else 1.0

    for i, day in enumerate(nav_data):
        date = day["date"]
        nav = day["nav"]

        if i == 0:
            # Day 1: 初始买入，不给建议
            action = "none"
            action_amount = 0
            reason = f"初始买入{req.initial_capital}元，等待信号"
            signal_level = None
            signal_score = None
            daily_return_pct = 0.0
        else:
            # 获取当天信号
            signal_info = await _get_signal_for_date(date, signal_index_code, session)
            signal_level = signal_info.get("signal_level")
            signal_score = signal_info.get("composite_score")

            # 根据信号生成操作建议
            action, action_amount, reason = _generate_daily_action(
                signal_level, signal_score, portfolio_value, req.initial_capital,
            )

            # 计算日收益率（基于净值变化）
            prev_nav = nav_data[i - 1]["nav"]
            if prev_nav > 0:
                daily_return_pct = round((nav / prev_nav - 1) * 100, 2)
            else:
                daily_return_pct = 0.0

            # 执行操作，更新持仓市值
            # 持仓市值 = 前日持仓 * (1 + 日收益率) + 操作金额
            portfolio_value = portfolio_value * (1 + daily_return_pct / 100.0)
            if action == "buy":
                portfolio_value += action_amount
            elif action == "sell":
                portfolio_value -= action_amount
                portfolio_value = max(portfolio_value, 0)  # 不能为负

        daily_records.append({
            "date": date,
            "signal_level": signal_level,
            "signal_score": signal_score,
            "action": action,
            "action_amount": action_amount if action != "hold" and action != "none" else 0,
            "nav": nav,
            "portfolio_value": round(portfolio_value, 2),
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
        stop_loss=rp.get("stop_loss", -0.15),
        stop_loss_threshold=rp.get("stop_loss_threshold", 1.0),
        stop_loss_reduce_pct=rp.get("stop_loss_reduce_pct", 50.0),
        take_profit=rp.get("take_profit", 0.30),
        take_profit_drawdown=rp.get("take_profit_drawdown", 0.10),
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
    days: int = Query(default=30),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """信号绩效统计"""
    cache_k = f"signal_perf:{index_code}:{days}"
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

    stmt = select(MarketSentiment).where(
        and_(
            MarketSentiment.index_code == index_code,
            MarketSentiment.trade_date >= start_date,
            MarketSentiment.trade_date <= end_date,
        )
    ).order_by(MarketSentiment.trade_date.desc()).limit(days)

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

    signal_counts = {}
    signals = []
    for r in records:
        sl = r.signal_level or "B"
        signal_counts[sl] = signal_counts.get(sl, 0) + 1
        signals.append({
            "date": r.trade_date,
            "signal_level": sl,
            "composite_score": r.composite_score,
            "confidence": r.confidence,
        })

    buy_count = sum(signal_counts.get(s, 0) for s in ["S+", "S", "A"])
    sell_count = sum(signal_counts.get(s, 0) for s in ["D", "E"])
    hold_count = sum(signal_counts.get(s, 0) for s in ["B", "C"])

    response = {
        "code": 0,
        "data": {
            "index_code": index_code,
            "total_signals": len(records),
            "signal_distribution": signal_counts,
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "hold_signals": hold_count,
            "signals": signals[:10],
            "_data_source": "real",
        },
        "message": "ok",
    }

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


@router.post("/strategy")
async def save_backtest_strategy(
    req: dict,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """保存回测方案（Stub）"""
    return {
        "code": 0,
        "data": {
            "id": 1,
            "name": req.get("name", "未命名方案"),
        },
        "message": "保存成功",
    }


@router.delete("/strategy/{strategy_id}")
async def delete_backtest_strategy(
    strategy_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除回测方案（Stub）"""
    return {"code": 0, "data": None, "message": "删除成功"}


@router.put("/strategy/{strategy_id}/activate")
async def activate_backtest_strategy(
    strategy_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """激活回测方案（Stub）"""
    return {"code": 0, "data": None, "message": "激活成功"}
