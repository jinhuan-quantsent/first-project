"""
回测引擎 — V5.0 扩展版
基于 V5 信号系统的策略回测框架

功能：
- 7级信号 → 5级行动映射（buy/sell_half/sell_all/hold）
- 5条风控规则（R1仓位上限/R2止损/R3止盈回撤/R4过热/R5回调偏离）
- 信号滞后缓冲
- 每日操作日志
- 风控统计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional
import math


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ActionRule:
    """信号 → 行动映射规则"""
    action_type: str  # buy, sell_half, sell_all, hold
    multiplier: float = 1.0
    label: str = ""


@dataclass
class RiskParams:
    """风控参数"""
    max_position: float = 0.95
    min_position: float = 0.05
    stop_loss: float = -0.15
    stop_loss_threshold: float = 1.0
    stop_loss_reduce_pct: float = 50.0
    take_profit: float = 0.30
    take_profit_drawdown: float = 0.10
    overheat_days: int = 10
    overheat_factor: float = 0.7
    pullback_lower: float = -0.08
    pullback_buy_mult: float = 0.5
    position_dev_lower: float = -0.05
    position_dev_buy_mult: float = 0.3
    base_buy_amount: float = 10000.0


# 默认行动映射
DEFAULT_ACTION_MAPPING: dict[str, dict] = {
    "S+": {"action_type": "buy", "multiplier": 2.0, "label": "大幅加仓"},
    "S":  {"action_type": "buy", "multiplier": 1.5, "label": "加仓"},
    "A":  {"action_type": "buy", "multiplier": 1.0, "label": "小幅加仓"},
    "B":  {"action_type": "hold", "multiplier": 0.0, "label": "持有"},
    "C":  {"action_type": "sell_half", "multiplier": 0.3, "label": "减仓30%"},
    "D":  {"action_type": "sell_half", "multiplier": 0.5, "label": "减仓50%"},
    "E":  {"action_type": "sell_all", "multiplier": 1.0, "label": "清仓"},
}


@dataclass
class BacktestConfig:
    """回测配置"""
    index_code: str = "SH000300"
    start_date: str = "2024-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 100000.0
    commission_rate: float = 0.0012  # 万1.2
    stamp_tax_rate: float = 0.001   # 千1（卖出）
    signal_strategy: str = "v5_signal"

    # Category 1: 信号映射
    signal_boundaries: list[float] = field(default_factory=lambda: [12.0, 25.0, 38.0, 52.0, 65.0, 80.0])
    signal_lag_days: int = 1

    # Category 2: 因子权重（向后兼容）
    buy_signals: list[str] = field(default_factory=lambda: ["S+", "S", "A"])
    sell_signals: list[str] = field(default_factory=lambda: ["D", "E"])
    hold_signals: list[str] = field(default_factory=lambda: ["B", "C"])

    # Category 3: 行动映射
    action_mapping: dict[str, ActionRule] = field(default_factory=lambda: {
        k: ActionRule(**v) for k, v in DEFAULT_ACTION_MAPPING.items()
    })

    # Category 5: 风控参数
    risk_params: RiskParams = field(default_factory=RiskParams)

    # 向后兼容
    max_position_pct: float = 1.0
    min_position_pct: float = 0.0


@dataclass
class TradeRecord:
    """交易记录"""
    trade_date: str
    trade_type: str  # buy, sell, risk_sell
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
    action_text: str = ""
    reason: str = ""
    is_risk_action: bool = False


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
    signal_accuracy: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    config: BacktestConfig
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    benchmark_curve: list[EquityPoint] = field(default_factory=list)
    daily_log: list[dict] = field(default_factory=list)
    risk_stats: dict = field(default_factory=dict)


# ============================================================
# 回测引擎
# ============================================================

class BacktestEngine:
    """V5.0 回测引擎 — 7级信号 + 5级行动 + 5条风控"""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self._config = config or BacktestConfig()

    def run(self, price_data: list[dict]) -> BacktestResult:
        """
        运行回测

        Args:
            price_data: [{date, close, signal_level, ...}, ...]
                        按日期升序排列的日线数据

        Returns:
            BacktestResult with daily_log and risk_stats
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
        daily_log: list[dict] = []

        # 初始状态
        cash = config.initial_capital
        shares = 0.0
        total_invested = config.initial_capital
        prev_equity = config.initial_capital

        # 买入持有基准
        benchmark_shares = config.initial_capital / price_data[0]["close"]
        benchmark_equity = config.initial_capital

        # 风控状态
        peak_portfolio_value = config.initial_capital
        stop_loss_triggered = False
        take_profit_triggered = False
        overheat_triggered = False
        consecutive_high_signal_days = 0

        # 信号滞后缓冲
        signal_buffer: list[str] = []

        # 风控统计
        risk_triggers = 0
        pullback_buys = 0
        deviation_buys = 0
        stop_loss_triggers = 0
        overheat_triggers = 0

        rp = config.risk_params

        for i, bar in enumerate(price_data):
            d = bar["date"]
            close = float(bar["close"])
            raw_signal = bar.get("signal_level", "B")

            # ---- 1. 信号滞后处理 ----
            signal_buffer.append(raw_signal)
            if config.signal_lag_days > 0 and len(signal_buffer) > config.signal_lag_days:
                effective_signal = signal_buffer[-(config.signal_lag_days + 1)]
            else:
                effective_signal = signal_buffer[0]

            # ---- 2. 获取行动映射 ----
            action = config.action_mapping.get(effective_signal, ActionRule("hold", 0, "持有"))

            # ---- 3. 计算当前组合状态 ----
            portfolio_value = cash + shares * close
            position_value = shares * close
            position_ratio = position_value / portfolio_value if portfolio_value > 0 else 0
            total_return_rate = (portfolio_value - total_invested) / total_invested if total_invested > 0 else 0

            if portfolio_value > peak_portfolio_value:
                peak_portfolio_value = portfolio_value

            # ---- 4. 过热信号统计 ----
            if effective_signal in ("C", "D", "E"):
                consecutive_high_signal_days += 1
            else:
                consecutive_high_signal_days = 0

            # ---- 5. 风控检查 R1-R5 ----
            risk_override: Optional[tuple] = None  # (type, sell_shares, reason)

            # R1: 仓位上限
            if position_ratio > rp.max_position and shares > 0:
                excess = position_ratio - rp.max_position
                sell_shares = shares * excess
                if sell_shares > 0:
                    risk_override = ("risk_sell", sell_shares, f"仓位超限({position_ratio*100:.1f}%>{rp.max_position*100:.0f}%)")

            # R2: 止损
            if total_return_rate < rp.stop_loss * rp.stop_loss_threshold and not stop_loss_triggered and shares > 0:
                stop_loss_triggered = True
                sell_pct = rp.stop_loss_reduce_pct / 100
                sell_shares = shares * sell_pct
                if sell_shares > 0:
                    risk_override = ("risk_sell", sell_shares, f"触发止损线(收益{total_return_rate*100:.1f}%<止损{rp.stop_loss*rp.stop_loss_threshold*100:.1f}%)")
                    stop_loss_triggers += 1

            # R3: 止盈回撤
            if total_return_rate > rp.take_profit and not take_profit_triggered and shares > 0:
                drawdown_from_peak = (portfolio_value - peak_portfolio_value) / peak_portfolio_value
                if drawdown_from_peak < -rp.take_profit_drawdown:
                    take_profit_triggered = True
                    sell_shares = shares * 0.5
                    if sell_shares > 0:
                        risk_override = ("risk_sell", sell_shares, f"触发止盈回撤(收益{total_return_rate*100:.1f}%，回撤{drawdown_from_peak*100:.1f}%)")

            # R4: 过热
            if consecutive_high_signal_days >= rp.overheat_days and not overheat_triggered and shares > 0:
                overheat_triggered = True
                target_shares = shares * rp.overheat_factor
                sell_shares = shares - target_shares
                if sell_shares > 0:
                    risk_override = ("risk_sell", sell_shares, f"过热连续{rp.overheat_days}天，仓位×{rp.overheat_factor}")
                    overheat_triggers += 1

            # ---- 6. 执行操作 ----
            action_text = ""
            is_risk = False
            trade_record = None

            if risk_override:
                # 风控减仓
                is_risk = True
                risk_triggers += 1
                _, sell_shares, reason = risk_override
                actual_sell = min(sell_shares, shares)
                sell_amount = actual_sell * close
                commission = sell_amount * (config.commission_rate + config.stamp_tax_rate)
                net_amount = sell_amount - commission

                shares -= actual_sell
                shares = max(0, shares)
                cash += net_amount
                action_text = f"风控减仓 ¥{sell_amount:,.0f}"

                trade_record = TradeRecord(
                    trade_date=d, trade_type="risk_sell",
                    signal_level=effective_signal,
                    price=round(close, 4), shares=round(actual_sell, 2),
                    amount=round(net_amount, 2), commission=round(commission, 2),
                    reason=reason,
                )
            elif action.action_type == "buy":
                if position_ratio >= rp.max_position:
                    action_text = "持有(仓位达上限)"
                else:
                    buy_amount = rp.base_buy_amount * action.multiplier
                    if buy_amount > cash:
                        buy_amount = cash * 0.95  # 留5%现金缓冲
                    if buy_amount > 0:
                        commission = buy_amount * config.commission_rate
                        actual_buy = buy_amount - commission
                        buy_shares = actual_buy / close
                        shares += buy_shares
                        total_invested += buy_amount
                        cash -= buy_amount
                        action_text = f"加仓 ¥{buy_amount:,.0f}"
                        trade_record = TradeRecord(
                            trade_date=d, trade_type="buy",
                            signal_level=effective_signal,
                            price=round(close, 4), shares=round(buy_shares, 2),
                            amount=round(actual_buy, 2), commission=round(commission, 2),
                            reason=f"信号{effective_signal}→{action.label}",
                        )
                    else:
                        action_text = "持有(现金不足)"
            elif action.action_type == "sell_half":
                if shares <= 0:
                    action_text = "持有(无持仓)"
                elif position_ratio <= rp.min_position:
                    action_text = "持有(仓位达下限)"
                else:
                    sell_shares = shares * action.multiplier
                    sell_amount = sell_shares * close
                    commission = sell_amount * (config.commission_rate + config.stamp_tax_rate)
                    net_amount = sell_amount - commission
                    shares -= sell_shares
                    cash += net_amount
                    action_text = f"减仓 ¥{sell_amount:,.0f}"
                    trade_record = TradeRecord(
                        trade_date=d, trade_type="sell",
                        signal_level=effective_signal,
                        price=round(close, 4), shares=round(sell_shares, 2),
                        amount=round(net_amount, 2), commission=round(commission, 2),
                        reason=f"信号{effective_signal}→{action.label}",
                    )
            elif action.action_type == "sell_all":
                if shares <= 0:
                    action_text = "持有(无持仓)"
                elif position_ratio <= rp.min_position:
                    action_text = "持有(仓位达下限)"
                else:
                    sell_amount = shares * close
                    commission = sell_amount * (config.commission_rate + config.stamp_tax_rate)
                    net_amount = sell_amount - commission
                    shares = 0
                    cash += net_amount
                    action_text = f"清仓 ¥{sell_amount:,.0f}"
                    trade_record = TradeRecord(
                        trade_date=d, trade_type="sell",
                        signal_level=effective_signal,
                        price=round(close, 4), shares=round(shares, 2),
                        amount=round(net_amount, 2), commission=round(commission, 2),
                        reason=f"信号{effective_signal}→{action.label}",
                    )
            else:
                action_text = "持有"

            # ---- R5: 回调/偏离加仓（只在hold状态下） ----
            if not risk_override and action.action_type == "hold" and shares > 0:
                drawdown_from_peak = (portfolio_value - peak_portfolio_value) / peak_portfolio_value
                # 回调加仓
                if drawdown_from_peak <= rp.pullback_lower and drawdown_from_peak > rp.pullback_lower * 2.5:
                    buy_amount = rp.base_buy_amount * rp.pullback_buy_mult
                    if buy_amount <= cash * 0.95:
                        commission = buy_amount * config.commission_rate
                        actual_buy = buy_amount - commission
                        buy_shares = actual_buy / close
                        shares += buy_shares
                        total_invested += buy_amount
                        cash -= buy_amount
                        action_text = f"回调加仓 ¥{buy_amount:,.0f}"
                        pullback_buys += 1
                        trade_record = TradeRecord(
                            trade_date=d, trade_type="buy",
                            signal_level=effective_signal,
                            price=round(close, 4), shares=round(buy_shares, 2),
                            amount=round(actual_buy, 2), commission=round(commission, 2),
                            reason=f"回调{drawdown_from_peak*100:.1f}%≤下限{rp.pullback_lower*100:.0f}%",
                        )
                # 偏离加仓
                elif position_ratio < (1 + rp.position_dev_lower) and position_ratio > 0 and action_text == "持有":
                    buy_amount = rp.base_buy_amount * rp.position_dev_buy_mult
                    if buy_amount <= cash * 0.95:
                        commission = buy_amount * config.commission_rate
                        actual_buy = buy_amount - commission
                        buy_shares = actual_buy / close
                        shares += buy_shares
                        total_invested += buy_amount
                        cash -= buy_amount
                        action_text = f"偏离加仓 ¥{buy_amount:,.0f}"
                        deviation_buys += 1
                        trade_record = TradeRecord(
                            trade_date=d, trade_type="buy",
                            signal_level=effective_signal,
                            price=round(close, 4), shares=round(buy_shares, 2),
                            amount=round(actual_buy, 2), commission=round(commission, 2),
                            reason=f"仓位{position_ratio*100:.1f}%偏离下限{(1+rp.position_dev_lower)*100:.0f}%",
                        )

            # ---- 重置风控触发器（条件恢复） ----
            if total_return_rate > rp.stop_loss * rp.stop_loss_threshold * 1.5:
                stop_loss_triggered = False
            if total_return_rate < rp.take_profit * 0.5:
                take_profit_triggered = False
            if consecutive_high_signal_days < rp.overheat_days // 2:
                overheat_triggered = False

            # ---- 记录交易 ----
            if trade_record:
                trades.append(trade_record)

            # ---- 计算权益 ----
            portfolio_value = cash + shares * close
            position_value = shares * close
            position_ratio = position_value / portfolio_value if portfolio_value > 0 else 0
            daily_return = (portfolio_value - prev_equity) / prev_equity if prev_equity > 0 else 0.0

            equity_curve.append(EquityPoint(
                date=d,
                equity=round(portfolio_value, 2),
                position_pct=round(position_ratio, 4),
                signal_level=effective_signal,
                daily_return=round(daily_return, 6),
                action_text=action_text,
                reason=f"综合→{effective_signal} {action.label}" + (" [风控]" if is_risk else ""),
                is_risk_action=is_risk,
            ))

            # ---- 记录每日日志 ----
            daily_log.append({
                "date": d,
                "signal": effective_signal,
                "nav": round(close, 4),
                "advice_text": action_text,
                "position_value": round(position_value, 2),
                "reason": f"综合→{effective_signal} {action.label}" + (" [风控]" if is_risk else ""),
            })

            # ---- 基准曲线 ----
            benchmark_equity = benchmark_shares * close
            benchmark_curve.append(EquityPoint(
                date=d,
                equity=round(benchmark_equity, 2),
                position_pct=1.0,
                signal_level="benchmark",
                daily_return=0.0,
            ))

            prev_equity = portfolio_value

        # ---- 计算绩效 ----
        metrics = self._calc_metrics(equity_curve, trades, config)

        # ---- 信号准确率 ----
        if equity_curve:
            correct_signals = sum(
                1 for pt in equity_curve
                if (pt.signal_level in ("S+", "S", "A") and pt.daily_return > 0)
                or (pt.signal_level in ("D", "E") and pt.daily_return < 0)
                or (pt.signal_level in ("B", "C"))
            )
            metrics.signal_accuracy = round(correct_signals / len(equity_curve) * 100, 1)

        # ---- 风控统计 ----
        risk_stats = {
            "risk_triggers": risk_triggers,
            "pullback_buys": pullback_buys,
            "deviation_buys": deviation_buys,
            "stop_loss_triggers": stop_loss_triggers,
            "overheat_triggers": overheat_triggers,
        }

        return BacktestResult(
            config=config,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=trades,
            benchmark_curve=benchmark_curve,
            daily_log=daily_log,
            risk_stats=risk_stats,
        )

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
        risk_free = 2.5
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
            avg_hold_days=0.0,
            calmar_ratio=round(calmar, 2),
            volatility=round(annual_vol, 2),
        )
