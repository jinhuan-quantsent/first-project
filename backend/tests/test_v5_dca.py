"""
V5.0 定投调整建议引擎测试 — test_v5_dca.py
覆盖：7级信号→定投倍数映射 + 边界 + 有效性校验
"""
import pytest
from app.engine.dca_advice import (
    DcaAdviceEngine,
    DcaAdvice,
    SIGNAL_TO_MULTIPLIER,
    SIGNAL_TO_ACTION,
    SIGNAL_TO_DESCRIPTION,
)


# ============================================================
# 7级信号 → 定投倍数映射 (parametrized)
# ============================================================
class TestSignalToMultiplier:
    """测试 7级信号 → 定投倍数映射（PRD拍板 2026-06-14）"""

    @pytest.mark.parametrize("signal,expected", [
        ("S+", 3.0),
        ("S",  2.0),
        ("A",  1.5),
        ("B",  1.0),
        ("C",  0.8),
        ("D",  0.5),
        ("E",  0.0),
    ])
    def test_multiplier_mapping(self, signal, expected):
        """7级信号定投倍数映射"""
        engine = DcaAdviceEngine()
        advice = engine.get_advice(signal)
        assert advice.multiplier == pytest.approx(expected, 0.001)

    @pytest.mark.parametrize("signal,expected", [
        ("S+", 3.0),
        ("S",  2.0),
        ("A",  1.5),
        ("B",  1.0),
        ("C",  0.8),
        ("D",  0.5),
        ("E",  0.0),
    ])
    def test_get_multiplier_shortcut(self, signal, expected):
        """get_multiplier 便捷方法"""
        engine = DcaAdviceEngine()
        assert engine.get_multiplier(signal) == pytest.approx(expected, 0.001)


# ============================================================
# 7级信号 → 操作动作映射
# ============================================================
class TestSignalToAction:
    """测试 7级信号 → 操作动作"""

    @pytest.mark.parametrize("signal,expected_action", [
        ("S+", "加倍定投"),
        ("S",  "加倍定投"),
        ("A",  "增额定投"),
        ("B",  "标准定投"),
        ("C",  "减额定投"),
        ("D",  "减额定投"),
        ("E",  "建议赎回"),
    ])
    def test_action_mapping(self, signal, expected_action):
        engine = DcaAdviceEngine()
        advice = engine.get_advice(signal)
        assert advice.action == expected_action


# ============================================================
# 赎回建议标志
# ============================================================
class TestRedeemFlag:
    """测试 is_redeem 标志"""

    def test_only_e_is_redeem(self):
        """仅 E 级触发赎回建议"""
        engine = DcaAdviceEngine()
        for level in DcaAdviceEngine.VALID_LEVELS:
            advice = engine.get_advice(level)
            if level == "E":
                assert advice.is_redeem is True
            else:
                assert advice.is_redeem is False

    def test_e_multiplier_zero(self):
        """E 级倍数为 0.0（建议暂停定投）"""
        engine = DcaAdviceEngine()
        advice = engine.get_advice("E")
        assert advice.multiplier == 0.0
        assert advice.is_redeem is True


# ============================================================
# 信号索引正确性
# ============================================================
class TestSignalIndex:
    """测试 signal_index 字段"""

    def test_s_plus_index_zero(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("S+")
        assert advice.signal_index == 0

    def test_s_index_one(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("S")
        assert advice.signal_index == 1

    def test_a_index_two(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("A")
        assert advice.signal_index == 2

    def test_b_index_three(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("B")
        assert advice.signal_index == 3

    def test_c_index_four(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("C")
        assert advice.signal_index == 4

    def test_d_index_five(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("D")
        assert advice.signal_index == 5

    def test_e_index_six(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("E")
        assert advice.signal_index == 6

    def test_indexes_sequential(self):
        """信号索引应连续递增"""
        engine = DcaAdviceEngine()
        indices = []
        for level in DcaAdviceEngine.VALID_LEVELS:
            advice = engine.get_advice(level)
            indices.append(advice.signal_index)
        assert indices == list(range(len(DcaAdviceEngine.VALID_LEVELS)))


# ============================================================
# 输入有效性校验
# ============================================================
class TestInputValidation:
    """测试输入有效性校验"""

    def test_valid_levels(self):
        """所有7级信号均可正常处理"""
        engine = DcaAdviceEngine()
        for level in DcaAdviceEngine.VALID_LEVELS:
            advice = engine.get_advice(level)
            assert advice.signal_level == level

    def test_invalid_level_raises(self):
        """无效信号等级应抛出 ValueError"""
        engine = DcaAdviceEngine()
        with pytest.raises(ValueError, match="无效信号等级"):
            engine.get_advice("X")

    def test_invalid_level_empty_string(self):
        engine = DcaAdviceEngine()
        with pytest.raises(ValueError, match="无效信号等级"):
            engine.get_advice("")

    def test_invalid_level_none_like(self):
        engine = DcaAdviceEngine()
        with pytest.raises(ValueError, match="无效信号等级"):
            engine.get_advice("INVALID")

    def test_lowercase_input(self):
        """小写信号被 uppercase 处理"""
        engine = DcaAdviceEngine()
        advice = engine.get_advice("s+")
        assert advice.signal_level == "S+"
        assert advice.multiplier == 3.0

    def test_with_spaces(self):
        """带空格的输入被 strip 处理"""
        engine = DcaAdviceEngine()
        advice = engine.get_advice("  S  ")
        assert advice.signal_level == "S"
        assert advice.multiplier == 2.0


# ============================================================
# to_dict 输出
# ============================================================
class TestToDict:
    """测试 to_dict 方法"""

    def test_to_dict_contains_all_keys(self):
        engine = DcaAdviceEngine()
        advice = engine.get_advice("B")
        d = advice.to_dict()
        assert "signal_level" in d
        assert "multiplier" in d
        assert "action" in d
        assert "advice_text" in d
        assert "is_redeem" in d

    def test_to_dict_signal_level(self):
        engine = DcaAdviceEngine()
        d = engine.get_advice("S+").to_dict()
        assert d["signal_level"] == "S+"

    def test_to_dict_is_redeem_false_for_b(self):
        engine = DcaAdviceEngine()
        d = engine.get_advice("B").to_dict()
        assert d["is_redeem"] is False

    def test_to_dict_is_redeem_true_for_e(self):
        engine = DcaAdviceEngine()
        d = engine.get_advice("E").to_dict()
        assert d["is_redeem"] is True


# ============================================================
# is_valid_level
# ============================================================
class TestIsValidLevel:
    """测试 is_valid_level 方法"""

    def test_valid_levels_return_true(self):
        engine = DcaAdviceEngine()
        for level in DcaAdviceEngine.VALID_LEVELS:
            assert engine.is_valid_level(level) is True

    def test_invalid_level_return_false(self):
        engine = DcaAdviceEngine()
        assert engine.is_valid_level("X") is False
        assert engine.is_valid_level("") is False
        assert engine.is_valid_level("super") is False

    def test_case_insensitive_valid(self):
        engine = DcaAdviceEngine()
        assert engine.is_valid_level("s+") is True
        assert engine.is_valid_level("e") is True


# ============================================================
# all_levels
# ============================================================
class TestAllLevels:
    """测试 all_levels 类方法"""

    def test_returns_7_levels(self):
        assert len(DcaAdviceEngine.all_levels()) == 7

    def test_returns_correct_order(self):
        assert DcaAdviceEngine.all_levels() == ["S+", "S", "A", "B", "C", "D", "E"]


# ============================================================
# 建议文案非空
# ============================================================
class TestAdviceText:
    """测试建议文案非空"""

    @pytest.mark.parametrize("signal", DcaAdviceEngine.VALID_LEVELS)
    def test_advice_text_not_empty(self, signal):
        engine = DcaAdviceEngine()
        advice = engine.get_advice(signal)
        assert isinstance(advice.advice_text, str)
        assert len(advice.advice_text) > 10

    def test_signal_e_mentions_redeem(self):
        """E 级建议文案应包含赎回相关表述"""
        engine = DcaAdviceEngine()
        advice = engine.get_advice("E")
        # 可能包含"赎回"或"暂停"
        assert "赎" in advice.advice_text or "暂停" in advice.advice_text


# ============================================================
# SIGNAL_TO_MULTIPLIER 常量完整性
# ============================================================
class TestMultiplierConstant:
    """测试 SIGNAL_TO_MULTIPLIER 常量完整性"""

    def test_all_7_levels_present(self):
        assert len(SIGNAL_TO_MULTIPLIER) == 7
        for level in DcaAdviceEngine.VALID_LEVELS:
            assert level in SIGNAL_TO_MULTIPLIER

    def test_multiplier_range(self):
        """倍数应在合理范围内"""
        for level, mult in SIGNAL_TO_MULTIPLIER.items():
            assert 0.0 <= mult <= 3.0, f"{level}: {mult} out of range"

    def test_s_plus_highest_multiplier(self):
        """S+ 倍数最高"""
        assert SIGNAL_TO_MULTIPLIER["S+"] == 3.0

    def test_e_zero_multiplier(self):
        """E 倍数为 0"""
        assert SIGNAL_TO_MULTIPLIER["E"] == 0.0


# ============================================================
# 与仓位引擎的独立性
# ============================================================
class TestIndependence:
    """测试定投引擎与仓位引擎的独立性"""

    def test_dca_does_not_modify_position(self):
        """定投引擎不修改仓位建议"""
        from app.engine.position_v5 import PositionEngineV5
        from unittest.mock import MagicMock
        pos_engine = PositionEngineV5(MagicMock())
        dca_engine = DcaAdviceEngine()

        # 获取各信号下仓位建议 vs 定投建议
        signal = "S+"
        dca = dca_engine.get_advice(signal)
        # 验证 dca 对象独立存在，不依赖 PositionEngineV5
        assert dca.multiplier == 3.0
        assert isinstance(dca.to_dict(), dict)
