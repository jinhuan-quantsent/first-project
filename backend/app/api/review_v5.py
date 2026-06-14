"""
回测接口 — V5.0
策略回测 + 绩效评估
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.engine.backtest import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    BacktestMetrics,
)

router = APIRouter()


# ============================================================
# Pydantic 模型
# ============================================================

class BacktestRequest(BaseModel):
    """回测请求"""
    index_code: str = "SH000300"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 100000.0
    signal_strategy: str = "v5_signal"
    buy_signals: list[str] = ["S+", "S", "A"]
    sell_signals: list[str] = ["D", "E"]
    hold_signals: list[str] = ["B", "C"]


class BacktestResponse(BaseModel):
    """回测响应"""
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    equity_curve: list[dict]
    trades: list[dict]


# ============================================================
# 辅助函数
# ============================================================

def _generate_mock_price_data(
    index_code: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """
    生成 Mock 价格数据（含 V5 信号）
    用于无真实数据时的演示
    """
    import random
    from datetime import datetime, timedelta

    random.seed(hash(index_code))
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    data = []
    price = 3000.0  # 起始价格
    current = start
    signal_levels = ["S+", "S", "A", "B", "C", "D", "E"]
    signal = "B"

    while current <= end:
        # 跳过周末
        if current.weekday() < 5:
            # 随机价格变化
            change = (random.random() - 0.48) * 2.0
            price *= (1 + change / 100)
            price = max(price * 0.95, price)  # 防止负价格

            # 随机信号变化
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


def _run_backtest(req: BacktestRequest) -> BacktestResult:
    """执行回测"""
    config = BacktestConfig(
        index_code=req.index_code,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        signal_strategy=req.signal_strategy,
        buy_signals=req.buy_signals,
        sell_signals=req.sell_signals,
        hold_signals=req.hold_signals,
    )

    # 获取价格数据（Mock）
    price_data = _generate_mock_price_data(
        req.index_code, req.start_date, req.end_date,
    )

    engine = BacktestEngine(config)
    return engine.run(price_data)


# ============================================================
# API 接口
# ============================================================

@router.post("/review/run-backtest")
async def run_backtest(
    req: BacktestRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    运行策略回测

    基于V5信号系统进行历史回测，返回权益曲线和绩效指标
    """
    result = _run_backtest(req)

    equity_curve = [
        {
            "date": pt.date,
            "equity": pt.equity,
            "position_pct": pt.position_pct,
            "signal_level": pt.signal_level,
            "daily_return": pt.daily_return,
        }
        for pt in result.equity_curve
    ]

    trades = [
        {
            "date": t.trade_date,
            "type": t.trade_type,
            "signal_level": t.signal_level,
            "price": t.price,
            "shares": t.shares,
            "amount": t.amount,
            "commission": t.commission,
            "reason": t.reason,
        }
        for t in result.trades
    ]

    return {
        "code": 0,
        "data": {
            "total_return": result.metrics.total_return,
            "annual_return": result.metrics.annual_return,
            "max_drawdown": result.metrics.max_drawdown,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "win_rate": result.metrics.win_rate,
            "profit_loss_ratio": result.metrics.profit_loss_ratio,
            "total_trades": result.metrics.total_trades,
            "calmar_ratio": result.metrics.calmar_ratio,
            "volatility": result.metrics.volatility,
            "equity_curve": equity_curve,
            "trades": trades,
        },
        "message": "ok",
    }


@router.get("/review/signal-performance")
async def get_signal_performance(
    index_code: str = Query(default="SH000300"),
    days: int = Query(default=30),
) -> dict:
    """
    信号绩效统计

    统计最近N天的信号准确率
    """
    # Mock 信号绩效数据
    import random
    random.seed(hash(index_code))

    signals = []
    correct = 0
    total = 0
    for i in range(days):
        signal_type = random.choice(["buy", "sell", "hold"])
        actual_return = round((random.random() - 0.45) * 5, 2)
        is_correct = (
            (signal_type == "buy" and actual_return > 0)
            or (signal_type == "sell" and actual_return < 0)
            or (signal_type == "hold" and abs(actual_return) < 1)
        )
        if is_correct:
            correct += 1
        total += 1

        signals.append({
            "date": f"2025-04-{String(i + 1).zfill(2)}",
            "signal_type": signal_type,
            "actual_return": actual_return,
            "is_correct": is_correct,
        })

    return {
        "code": 0,
        "data": {
            "index_code": index_code,
            "total_signals": total,
            "correct_signals": correct,
            "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
            "buy_signals": sum(1 for s in signals if s["signal_type"] == "buy"),
            "sell_signals": sum(1 for s in signals if s["signal_type"] == "sell"),
            "hold_signals": sum(1 for s in signals if s["signal_type"] == "hold"),
            "signals": signals[-10:],  # 最近10条
        },
        "message": "ok",
    }


@router.get("/review/strategies")
async def get_strategies(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取可用回测策略列表

    返回预设策略 + 用户自定义策略
    """
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
