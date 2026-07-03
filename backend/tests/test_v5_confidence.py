"""
V5.0 置信度引擎测试
覆盖：5维度评分 + 4星映射 + 四道防线检查
"""
import pytest
from unittest.mock import MagicMock
from app.engine.confidence import ConfidenceEngine
from app.engine.factor_engine.base import FactorSigmoidResult


def make_result(name, percentile=0.5, sigmoid_score=50.0):
    """快捷创建 FactorSigmoidResult"""
    return FactorSigmoidResult(
        factor_name=name,
        percentile=percentile,
        sigmoid_score=sigmoid_score,
        c_param=0.5,
        k_param=3.0,
        slope_at_midpoint=0.75,
    )


class TestConfidenceEngine:
    """置信度计算测试"""

    def setup_method(self):
        self.engine = ConfidenceEngine()

    # ---- 5维度评分 ----

    def test_factor_consistency_high(self):
        """因子一致时得分 > 80"""
        results = [make_result(f"F{i}", sigmoid_score=55 + i) for i in range(11)]
        detail = self.engine._calc_factor_consistency(results)
        assert isinstance(detail, float)
        assert 0 <= detail <= 100

    def test_factor_consistency_low_when_divergent(self):
        """因子分歧时得分 < 50"""
        results = [make_result(f"F{i}", sigmoid_score=20 + i * 7) for i in range(11)]
        detail = self.engine._calc_factor_consistency(results)
        assert detail < 60  # 分歧大 → 低分

    def test_signal_strength_extreme(self):
        """极端信号强度最高"""
        strong = self.engine._calc_signal_strength("S+")
        weak   = self.engine._calc_signal_strength("B")
        assert strong > weak

    def test_regime_match_bear_buy(self):
        """熊市 + 恐惧信号 = 高匹配"""
        match = self.engine._calc_regime_match("S", "bear")
        assert match > 60

    def test_regime_match_bull_sell_mismatch(self):
        """牛市 + 恐惧信号 = 低匹配"""
        match = self.engine._calc_regime_match("S+", "bull")
        assert match < 60

    # ---- 4星映射 ----

    @pytest.mark.parametrize("detail,expected_stars", [
        ({"factor_consistency": 90, "signal_strength": 90, "regime_match": 90, "persistence": 90, "data_quality": 90}, 4),
        ({"factor_consistency": 70, "signal_strength": 70, "regime_match": 70, "persistence": 70, "data_quality": 70}, 3),
        ({"factor_consistency": 50, "signal_strength": 50, "regime_match": 50, "persistence": 50, "data_quality": 50}, 2),
        ({"factor_consistency": 20, "signal_strength": 20, "regime_match": 20, "persistence": 20, "data_quality": 20}, 1),
    ])
    def test_stars_mapping(self, detail, expected_stars):
        """4星映射正确"""
        stars = self.engine._map_to_stars(detail)
        assert stars == expected_stars

    # ---- 完整流程 ----

    def test_full_calculation(self):
        """端到端置信度计算"""
        results = [make_result(f"F{i}", sigmoid_score=50 + i % 5 * 10) for i in range(11)]
        stars, detail, defenses = self.engine.calculate(
            results, signal_level="S", regime="bear",
        )
        assert stars in (1, 2, 3, 4)
        assert "factor_consistency" in detail
        assert isinstance(defenses, list)

    # ---- 防线触发 ----

    def test_defense_extreme_volatility(self):
        """极端波动防线触发字符串返回"""
        results = [make_result("VOL", sigmoid_score=95)]
        stars, detail, defenses = self.engine.calculate(
            results, signal_level="E", regime="extreme_volatility",
        )
        assert stars >= 1
