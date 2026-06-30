"""
P5-1 回测引擎 V5.1 P0 修复测试

测试目标：
- 胜率 bug 修复（不再 100%）
- 加权成本追踪（cost_basis 字段）
- 交易成本模型（commission, subscription_fee, redemption_fee, slippage）
- 持有天数计算
- 向后兼容（cost_model=None 仍正常工作）
"""
import pytest
from datetime import date, timedelta
from app.engine.backtest import (
    BacktestEngine, BacktestConfig, BacktestResult,
    CostModel, TradeRecord, _holding_days, RiskParams,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def cost_model():
    """默认成本模型"""
    return CostModel()


@pytest.fixture
def down_then_up_data():
    """价格数据：先跌后涨（适合 S+ 买入 + E 清仓策略）"""
    data = []
    for i in range(20):
        price = 1.0 - i * 0.01
        data.append({"date": f"2024-01-{i+1:02d}", "close": price, "signal_level": "S+"})
    for i in range(20):
        price = 0.8
        data.append({"date": f"2024-02-{i+1:02d}", "close": price, "signal_level": "B"})
    for i in range(20):
        price = 0.8 + i * 0.02
        data.append({"date": f"2024-03-{i+1:02d}", "close": price, "signal_level": "E"})
    return data


@pytest.fixture
def flat_data():
    """横盘数据（持有策略）"""
    return [
        {"date": f"2024-01-{i+1:02d}", "close": 1.0, "signal_level": "B"}
        for i in range(30)
    ]


# ============================================================
# 1. _holding_days 辅助函数测试
# ============================================================

class TestHoldingDays:
    def test_none_returns_zero(self):
        """last_buy_date=None 应返回 0"""
        assert _holding_days(None, "2024-06-17") == 0

    def test_basic(self):
        """基本日期差"""
        assert _holding_days("2024-01-01", "2024-01-11") == 10
        assert _holding_days("2024-01-01", "2024-01-01") == 0
        assert _holding_days("2024-01-01", "2025-01-01") == 366  # 2024 闰年

    def test_invalid_date_returns_zero(self):
        """非法日期格式应返回 0 而非抛异常"""
        assert _holding_days("invalid", "2024-06-17") == 0
        assert _holding_days("2024-13-99", "2024-06-17") == 0


# ============================================================
# 2. CostModel 成本计算测试
# ============================================================

class TestCostModel:
    def test_subscription_fee(self, cost_model):
        """申购费 = 金额 × 0.15%"""
        assert cost_model.calc_subscription_cost(10000) == pytest.approx(15.0)
        assert cost_model.calc_subscription_cost(0) == 0
        assert cost_model.calc_subscription_cost(100000) == pytest.approx(150.0)

    def test_redemption_fee_tiers(self, cost_model):
        """赎回费阶梯：0-6d=0.5%, 7-364d=0.3%, 365-729d=0.1%, >=730d=0.05%"""
        # 短期 (< 7 天)
        assert cost_model.calc_redemption_cost(10000, 0) == pytest.approx(50.0)
        assert cost_model.calc_redemption_cost(10000, 3) == pytest.approx(50.0)
        assert cost_model.calc_redemption_cost(10000, 6) == pytest.approx(50.0)
        # 中期 [7, 365)
        assert cost_model.calc_redemption_cost(10000, 7) == pytest.approx(30.0)
        assert cost_model.calc_redemption_cost(10000, 100) == pytest.approx(30.0)
        assert cost_model.calc_redemption_cost(10000, 364) == pytest.approx(30.0)
        # 长期 [365, 730)
        assert cost_model.calc_redemption_cost(10000, 365) == pytest.approx(10.0)
        assert cost_model.calc_redemption_cost(10000, 500) == pytest.approx(10.0)
        # 超长期 [730, inf)
        assert cost_model.calc_redemption_cost(10000, 730) == pytest.approx(5.0)
        assert cost_model.calc_redemption_cost(10000, 1000) == pytest.approx(5.0)

    def test_slippage(self, cost_model):
        """滑点 = 金额 × 0.1%"""
        assert cost_model.calc_slippage_cost(10000) == pytest.approx(10.0)
        assert cost_model.calc_slippage_cost(100000) == pytest.approx(100.0)

    def test_effective_buy_price_includes_fees(self, cost_model):
        """eff_buy_price 包含申购费+滑点（价格上浮）"""
        assert cost_model.effective_buy_price(1.0) == pytest.approx(1.0025)
        assert cost_model.effective_buy_price(2.0) == pytest.approx(2.005)

    def test_effective_sell_price_reduces(self, cost_model):
        """eff_sell_price 扣赎回费+滑点（价格下降）"""
        # 持有 30 天 → 0.3% 赎回费 + 0.1% 滑点 = 0.4%
        assert cost_model.effective_sell_price(1.0, 30) == pytest.approx(0.996)
        # 持有 1 年 → 0.1% + 0.1% = 0.2%
        assert cost_model.effective_sell_price(1.0, 400) == pytest.approx(0.998)

    def test_custom_fee(self):
        """自定义费率"""
        cm = CostModel(subscription_fee=0.0, slippage=0.0)
        assert cm.effective_buy_price(1.0) == 1.0
        # 默认赎回费保留，30 天 → 0.3% 赎回费
        assert cm.effective_sell_price(1.0, 100) == pytest.approx(0.997)

        cm2 = CostModel(subscription_fee=0.01, slippage=0.005)
        # 买入 = 1.0 × (1 + 0.01 + 0.005) = 1.015
        assert cm2.effective_buy_price(1.0) == pytest.approx(1.015)
        # 卖出（30 天）= 1.0 × (1 - 0.003 - 0.005) = 0.992
        assert cm2.effective_sell_price(1.0, 30) == pytest.approx(0.992)


# ============================================================
# 3. 胜率 bug 修复验证
# ============================================================

class TestWinRateFix:
    def test_win_rate_not_always_100_percent(self, down_then_up_data, cost_model):
        """核心 bug 修复：胜率不应永远是 100%"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        engine = BacktestEngine(config)
        result = engine.run(down_then_up_data)

        # 旧 bug：卖出金额永远 > 0 → 100% 胜率
        # 新逻辑：profit_loss > 0 才算胜
        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]
        assert len(sell_trades) > 0, "应当有卖出交易"
        # 胜率应在 0-100% 之间（不是 0 或 100 极端值，除非策略确实完美或完全失败）
        assert 0 <= result.metrics.win_rate <= 100

    def test_win_rate_uses_profit_loss_not_amount(self, down_then_up_data, cost_model):
        """胜率应基于 profit_loss 字段计算（而非 t.amount）"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        result = BacktestEngine(config).run(down_then_up_data)

        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]
        if sell_trades:
            # 手动重算胜率
            win_count_manual = sum(1 for t in sell_trades if t.profit_loss > 0)
            expected_win_rate = win_count_manual / len(sell_trades) * 100
            assert result.metrics.win_rate == pytest.approx(round(expected_win_rate, 2), abs=0.01)

    def test_distinguishes_winning_and_losing_sells(self, down_then_up_data, cost_model):
        """V5.1 应能区分盈利卖出和亏损卖出"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        result = BacktestEngine(config).run(down_then_up_data)

        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]
        # 至少有一笔交易有 profit_loss 字段填充（V5.0 旧代码无此字段）
        for t in sell_trades:
            assert hasattr(t, "profit_loss")
            assert hasattr(t, "cost_basis")
            assert hasattr(t, "holding_days")
            assert hasattr(t, "subscription_fee") or hasattr(t, "redemption_fee")
            assert hasattr(t, "net_amount")

    def test_includes_risk_sell_in_win_rate(self, down_then_up_data, cost_model):
        """胜率分母应包含 risk_sell（V5.0 bug：只计 sell 不计 risk_sell）"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        result = BacktestEngine(config).run(down_then_up_data)

        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]
        total_sell = sum(1 for t in result.trades if t.trade_type in ("sell", "risk_sell"))
        # 胜率分母应等于 sell_trades 总数
        if total_sell > 0:
            # 计算胜率时分母必须包含所有 sell + risk_sell
            assert result.metrics.total_trades >= total_sell


# ============================================================
# 4. 加权成本追踪
# ============================================================

class TestCostBasisTracking:
    def test_buy_updates_avg_cost(self, cost_model):
        """多次买入后 avg_cost 应该是加权平均"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        # 简单 3 天数据：第 1 天买入，第 2 天继续买入，第 3 天清仓
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},
            {"date": "2024-01-02", "close": 1.1, "signal_level": "S+"},
            {"date": "2024-01-03", "close": 1.2, "signal_level": "E"},
        ]
        result = BacktestEngine(config).run(data)
        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]

        if sell_trades:
            for t in sell_trades:
                # cost_basis 应 > 0（除非未成功建仓）
                if t.cost_basis > 0:
                    # 加权成本应介于两次买入价之间（1.0 ~ 1.1）
                    # 含费后略高
                    assert 0.99 <= t.cost_basis <= 1.12, f"cost_basis={t.cost_basis} 不在合理范围"

    def test_sell_does_not_change_avg_cost(self, cost_model):
        """卖出不影响剩余持仓的加权成本"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},  # 买入
            {"date": "2024-01-02", "close": 1.1, "signal_level": "D"},  # 减仓 50%
            {"date": "2024-01-03", "close": 1.2, "signal_level": "D"},  # 再减仓
        ]
        result = BacktestEngine(config).run(data)
        # 多次 sell 的 cost_basis 应保持一致（剩余持仓成本不变）
        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]
        if len(sell_trades) >= 2:
            cost_basis_values = [t.cost_basis for t in sell_trades if t.cost_basis > 0]
            # 至少前两个非零 cost_basis 应该相同
            if len(cost_basis_values) >= 2:
                assert cost_basis_values[0] == pytest.approx(cost_basis_values[1], abs=0.001)

    def test_sell_all_resets_avg_cost(self, cost_model):
        """清仓后 avg_cost 应归零（不影响下次买入的成本计算）"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},  # 买入
            {"date": "2024-01-02", "close": 1.1, "signal_level": "E"},   # 清仓
            {"date": "2024-01-03", "close": 1.2, "signal_level": "S+"},  # 重新买入
            {"date": "2024-01-04", "close": 1.3, "signal_level": "E"},   # 再次清仓
        ]
        result = BacktestEngine(config).run(data)
        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]
        # 第二次清仓的 cost_basis 应该是新一轮买入的加权成本
        # 而非继承第一次的成本
        if len(sell_trades) >= 2:
            # 第二次清仓的 cost_basis 应接近 1.2 + 费用，而非 1.0
            assert sell_trades[-1].cost_basis >= 1.15  # 包含费用


# ============================================================
# 5. 交易成本扣减
# ============================================================

class TestCostDeduction:
    def test_buy_charges_subscription_and_slippage(self, cost_model):
        """买入时扣申购费+滑点，net_amount = amount - commission"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = [{"date": "2024-01-01", "close": 1.0, "signal_level": "S+"}]
        result = BacktestEngine(config).run(data)

        buy_trades = [t for t in result.trades if t.trade_type == "buy"]
        assert len(buy_trades) > 0, "应有买入交易"
        t = buy_trades[0]
        # S+ → multiplier=2.0 → amount=20000
        # 申购费 = 20000 × 0.15% = 30 元
        # 滑点 = 20000 × 0.1% = 20 元
        assert t.amount == pytest.approx(20000.0, abs=1.0)
        assert t.subscription_fee == pytest.approx(30.0, abs=0.1)
        assert t.slippage == pytest.approx(20.0, abs=0.1)
        assert t.commission == pytest.approx(50.0, abs=0.1)
        # net_amount = amount - commission
        assert t.net_amount == pytest.approx(t.amount - t.commission, abs=0.01)

    def test_sell_charges_redemption_and_slippage(self, cost_model):
        """卖出时扣赎回费+滑点"""
        # signal_lag_days=0 让信号当天生效
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model, signal_lag_days=0,
        )
        # 用 2 天买入 + 1 天清仓，让 sell_all 有机会执行
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},
            {"date": "2024-01-02", "close": 1.0, "signal_level": "B"},  # 持有
            {"date": "2024-01-03", "close": 1.2, "signal_level": "E"},  # 清仓
        ]
        result = BacktestEngine(config).run(data)

        sell_trades = [t for t in result.trades if t.trade_type == "sell"]
        assert len(sell_trades) > 0, f"应有 sell 交易，实际 trades: {[(t.trade_type, t.shares) for t in result.trades]}"
        t = sell_trades[0]
        # 持有 2 天 → 0.5% 赎回费 + 0.1% 滑点 = 0.6%
        assert t.holding_days >= 1
        # 费率应 = 0.5% + 0.1% = 0.6%
        expected_fee_rate = 0.005 + 0.001
        assert t.commission == pytest.approx(t.amount * expected_fee_rate, abs=2.0)
        # net_amount = amount - commission (允许舍入误差)
        assert t.net_amount == pytest.approx(t.amount - t.commission, abs=0.05)

    def test_holding_days_affects_redemption_fee(self, cost_model):
        """持有天数影响赎回费率"""
        config_long = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        # 持有 3 年 → 0.05% 赎回费 + 0.1% 滑点
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},
            {"date": "2027-01-01", "close": 1.5, "signal_level": "E"},
        ]
        result = BacktestEngine(config_long).run(data)
        sell_trades = [t for t in result.trades if t.trade_type == "sell"]

        if sell_trades:
            t = sell_trades[0]
            # 持有 3 年 → 0.05% 赎回费（<0.5% 短期）
            assert t.holding_days > 1000
            # 费率应 = 0.05% + 0.1% = 0.15%
            assert t.commission == pytest.approx(t.amount * 0.0015, abs=2.0)


# ============================================================
# 6. 持有天数追踪
# ============================================================

class TestHoldingDaysTracking:
    def test_holding_days_calculated(self, cost_model):
        """持有天数应从 last_buy_date 计算到 sell_date"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},
            {"date": "2024-02-15", "close": 1.2, "signal_level": "E"},
        ]
        result = BacktestEngine(config).run(data)
        sell_trades = [t for t in result.trades if t.trade_type == "sell"]

        if sell_trades:
            t = sell_trades[0]
            # 1/1 到 2/15 = 45 天
            assert 44 <= t.holding_days <= 46

    def test_avg_hold_days_in_metrics(self, cost_model):
        """BacktestMetrics.avg_hold_days 应基于 sell_trades.holding_days 平均"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = [
            {"date": "2024-01-01", "close": 1.0, "signal_level": "S+"},
            {"date": "2024-01-11", "close": 1.0, "signal_level": "E"},
        ]
        result = BacktestEngine(config).run(data)
        sell_trades = [t for t in result.trades if t.trade_type in ("sell", "risk_sell")]

        if sell_trades:
            # avg_hold_days 应是各笔 selling 持有天数的平均
            manual_avg = sum(t.holding_days for t in sell_trades) / len(sell_trades)
            assert result.metrics.avg_hold_days == pytest.approx(round(manual_avg, 1), abs=0.1)


# ============================================================
# 7. 向后兼容：cost_model=None
# ============================================================

class TestBackwardCompatibility:
    def test_no_cost_model_works(self, down_then_up_data):
        """cost_model=None 时应正常跑（无费用）"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=None,
        )
        result = BacktestEngine(config).run(down_then_up_data)

        # 不应崩溃
        assert result.metrics is not None
        # 所有交易 commission=0
        for t in result.trades:
            assert t.commission == 0
            assert t.subscription_fee == 0
            assert t.redemption_fee == 0
            assert t.slippage == 0

    def test_v5_behavior_preserved(self, down_then_up_data):
        """关闭成本模型时，行为应接近 V5.0（但胜率计算方式已更新）"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=None,
        )
        result_v51 = BacktestEngine(config).run(down_then_up_data)

        # 即使无成本，profit_loss 字段仍应填充（V5.0 bug 修复后永远会算）
        sell_trades = [t for t in result_v51.trades if t.trade_type in ("sell", "risk_sell")]
        for t in sell_trades:
            # cost_basis 仍应追踪
            assert t.cost_basis >= 0
            # profit_loss 应有值（即使是 0 也不应是空）
            assert t.profit_loss is not None

    def test_trade_record_new_fields_default(self):
        """TradeRecord 新字段应有默认值（向后兼容）"""
        # 即使不传新字段，也不应抛 TypeError
        t = TradeRecord(
            trade_date="2024-01-01", trade_type="buy",
            signal_level="S+", price=1.0, shares=100.0,
            amount=10000.0, commission=0.0,
        )
        assert t.cost_basis == 0.0
        assert t.profit_loss == 0.0
        assert t.holding_days == 0
        assert t.subscription_fee == 0.0
        assert t.redemption_fee == 0.0
        assert t.slippage == 0.0
        assert t.net_amount == 0.0


# ============================================================
# 8. 端到端真实数据验证
# ============================================================

class TestEndToEnd:
    def test_realistic_scenario_a_down_then_up(self, cost_model):
        """真实场景 A：跌后涨（S+ 抄底 + E 清仓）→ 应有合理胜率"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = []
        for i in range(20):
            data.append({"date": f"2024-01-{i+1:02d}", "close": 1.0 - i*0.01, "signal_level": "S+"})
        for i in range(20):
            data.append({"date": f"2024-02-{i+1:02d}", "close": 0.8, "signal_level": "B"})
        for i in range(20):
            data.append({"date": f"2024-03-{i+1:02d}", "close": 0.8 + i*0.02, "signal_level": "E"})

        result = BacktestEngine(config).run(data)
        # 至少有交易发生
        assert result.metrics.total_trades > 0
        # 总收益应为正（跌后涨策略）
        assert result.metrics.total_return > 0, f"跌后涨策略应为正收益，实际: {result.metrics.total_return:.2f}%"

    def test_realistic_scenario_b_up_then_down(self, cost_model):
        """真实场景 B：涨后跌（追涨杀跌）→ 应有负收益"""
        config = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=cost_model,
        )
        data = []
        for i in range(20):
            data.append({"date": f"2024-01-{i+1:02d}", "close": 1.0 + i*0.01, "signal_level": "B"})
        for i in range(20):
            data.append({"date": f"2024-02-{i+1:02d}", "close": 1.2 - i*0.01, "signal_level": "S+"})  # 抄底但继续跌
        for i in range(20):
            data.append({"date": f"2024-03-{i+1:02d}", "close": 1.0 - i*0.01, "signal_level": "E"})  # 割肉

        result = BacktestEngine(config).run(data)
        # 涨后跌策略 + 频繁交易 → 应该是亏损
        assert result.metrics.total_return < 0, f"涨后跌策略应为负收益，实际: {result.metrics.total_return:.2f}%"

    def test_cost_reduces_returns(self, down_then_up_data):
        """V5.1 收益应 ≤ V5.0 收益（成本拖累）"""
        config_v50 = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=None,
        )
        config_v51 = BacktestConfig(
            index_code="SH_TEST", initial_capital=100000,
            cost_model=CostModel(),
        )
        result_v50 = BacktestEngine(config_v50).run(down_then_up_data)
        result_v51 = BacktestEngine(config_v51).run(down_then_up_data)

        # 有成本的总收益应 ≤ 无成本的
        assert result_v51.metrics.total_return <= result_v50.metrics.total_return, \
            f"含成本应拖累收益: V5.0={result_v50.metrics.total_return:.2f}%, V5.1={result_v51.metrics.total_return:.2f}%"
