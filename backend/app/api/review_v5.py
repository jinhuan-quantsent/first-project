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
    # 检查缓存
    cache_k = f"backtest:{req.index_code}:{req.start_date}:{req.end_date}:{req.signal_strategy}:{hash(str(req.risk_params))}"
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    # 1. 获取真实价格数据
    price_data = await _get_real_price_data(req.index_code, req.start_date, req.end_date)

    # 2. 获取真实信号数据
    signal_map = await _get_real_signal_data(req.index_code, req.start_date, req.end_date, session)

    # 3. 合并信号到价格数据
    if price_data and signal_map:
        for item in price_data:
            date_key = item["date"].replace("-", "")
            if date_key in signal_map:
                item["signal_level"] = signal_map[date_key]
    elif not price_data:
        price_data = _generate_mock_price_data(req.index_code, req.start_date, req.end_date)

    # 4. 构建行动映射
    action_mapping = {}
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
        action_mapping=action_mapping if action_mapping else None,
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
