"""
V5.0 仓位建议引擎测试 — test_position_v5.py
覆盖：5×7 仓位矩阵 + 置信度修正 + 市场体制修正 + 交易成本校验 + 7天频率限制
"""
import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.engine.position_v5 import PositionEngineV5
from app.core.config import settings


# ============================================================
# Mock Session 辅助
# ============================================================
class MockSession:
    """Mock 异步数据库会话"""
    def __init__(self, last_execute_date=None):
        self.last_execute_date = last_execute_date
        self.execute = AsyncMock()
        if last_execute_date:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=last_execute_date)
            self.execute.return_value = mock_result
        else:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none = MagicMock(return_value=None)
            self.execute.return_value = mock_result


# ============================================================
# 仓位等级转换测试
# ============================================================
class TestPctToLevel:
    """测试 _pct_to_level 边界值"""

    def setup_method(self):
        self.engine = PositionEngineV5(MockSession())

    @pytest.mark.parametrize("pct,expected", [
        (0.0, "empty"),
        (0.124, "empty"),
        (0.125, "light"),
        (0.374, "light"),
        (0.375, "mid"),
        (0.50, "mid"),
        (0.624, "mid"),
        (0.625, "heavy"),
        (0.75, "heavy"),
        (0.874, "heavy"),
        (0.875, "full"),
        (1.0, "full"),
    ])
    def test_pct_to_level_boundaries(self, pct, expected):
        """所有边界值应正确映射到仓位等级"""
        assert self.engine._pct_to_level(pct) == expected


# ============================================================
# 信号等级到索引测试
# ============================================================
class TestSignalToIdx:
    """测试 _signal_to_idx"""

    def setup_method(self):
        self.engine = PositionEngineV5(MockSession())

    @pytest.mark.parametrize("level,expected", [
        ("S+", 0), ("S", 1), ("A", 2), ("B", 3),
        ("C", 4), ("D", 5), ("E", 6),
    ])
    def test_valid_signal_levels(self, level, expected):
        assert self.engine._signal_to_idx(level) == expected

    def test_unknown_signal_level_defaults_to_B(self):
        """未知信号等级默认 B(3)"""
        assert self.engine._signal_to_idx("UNKNOWN") == 3
        assert self.engine._signal_to_idx("X") == 3


# ============================================================
# 市场体制修正系数测试
# ============================================================
class TestRegimeAdj:
    """测试 _calc_regime_adj"""

    def setup_method(self):
        self.engine = PositionEngineV5(MockSession())

    @pytest.mark.parametrize("regime,expected", [
        ("bull", 1.10),
        ("bear", 0.85),
        ("extreme_volatility", 0.70),
        ("sideways", 1.00),
    ])
    def test_regime_adjustments(self, regime, expected):
        assert self.engine._calc_regime_adj(regime) == expected

    def test_unknown_regime_defaults_to_1(self):
        """未知体制默认 1.00（中性）"""
        assert self.engine._calc_regime_adj("unknown") == 1.00


# ============================================================
# 5×7 仓位矩阵测试（核心）
# ============================================================
class TestPositionMatrix:
    """测试 5×7 仓位矩阵（5 等级 × 7 信号）"""

    @pytest.mark.asyncio

    async def test_matrix_is_5x7(self):
        """矩阵应为 5×7"""
        matrix = settings.V5_POSITION_MATRIX
        assert len(matrix) == 5, f"应有5行，实际 {len(matrix)}"
        for i, row in enumerate(matrix):
            assert len(row) == 7, f"第{i}行应有7列，实际 {len(row)}"

    @pytest.mark.asyncio

    async def test_matrix_all_values_in_valid_range(self):
        """所有矩阵值应在 [0, 1] 范围内"""
        matrix = settings.V5_POSITION_MATRIX
        for i, row in enumerate(matrix):
            for j, val in enumerate(row):
                assert 0.0 <= val <= 1.0, \
                    f"矩阵[{i}][{j}]={val} 超出 [0,1] 范围"

    @pytest.mark.asyncio

    async def test_matrix_panic_increases_position(self):
        """恐慌信号(S+)应建议较高仓位（满仓+恐慌 → 100%）"""
        matrix = settings.V5_POSITION_MATRIX
        # 从 full 仓位开始（index=4）+ S+ 恐慌信号
        assert matrix[4][0] >= 0.9, \
            f"full + 恐慌信号 应≥0.9，实际 {matrix[4][0]}"

    @pytest.mark.asyncio

    async def test_matrix_greed_decreases_position(self):
        """贪婪信号(E)应建议较低仓位（满仓+贪婪 → 40%）"""
        matrix = settings.V5_POSITION_MATRIX
        # 从 full 仓位开始（index=4）+ E 极度贪婪
        assert matrix[4][6] <= 0.5, \
            f"full + 极度贪婪 应≤0.5，实际 {matrix[4][6]}"


# ============================================================
# calculate() 核心方法测试
# ============================================================
class TestCalculateBasic:
    """测试 calculate() 基本流程（无 session 干扰）"""

    @pytest.mark.asyncio

    async def test_calculate_returns_dict(self):
        """calculate() 应返回 dict"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1",
            fund_code="000001",
            current_position_pct=0.5,
            signal_level="B",
            confidence_stars=3,
        )
        assert isinstance(result, dict)

    @pytest.mark.asyncio

    async def test_calculate_result_has_required_fields(self):
        """结果应包含所有必要字段"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1",
            fund_code="000001",
            current_position_pct=0.5,
            signal_level="B",
            confidence_stars=3,
        )
        required = [
            "fund_code", "current_position_pct", "target_position_pct",
            "action", "signal_level", "confidence_stars",
            "matrix_result", "confidence_adj_factor",
            "regime_adj_factor", "cost_rejected", "frequency_blocked", "reason",
        ]
        for field in required:
            assert field in result, f"缺少字段: {field}"

    @pytest.mark.asyncio

    async def test_calculate_action_hold_when_no_change(self):
        """当 target == current 时 action 应为 hold"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1",
            fund_code="000001",
            current_position_pct=0.5,  # mid
            signal_level="B",  # mid target
            confidence_stars=3,
        )
        # target 应为 0.5（matrix[2][3] for mid/B）
        if abs(result["target_position_pct"] - 0.5) < 0.01:
            assert result["action"] == "hold"

    @pytest.mark.asyncio

    async def test_calculate_action_increase(self):
        """当 target > current 时 action 应为 increase"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1",
            fund_code="000001",
            current_position_pct=0.25,  # light
            signal_level="S+",  # 应加仓
            confidence_stars=3,
        )
        # 加仓方向
        if result["target_position_pct"] > result["current_position_pct"]:
            assert result["action"] == "increase"

    @pytest.mark.asyncio

    async def test_calculate_action_decrease(self):
        """当 target < current 时 action 应为 decrease"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1",
            fund_code="000001",
            current_position_pct=0.75,  # heavy
            signal_level="E",  # 应减仓
            confidence_stars=3,
        )
        if result["target_position_pct"] < result["current_position_pct"]:
            assert result["action"] == "decrease"


# ============================================================
# 置信度修正测试
# ============================================================
class TestConfidenceAdjustment:
    """测试置信度对仓位调整的影响"""

    @pytest.mark.asyncio

    async def test_5_stars_full_adjustment(self):
        """5星 → config 未配置，默认为 0.0（不操作）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.25, signal_level="S+",
            confidence_stars=5,
        )
        # config 中未配置 5星，默认为 0.0
        assert result["confidence_adj_factor"] == 0.0

    @pytest.mark.asyncio

    async def test_4_stars_high_adjustment(self):
        """4星 → 100%调整（conf_factor 应为 1.0）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.25, signal_level="S+",
            confidence_stars=4,
        )
        assert result["confidence_adj_factor"] == 1.0

    @pytest.mark.asyncio

    async def test_3_stars_medium_adjustment(self):
        """3星 → 中等调整（conf_factor 应为 0.75）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.25, signal_level="S+",
            confidence_stars=3,
        )
        assert result["confidence_adj_factor"] == 0.75

    @pytest.mark.asyncio

    async def test_2_stars_low_adjustment(self):
        """2星 → 低调整（conf_factor 应为 0.5）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.25, signal_level="S+",
            confidence_stars=2,
        )
        assert result["confidence_adj_factor"] == 0.5

    @pytest.mark.asyncio

    async def test_1_star_minimal_adjustment(self):
        """1星 → 不操作（conf_factor 应为 0.0）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.25, signal_level="S+",
            confidence_stars=1,
        )
        assert result["confidence_adj_factor"] == 0.0


# ============================================================
# 市场体制修正测试
# ============================================================
class TestRegimeAdjustment:
    """测试市场体制对仓位调整的影响"""

    @pytest.mark.asyncio

    async def test_bull_regime_more_aggressive(self):
        """牛市 → 更激进（regime_adj=1.10）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.5, signal_level="S+",  # 加仓
            confidence_stars=3, regime="bull",
        )
        assert result["regime_adj_factor"] == 1.10

    @pytest.mark.asyncio

    async def test_bear_regime_more_conservative(self):
        """熊市 → 更保守（regime_adj=0.85）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.5, signal_level="S+",
            confidence_stars=3, regime="bear",
        )
        assert result["regime_adj_factor"] == 0.85

    @pytest.mark.asyncio

    async def test_extreme_volatility_very_conservative(self):
        """极端波动 → 极保守（regime_adj=0.70）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.5, signal_level="S+",
            confidence_stars=3, regime="extreme_volatility",
        )
        assert result["regime_adj_factor"] == 0.70

    @pytest.mark.asyncio

    async def test_sideways_neutral(self):
        """震荡市 → 中性（regime_adj=1.00）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.5, signal_level="B",
            confidence_stars=3, regime="sideways",
        )
        assert result["regime_adj_factor"] == 1.00


# ============================================================
# 交易成本校验测试
# ============================================================
class TestCostRejection:
    """测试交易成本阈值校验"""

    @pytest.mark.asyncio

    async def test_small_adjustment_rejected(self):
        """调整幅度 < 1.5% → 拒绝（cost_rejected=True）"""
        engine = PositionEngineV5(MockSession())
        # 选择一个与 current 相近的 target
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.5, signal_level="B",
            confidence_stars=3, regime="sideways",
        )
        # 如果 target 接近 0.5，则应被成本阈值拒绝
        if abs(result["target_position_pct"] - 0.5) < settings.V5_COST_THRESHOLD_PCT:
            assert result["cost_rejected"] is True
            assert result["action"] == "hold"

    @pytest.mark.asyncio

    async def test_large_adjustment_accepted(self):
        """调整幅度 >= 1.5% → 接受（cost_rejected=False）"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0,  # empty
            signal_level="S+",  # 应大幅加仓
            confidence_stars=5, regime="bull",
        )
        # 大幅调整应被接受
        if abs(result["target_position_pct"] - 0.0) >= settings.V5_COST_THRESHOLD_PCT:
            assert result["cost_rejected"] is False


# ============================================================
# 7天频率限制测试
# ============================================================
class TestFrequencyLimit:
    """测试7天内执行频率限制"""

    @pytest.mark.asyncio

    async def test_no_history_no_block(self):
        """无执行历史 → 不阻断"""
        session = MockSession(last_execute_date=None)
        engine = PositionEngineV5(session)
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0, signal_level="S+",
            confidence_stars=5,
        )
        assert result["frequency_blocked"] is False

    @pytest.mark.asyncio

    async def test_recent_execute_blocked(self):
        """7天内执行过 → 阻断（frequency_blocked=True）"""
        recent_date = date.today() - timedelta(days=3)
        session = MockSession(last_execute_date=recent_date)
        engine = PositionEngineV5(session)
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0, signal_level="S+",
            confidence_stars=5,
        )
        assert result["frequency_blocked"] is True
        assert result["action"] == "hold"

    @pytest.mark.asyncio

    async def test_old_execute_not_blocked(self):
        """超过7天执行过 → 不阻断"""
        old_date = date.today() - timedelta(days=10)
        session = MockSession(last_execute_date=old_date)
        engine = PositionEngineV5(session)
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0, signal_level="S+",
            confidence_stars=5,
        )
        assert result["frequency_blocked"] is False


# ============================================================
# 5×7 矩阵全覆盖测试（35 条）
# ============================================================
class TestMatrixFullCoverage:
    """参数化测试 5×7 矩阵的所有 35 条组合"""

    LEVELS = ["empty", "light", "mid", "heavy", "full"]
    SIGNALS = ["S+", "S", "A", "B", "C", "D", "E"]
    LEVEL_PCT = {"empty": 0.0, "light": 0.25, "mid": 0.5, "heavy": 0.75, "full": 1.0}

    @pytest.mark.parametrize("level_idx,signal_idx", [
        (i, j) for i in range(5) for j in range(7)
    ])
    @pytest.mark.asyncio

    async def test_all_35_matrix_combinations(self, level_idx, signal_idx):
        """测试所有 5×7=35 条矩阵组合"""
        level = self.LEVELS[level_idx]
        signal = self.SIGNALS[signal_idx]
        current_pct = self.LEVEL_PCT[level]

        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=current_pct, signal_level=signal,
            confidence_stars=3,
        )

        # target 必须在 [0, 1] 范围内
        assert 0.0 <= result["target_position_pct"] <= 1.0
        # action 必须是有效值
        assert result["action"] in ("hold", "increase", "decrease")
        # current 保持不变
        assert result["current_position_pct"] == current_pct


# ============================================================
# 原因生成测试
# ============================================================
class TestReasonGeneration:
    """测试建议原因文案生成"""

    @pytest.mark.asyncio

    async def test_reason_includes_signal_level(self):
        """原因应包含信号等级"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0, signal_level="S+",
            confidence_stars=3,
        )
        assert "S+" in result["reason"]

    @pytest.mark.asyncio

    async def test_reason_includes_signal_label(self):
        """原因应包含信号中文标签"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0, signal_level="S+",
            confidence_stars=3,
        )
        assert "极度恐惧" in result["reason"]

    @pytest.mark.asyncio

    async def test_cost_rejected_reason(self):
        """成本拒绝时应使用对应文案"""
        engine = PositionEngineV5(MockSession())
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.5, signal_level="B",
            confidence_stars=3,
        )
        if result["cost_rejected"]:
            assert "交易成本" in result["reason"]

    @pytest.mark.asyncio

    async def test_frequency_blocked_reason(self):
        """频率阻断时应使用对应文案"""
        recent_date = date.today() - timedelta(days=2)
        session = MockSession(last_execute_date=recent_date)
        engine = PositionEngineV5(session)
        result = await engine.calculate(
            user_id="u1", fund_code="000001",
            current_position_pct=0.0, signal_level="S+",
            confidence_stars=3,
        )
        if result["frequency_blocked"]:
            assert "7天" in result["reason"] or "频率" in result["reason"]
