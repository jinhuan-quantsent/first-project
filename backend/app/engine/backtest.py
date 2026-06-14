"""
回测引擎 — V5.0
基于 V5 信号系统的策略回测框架

功能：
- 信号驱动回测（7级信号 → 仓位变化）
- 权益曲线计算
- 交易记录生成
- 绩效指标计算（年化收益、最大回撤、夏普比率等）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional
import math


@dataclass
class BacktestConfig:
    """回测配置"""
    index_code: str = "SH000300"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 100000.0
    commission_rate: float = 0.0012  # 万1.2
    stamp_tax_rate: float = 0.001   # 千1（卖出）
    signal_strategy: str = "v5_signal"  # v5_signal, simple_momentum, buy_hold

    # V5 信号策略参数
    buy_signals: list[str] = field(default_factory=lambda: ["S+", "S", "A"])
    sell_signals: list[str] = field(default_factory=lambda: ["D", "E"])
    hold_signals: list[str] = field(default_factory=lambda: ["B", "C"])

    # 仓位配置
    max_position_pct: float = 1.0
    min_position_pct: float = 0.0


@dataclass
class TradeRecord:
    """交易记录"""
    trade_date: str
    trade_type: str  # buy, sell
    signal_level: str
    price: float
    shares: float
    amount: float
    commission: float
    reason: str = ""


@dataclass
class EquityPoint:
    """权益曲线点"""
    date: str
    equity: float
    position_pct: float
    signal_level: str
    daily_return: float = 0.0


@dataclass
class BacktestMetrics:
    """回测绩效指标"""
    total_return: float = 0.0
    annual_return: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    total_trades: int = 0
    avg_hold_days: float = 0.0
    calmar_ratio: float = 0.0
    volatility: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    benchmark_curve: list[EquityPoint] = field(default_factory=list)


class BacktestEngine:
    """V5.0 回测引擎"""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self._config = config or BacktestConfig()

    def run(self, price_data: list[dict]) -> BacktestResult:
        """
        运行回测

        Args:
            price_data: [{date, close, signal_level, ...}, ...]
                        按日期升序排列的日线数据

        Returns:
            BacktestResult
        """
        config = self._config
        if not price_data:
            return BacktestResult(
                config=config,
                metrics=BacktestMetrics(),
                equity_curve=[],
                trades=[],
            )

        equity_curve: list[EquityPoint] = []
        trades: list[TradeRecord] = []
        benchmark_curve: list[EquityPoint] = []

        # 初始状态
        cash = config.initial_capital
        shares = 0.0
        equity = config.initial_capital
        position_pct = 0.0
        prev_equity = equity

        # 买入持有基准
        benchmark_shares = config.initial_capital / price_data[0]["close"]
        benchmark_equity = config.initial_capital

        for i, bar in enumerate(price_data):
            d = bar["date"]
            close = float(bar["close"])
            signal = bar.get("signal_level", "B")

            # 计算当前权益
            equity = cash + shares * close
            daily_return = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0

            equity_curve.append(EquityPoint(
                date=d,
                equity=round(equity, 2),
                position_pct=position_pct,
                signal_level=signal,
                daily_return=round(daily_return, 6),
            ))

            # 基准权益
            benchmark_equity = benchmark_shares * close
            benchmark_curve.append(EquityPoint(
                date=d,
                equity=round(benchmark_equity, 2),
                position_pct=1.0,
                signal_level="benchmark",
                daily_return=round((benchmark_equity - (benchmark_curve[-2].equity if len(benchmark_curve) > 1 else benchmark_equity)) / benchmark_equity, 6) if len(benchmark_curve) > 1 else 0.0,
            ))

            # 信号驱动仓位调整
            if config.signal_strategy == "v5_signal":
                target_pct = self._signal_to_position(signal, config)
            elif config.signal_strategy == "buy_hold":
                target_pct = 1.0
            else:
                target_pct = 0.5

            # 执行交易
            if abs(target_pct - position_pct) > 0.01:
                trade = self._execute_trade(
                    d, signal, close, target_pct, position_pct,
                    cash, shares, config,
                )
                if trade:
                    trades.append(trade)
                    cash = trade.amount  # 更新后
                    shares = trade.shares  # 更新后
                    position_pct = target_pct

            prev_equity = equity

        # 计算绩效指标
        metrics = self._calc_metrics(equity_curve, trades, config)

        return BacktestResult(
            config=config,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            benchmark_curve=benchmark_curve,
        )

    def _signal_to_position(self, signal: str, config: BacktestConfig) -> float:
        """信号等级 → 目标仓位百分比"""
        if signal in config.buy_signals:
            return 0.75  # 买入信号 → 75%仓位
        elif signal in config.sell_signals:
            return 0.25  # 卖出信号 → 25%仓位
        else:
            return 0.50  # 持有信号 → 50%仓位

    def _execute_trade(
        self,
        trade_date: str,
        signal: str,
        price: float,
        target_pct: float,
        current_pct: float,
        cash: float,
        shares: float,
        config: BacktestConfig,
    ) -> Optional[TradeRecord]:
        """执行交易"""
        equity = cash + shares * price
        target_value = equity * target_pct
        current_value = shares * price

        if target_value > current_value:
            # 买入
            buy_amount = target_value - current_value
            buy_amount = min(buy_amount, cash)
            buy_shares = buy_amount / price
            commission = buy_amount * config.commission_rate

            return TradeRecord(
                trade_date=trade_date,
                trade_type="buy",
                signal_level=signal,
                price=round(price, 4),
                shares=round(buy_shares, 2),
                amount=round(buy_amount - commission, 2),
                commission=round(commission, 2),
                reason=f"信号{signal}，目标仓位{target_pct*100:.0f}%",
            )
        elif target_value < current_value:
            # 卖出
            sell_value = current_value - target_value
            sell_shares = sell_value / price
            sell_amount = sell_value * (1 - config.commission_rate - config.stamp_tax_rate)

            return TradeRecord(
                trade_date=trade_date,
                trade_type="sell",
                signal_level=signal,
                price=round(price, 4),
                shares=round(sell_shares, 2),
                amount=round(sell_amount, 2),
                commission=round(sell_value * (config.commission_rate + config.stamp_tax_rate), 2),
                reason=f"信号{signal}，目标仓位{target_pct*100:.0f}%",
            )

        return None

    def _calc_metrics(
        self,
        equity_curve: list[EquityPoint],
        trades: list[TradeRecord],
        config: BacktestConfig,
    ) -> BacktestMetrics:
        """计算绩效指标"""
        if len(equity_curve) < 2:
            return BacktestMetrics()

        initial = config.initial_capital
        final = equity_curve[-1].equity

        # 总收益率
        total_return = (final - initial) / initial * 100

        # 年化收益率
        days = len(equity_curve)
        annual_return = ((final / initial) ** (252 / days) - 1) * 100 if days > 0 else 0.0

        # 最大回撤
        peak = initial
        max_dd = 0.0
        dd_duration = 0
        max_dd_duration = 0
        for pt in equity_curve:
            if pt.equity > peak:
                peak = pt.equity
                dd_duration = 0
            dd = (peak - pt.equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
            dd_duration += 1
            if dd > 0:
                max_dd_duration = max(max_dd_duration, dd_duration)

        # 波动率
        returns = [pt.daily_return for pt in equity_curve if pt.daily_return != 0]
        avg_return = sum(returns) / len(returns) if returns else 0
        variance = sum((r - avg_return) ** 2 for r in returns) / len(returns) if returns else 0
        daily_vol = math.sqrt(variance)
        annual_vol = daily_vol * math.sqrt(252) * 100

        # 夏普比率
        risk_free = 2.5  # 无风险利率 2.5%
        sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0.0

        # Calmar 比率
        calmar = annual_return / max_dd if max_dd > 0 else 0.0

        # 胜率
        win_trades = [t for t in trades if t.trade_type == "sell" and t.amount > 0]
        win_count = len(win_trades)
        total_sell = sum(1 for t in trades if t.trade_type == "sell")
        win_rate = (win_count / total_sell * 100) if total_sell > 0 else 0.0

        # 盈亏比
        if win_trades:
            avg_win = sum(t.amount for t in win_trades) / len(win_trades) if win_trades else 0
            lose_trades = [t for t in trades if t.trade_type == "sell" and t.amount <= 0]
            avg_lose = abs(sum(t.amount for t in lose_trades) / len(lose_trades)) if lose_trades else 1
            profit_loss_ratio = avg_win / avg_lose if avg_lose > 0 else 0
        else:
            profit_loss_ratio = 0.0

        return BacktestMetrics(
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_duration=max_dd_duration,
            sharpe_ratio=round(sharpe, 2),
            win_rate=round(win_rate, 2),
            profit_loss_ratio=round(profit_loss_ratio, 2),
            total_trades=len(trades),
            avg_hold_days=0.0,  # TODO
            calmar_ratio=round(calmar, 2),
            volatility=round(annual_vol, 2),
        )
