"""
模拟回溯引擎
用于验证情绪指标的历史有效性

核心功能：
- 回测指定时间段内的情绪信号表现
- 计算胜率、平均收益、最大回撤等指标
- 与基准（买入持有）对比
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class BacktestParams:
    """回测参数"""
    start_date: date
    end_date: date
    index_code: str = "SH000300"
    initial_capital: float = 100000.0  # 初始资金
    sentiment_threshold_buy: float = 30.0  # 买入阈值（恐慌时买入）
    sentiment_threshold_sell: float = 70.0  # 卖出阈值（贪婪时卖出）
    position_pct: float = 50.0  # 每次调仓比例(%)


@dataclass
class TradeRecord:
    """交易记录"""
    trade_date: date
    trade_type: str  # buy / sell
    price: float
    shares: float
    amount: float
    sentiment_score: float
    reason: str


@dataclass
class BacktestResult:
    """回测结果"""
    params: BacktestParams = field(default_factory=BacktestParams)
    total_return: float = 0.0  # 总收益率(%)
    annual_return: float = 0.0  # 年化收益率(%)
    max_drawdown: float = 0.0  # 最大回撤(%)
    win_rate: float = 0.0  # 胜率(%)
    sharpe_ratio: float = 0.0  # 夏普比率
    benchmark_return: float = 0.0  # 基准收益率(%)
    excess_return: float = 0.0  # 超额收益(%)
    total_trades: int = 0  # 总交易次数
    profit_trades: int = 0  # 盈利交易次数
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)  # [{date, value}]
    signal_accuracy: float = 0.0  # 信号准确率(%)


def run_backtest(
    sentiment_history: list[dict],
    price_history: list[dict],
    params: BacktestParams,
) -> BacktestResult:
    """
    执行模拟回溯

    Args:
        sentiment_history: 历史情绪数据 [{date, composite_score, sentiment_label}, ...]
        price_history: 历史价格数据 [{date, close}, ...]
        params: 回测参数

    Returns:
        BacktestResult: 回测结果
    """
    # 对齐数据
    sentiment_map: dict[str, float] = {
        str(s["date"]): s["composite_score"] for s in sentiment_history
    }
    price_map: dict[str, float] = {
        str(p["date"]): p["close"] for p in price_history
    }

    # 找到共同日期
    common_dates = sorted(set(sentiment_map.keys()) & set(price_map.keys()))

    if len(common_dates) < 10:
        return BacktestResult(params=params)

    # 初始状态
    cash = params.initial_capital
    shares = 0.0
    trades: list[TradeRecord] = []

    initial_price = price_map[common_dates[0]]
    equity_curve: list[dict] = []

    for d in common_dates:
        price = price_map[d]
        score = sentiment_map.get(d, 50.0)

        # 计算当前市值
        market_value = cash + shares * price

        # 买入信号：情绪评分低于买入阈值
        if score <= params.sentiment_threshold_buy and cash > params.initial_capital * 0.05:
            buy_amount = cash * (params.position_pct / 100)
            buy_shares = buy_amount / price
            cash -= buy_amount
            shares += buy_shares
            trades.append(TradeRecord(
                trade_date=date.fromisoformat(d),
                trade_type="buy",
                price=price,
                shares=buy_shares,
                amount=buy_amount,
                sentiment_score=score,
                reason=f"恐慌信号(评分{score})，分批建仓",
            ))

        # 卖出信号：情绪评分高于卖出阈值
        elif score >= params.sentiment_threshold_sell and shares > 0:
            sell_shares = shares * (params.position_pct / 100)
            sell_amount = sell_shares * price
            cash += sell_amount
            shares -= sell_shares
            trades.append(TradeRecord(
                trade_date=date.fromisoformat(d),
                trade_type="sell",
                price=price,
                shares=sell_shares,
                amount=sell_amount,
                sentiment_score=score,
                reason=f"贪婪信号(评分{score})，分批止盈",
            ))

        equity_curve.append({
            "date": d,
            "value": round(cash + shares * price, 2),
        })

    # 计算最终指标
    final_value = cash + shares * float(price_map[common_dates[-1]])
    total_return = (final_value / params.initial_capital - 1) * 100

    # 基准收益（买入持有）
    benchmark_return = (float(price_map[common_dates[-1]]) / initial_price - 1) * 100

    # 年化收益率
    days = len(common_dates)
    years = days / 252
    if years > 0 and total_return > -100:
        annual_return = ((1 + total_return / 100) ** (1 / years) - 1) * 100
    else:
        annual_return = 0.0

    # 最大回撤
    peak = 0.0
    max_dd = 0.0
    for point in equity_curve:
        v = point["value"]
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            max_dd = max(max_dd, dd)

    # 胜率
    profit_trades = sum(1 for t in trades if t.trade_type == "sell")
    if trades:
        win_rate = (profit_trades / len(trades)) * 100 if trades else 0
    else:
        win_rate = 0

    # 夏普比率（简化）
    if len(equity_curve) > 1:
        daily_returns = []
        for i in range(1, len(equity_curve)):
            r = (equity_curve[i]["value"] / equity_curve[i - 1]["value"] - 1)
            daily_returns.append(r)
        mean_ret = sum(daily_returns) / len(daily_returns)
        std_ret = (sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
        if std_ret > 0:
            sharpe = (mean_ret / std_ret) * (252 ** 0.5)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    return BacktestResult(
        params=params,
        total_return=round(total_return, 2),
        annual_return=round(annual_return, 2),
        max_drawdown=round(max_dd, 2),
        win_rate=round(win_rate, 2),
        sharpe_ratio=round(sharpe, 2),
        benchmark_return=round(benchmark_return, 2),
        excess_return=round(total_return - benchmark_return, 2),
        total_trades=len(trades),
        profit_trades=profit_trades,
        trades=trades,
        equity_curve=equity_curve,
        signal_accuracy=round(win_rate, 2),
    )
