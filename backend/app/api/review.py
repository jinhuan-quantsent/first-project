"""
复盘分析接口
信号表现、回测、优化报告
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.engine.backtest import run_backtest, BacktestParams, BacktestResult

router = APIRouter()


class BacktestRequest(BaseModel):
    """回测请求"""
    index_code: str = "SH000300"
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD
    initial_capital: float = 100000.0
    sentiment_threshold_buy: float = 30.0
    sentiment_threshold_sell: float = 70.0
    position_pct: float = 50.0


@router.get("/review/signal-performance")
async def get_signal_performance(
    index_code: str = Query(default="SH000300", description="指数代码"),
    days: int = Query(default=30, description="回溯天数"),
) -> dict:
    """
    信号表现分析

    查看历史情绪信号的准确度
    """
    today = date.today()
    # Mock 信号表现数据
    signals = []
    base_score = 50.0
    for i in range(days, 0, -1):
        d = today - timedelta(days=i)
        score = base_score + (hash(f"{index_code}{d.isoformat()}") % 40 - 20)
        score = max(10, min(90, score))
        actual_return = (score - 50) * 0.05  # 简化：评分与收益正相关

        # 判断信号是否正确
        if score < 30:
            signal_type = "buy"
            correct = actual_return > 0  # 恐慌买入后如果涨了=正确
        elif score > 70:
            signal_type = "sell"
            correct = actual_return < 0  # 狂热卖出后如果跌了=正确
        else:
            signal_type = "hold"
            correct = abs(actual_return) < 2  # 中性波动小=正确

        signals.append({
            "date": d.isoformat(),
            "composite_score": round(score, 1),
            "signal_type": signal_type,
            "actual_return": round(actual_return, 2),
            "is_correct": correct,
        })

    correct_count = sum(1 for s in signals if s["is_correct"])
    accuracy = round(correct_count / len(signals) * 100, 1) if signals else 0

    return {
        "code": 0,
        "data": {
            "index_code": index_code,
            "total_signals": len(signals),
            "correct_signals": correct_count,
            "accuracy": accuracy,
            "buy_signals": sum(1 for s in signals if s["signal_type"] == "buy"),
            "sell_signals": sum(1 for s in signals if s["signal_type"] == "sell"),
            "hold_signals": sum(1 for s in signals if s["signal_type"] == "hold"),
            "signals": signals[-20:],  # 最近20条
        },
        "message": "ok",
    }


@router.post("/review/backtest")
async def run_backtest_endpoint(request: BacktestRequest) -> dict:
    """
    执行模拟回测

    基于历史情绪数据和价格数据回测策略表现
    """
    start_date = date.fromisoformat(request.start_date)
    end_date = date.fromisoformat(request.end_date)

    params = BacktestParams(
        start_date=start_date,
        end_date=end_date,
        index_code=request.index_code,
        initial_capital=request.initial_capital,
        sentiment_threshold_buy=request.sentiment_threshold_buy,
        sentiment_threshold_sell=request.sentiment_threshold_sell,
        position_pct=request.position_pct,
    )

    # Mock 历史数据
    days_diff = (end_date - start_date).days
    if days_diff > 365:
        days_diff = 365

    sentiment_history = []
    price_history = []
    base_price = 3500.0
    for i in range(days_diff + 1):
        d = start_date + timedelta(days=i)
        score = 50.0 + (hash(f"{request.index_code}{d.isoformat()}") % 40 - 20)
        price = base_price * (1 + sum(
            (hash(f"p{j}") % 20 - 10) / 1000
            for j in range(i)
        ))

        sentiment_history.append({
            "date": d.isoformat(),
            "composite_score": max(5, min(95, score)),
            "sentiment_label": "neutral",
        })
        price_history.append({
            "date": d.isoformat(),
            "close": round(price, 2),
        })

    result: BacktestResult = run_backtest(sentiment_history, price_history, params)

    return {
        "code": 0,
        "data": {
            "params": {
                "index_code": params.index_code,
                "start_date": params.start_date.isoformat(),
                "end_date": params.end_date.isoformat(),
                "initial_capital": params.initial_capital,
                "sentiment_threshold_buy": params.sentiment_threshold_buy,
                "sentiment_threshold_sell": params.sentiment_threshold_sell,
            },
            "result": {
                "total_return": result.total_return,
                "annual_return": result.annual_return,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "sharpe_ratio": result.sharpe_ratio,
                "benchmark_return": result.benchmark_return,
                "excess_return": result.excess_return,
                "total_trades": result.total_trades,
                "profit_trades": result.profit_trades,
            },
            "trades": [
                {
                    "date": t.trade_date.isoformat(),
                    "type": t.trade_type,
                    "price": t.price,
                    "amount": round(t.amount, 2),
                    "reason": t.reason,
                }
                for t in result.trades[:20]  # 最近20笔
            ],
            "equity_curve": result.equity_curve[-60:],  # 最近60天
        },
        "message": "ok",
    }


@router.get("/review/optimization-report")
async def get_optimization_report() -> dict:
    """
    参数优化报告

    基于历史回测给出最优参数建议
    """
    return {
        "code": 0,
        "data": {
            "current_params": {
                "sentiment_threshold_buy": 30.0,
                "sentiment_threshold_sell": 70.0,
                "position_pct": 50.0,
            },
            "suggested_params": {
                "sentiment_threshold_buy": 25.0,
                "sentiment_threshold_sell": 72.0,
                "position_pct": 55.0,
            },
            "improvement": {
                "expected_excess_return": 3.5,
                "expected_win_rate_improvement": 5.2,
            },
            "sensitivity_analysis": [
                {"param": "sentiment_threshold_buy", "range": [20, 25, 30, 35, 40], "returns": [12.5, 14.8, 13.2, 10.1, 8.5]},
                {"param": "sentiment_threshold_sell", "range": [60, 65, 70, 75, 80], "returns": [9.8, 12.1, 13.2, 14.5, 11.2]},
            ],
            "recommendation": "建议降低买入阈值至25分（更恐慌时买入），提高卖出阈值至72分（更乐观时卖出），可获得更好的风险收益比",
        },
        "message": "ok",
    }
