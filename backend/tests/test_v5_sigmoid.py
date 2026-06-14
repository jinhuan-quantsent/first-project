"""
V5.0 Sigmoid 映射层测试 — test_v5_sigmoid.py
覆盖 SigmoidMapper.apply_sigmoid / map_batch / 参数映射 / 反向因子
"""
import pytest
import math
from app.engine.sigmoid import SigmoidMapper, REVERSE_FACTORS
from app.engine.factor_engine.base import FactorQuantileResult


# ============================================================
# apply_sigmoid 单元测试
# ============================================================
class TestApplySigmoid:
    """测试 SigmoidMapper.apply_sigmoid 方法"""

    def test_midpoint_returns_50(self):
        """x=c=0.50 时 sigmoid 应返回 50"""
        mapper = SigmoidMapper()
        assert mapper.apply_sigmoid(0.50, c=0.50, k=3.0) == 50.0

    def test_high_percentile_high_score(self):
        """x > c 时应返回 > 50 的得分"""
        mapper = SigmoidMapper()
        score = mapper.apply_sigmoid(0.80, c=0.50, k=3.0)
        assert score > 50.0

    def test_low_percentile_low_score(self):
        """x < c 时应返回 < 50 的得分"""
        mapper = SigmoidMapper()
        score = mapper.apply_sigmoid(0.20, c=0.50, k=3.0)
        assert score < 50.0

    def test_zero_percentile(self):
        """x=0 时应返回接近 0 的得分"""
        mapper = SigmoidMapper()
        score = mapper.apply_sigmoid(0.0, c=0.50, k=3.0)
        assert score < 20.0
        assert score >= 0.0

    def test_one_percentile(self):
        """x=1 时应返回接近 100 的得分"""
        mapper = SigmoidMapper()
        score = mapper.apply_sigmoid(1.0, c=0.50, k=3.0)
        assert score > 80.0
        assert score <= 100.0

    def test_none_default_midpoint(self):
        """x=None 时默认使用 0.50 返回 50"""
        mapper = SigmoidMapper()
        score = mapper.apply_sigmoid(None, c=0.50, k=3.0)
        assert score == 50.0

    def test_out_of_range_clamped(self):
        """x < 0 被 clamp 到 0，x > 1 被 clamp 到 1"""
        mapper = SigmoidMapper()
        score_low = mapper.apply_sigmoid(-0.5, c=0.50, k=3.0)
        score_high = mapper.apply_sigmoid(1.5, c=0.50, k=3.0)
        assert score_low < 20.0  # clamped to 0
        assert score_high > 80.0  # clamped to 1

    def test_different_c_param(self):
        """不同的 c 参数影响中点位置"""
        mapper = SigmoidMapper()
        # c=0.30: 样本值在 30%分位时得 50 分 → 左移
        score_at_50_left = mapper.apply_sigmoid(0.50, c=0.30, k=4.0)
        # c=0.70: 样本值在 70%分位时得 50 分 → 右移
        score_at_50_right = mapper.apply_sigmoid(0.50, c=0.70, k=4.0)
        assert score_at_50_left > 50.0  # 50%分位 > 30%中点 → 得分 > 50
        assert score_at_50_right < 50.0  # 50%分位 < 70%中点 → 得分 < 50

    def test_different_k_param(self):
        """不同的 k 参数影响曲线陡峭程度"""
        mapper = SigmoidMapper()
        # k=1.0 (平缓): x=0.80 时得分温和
        score_flat = mapper.apply_sigmoid(0.80, c=0.50, k=1.0)
        # k=10.0 (陡峭): x=0.80 时得分极端
        score_steep = mapper.apply_sigmoid(0.80, c=0.50, k=10.0)
        assert score_steep > score_flat  # 陡峭曲线对偏离中点更敏感

    def test_score_in_0_100_range(self):
        """Sigmoid 得分始终在 [0, 100] 范围内"""
        mapper = SigmoidMapper()
        for c in [0.30, 0.50, 0.60]:
            for k in [1.0, 2.5, 4.0, 8.0]:
                for x in [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]:
                    score = mapper.apply_sigmoid(x, c=c, k=k)
                    assert 0.0 <= score <= 100.0, \
                        f"x={x}, c={c}, k={k} → score={score} out of range"

    def test_formula_correctness(self):
        """手动验证 Sigmoid 公式：score = 100 / (1 + e^(-k*(x-c)))"""
        mapper = SigmoidMapper()
        x, c, k = 0.60, 0.50, 3.0
        score = mapper.apply_sigmoid(x, c, k)
        expected = round(100.0 / (1.0 + math.exp(-k * (x - c))), 4)
        assert score == expected

    def test_round_to_4_decimals(self):
        """sigmoid 得分应四舍五入到 4 位小数"""
        mapper = SigmoidMapper()
        score = mapper.apply_sigmoid(0.65, c=0.50, k=3.0)
        import decimal
        d = decimal.Decimal(str(score))
        exponent = d.as_tuple().exponent
        assert exponent >= -4  # 不超过 4 位小数


# ============================================================
# 反向因子测试 (ERP)
# ============================================================
class TestReverseFactor:
    """测试 ERP 反向因子处理"""

    def test_erp_is_reverse_factor(self):
        """ERP 应在 REVERSE_FACTORS 集合中"""
        assert "ERP" in REVERSE_FACTORS

    def test_erp_high_percentile_gives_low_score(self):
        """ERP 高分位数 → 高原始 sigmoid 得分 → 反转后低分"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult(
            factor_name="ERP",
            raw_value=5.0,
            percentile=0.90,
            window_size=250,
            available_samples=200,
        )
        results = mapper.map_batch([qr])
        assert len(results) == 1
        # 原始 sigmoid(0.90, 0.50, 4.0) 应很高，反转后应很低
        assert results[0].sigmoid_score < 50.0

    def test_erp_low_percentile_gives_high_score(self):
        """ERP 低分位数 → 低原始 sigmoid 得分 → 反转后高分"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult(
            factor_name="ERP",
            raw_value=-2.0,
            percentile=0.10,
            window_size=250,
            available_samples=200,
        )
        results = mapper.map_batch([qr])
        assert len(results) == 1
        assert results[0].sigmoid_score > 50.0

    def test_erp_midpoint_inverted(self):
        """ERP 中点处反转后仍为 50"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult(
            factor_name="ERP",
            raw_value=2.0,
            percentile=0.50,
            window_size=250,
            available_samples=200,
        )
        results = mapper.map_batch([qr])
        assert results[0].sigmoid_score == 50.0

    def test_non_erp_factor_not_reversed(self):
        """非 ERP 因子不做反转"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult(
            factor_name="VOL",
            raw_value=18.0,
            percentile=0.90,
            window_size=250,
            available_samples=200,
        )
        results = mapper.map_batch([qr])
        # VOL 不是反向因子，应该保持高得分
        assert results[0].sigmoid_score > 50.0


# ============================================================
# map_batch 批量映射测试
# ============================================================
class TestMapBatch:
    """测试 SigmoidMapper.map_batch 批量映射"""

    def test_batch_returns_correct_count(self):
        """map_batch 应返回与输入相同数量的结果"""
        mapper = SigmoidMapper()
        qrs = [
            FactorQuantileResult("VOL", 18.0, 0.50, 250, 200),
            FactorQuantileResult("ADR", 1.2, 0.50, 250, 200),
        ]
        results = mapper.map_batch(qrs)
        assert len(results) == len(qrs)

    def test_batch_empty_list(self):
        """空列表应返回空列表"""
        mapper = SigmoidMapper()
        results = mapper.map_batch([])
        assert results == []

    def test_batch_all_fields_present(self):
        """每个结果应包含所有必要字段"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("VOL", 18.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        r = results[0]
        assert r.factor_name == "VOL"
        assert r.percentile == 0.50
        assert isinstance(r.sigmoid_score, float)
        assert isinstance(r.c_param, float)
        assert isinstance(r.k_param, float)
        assert isinstance(r.slope_at_midpoint, float)

    def test_batch_preserves_percentile(self):
        """批量映射应保留原始分位数"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("TURN", 1.5, 0.35, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].percentile == 0.35

    @pytest.mark.parametrize("factor_name", [
        "VOL", "ADR", "FLOW", "ETF", "POS", "NBF", "NEWF",
    ])
    def test_all_c050_factors_midpoint_50(self, factor_name):
        """c=0.50 的非反向因子在 50%分位时应得 50 ± 0.1 分"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult(factor_name, 0.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert abs(results[0].sigmoid_score - 50.0) < 0.1


# ============================================================
# 参数映射测试
# ============================================================
class TestParamMapping:
    """测试因子特异的 Sigmoid 参数映射"""

    def test_vol_params(self):
        """VOL: c=0.50, k=3.0"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("VOL", 18.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.50
        assert results[0].k_param == 3.0

    def test_erp_params(self):
        """ERP: c=0.50, k=4.0（高敏感）"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("ERP", 2.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.50
        assert results[0].k_param == 4.0

    def test_nhnl_params(self):
        """NHNL: c=0.60（右移中点）, k=2.5"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("NHNL", 8.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.60
        assert results[0].k_param == 2.5

    def test_turn_params(self):
        """TURN: c=0.40（左移中点）, k=3.0"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("TURN", 1.5, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.40
        assert results[0].k_param == 3.0

    def test_pcr_params(self):
        """PCR: c=0.30（极左移）, k=4.0"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("PCR", 0.8, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.30
        assert results[0].k_param == 4.0

    def test_pos_params(self):
        """POS: c=0.50, k=1.8（最平缓）"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("POS", 45.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.50
        assert results[0].k_param == 1.8

    def test_unknown_factor_default_params(self):
        """未知因子使用默认参数 c=0.50, k=3.0"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("UNKNOWN", 0.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == 0.50
        assert results[0].k_param == 3.0

    @pytest.mark.parametrize("name,expected_c,expected_k", [
        ("VOL", 0.50, 3.0),
        ("ADR", 0.50, 2.5),
        ("ERP", 0.50, 4.0),
        ("FLOW", 0.50, 2.0),
        ("ETF", 0.50, 2.0),
        ("NHNL", 0.60, 2.5),
        ("TURN", 0.40, 3.0),
        ("POS", 0.50, 1.8),
        ("NBF", 0.50, 2.5),
        ("PCR", 0.30, 4.0),
        ("NEWF", 0.50, 2.0),
    ])
    def test_all_11_factor_params(self, name, expected_c, expected_k):
        """验证全部 11 个因子的参数映射"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult(name, 0.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].c_param == expected_c, f"{name} c_param mismatch"
        assert results[0].k_param == expected_k, f"{name} k_param mismatch"


# ============================================================
# 斜率计算测试
# ============================================================
class TestSlopeAtMidpoint:
    """测试 _slope_at_midpoint 方法"""

    def test_slope_basic(self):
        """斜率公式：k * 50 * (1 - 50/100) = k * 25"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("VOL", 18.0, 0.50, 250, 200)
        results = mapper.map_batch([qr])
        # k=3.0 → slope = 3.0 * 25 = 75.0
        assert results[0].slope_at_midpoint == 75.0

    def test_slope_varied_by_k(self):
        """不同 k 参数产生不同斜率"""
        mapper = SigmoidMapper()
        # ERP: k=4.0 → slope = 4.0 * 25 = 100.0
        qr_erp = FactorQuantileResult("ERP", 2.0, 0.50, 250, 200)
        results_erp = mapper.map_batch([qr_erp])
        assert results_erp[0].slope_at_midpoint == 100.0

        # POS: k=1.8 → slope = 1.8 * 25 = 45.0
        qr_pos = FactorQuantileResult("POS", 45.0, 0.50, 250, 200)
        results_pos = mapper.map_batch([qr_pos])
        assert results_pos[0].slope_at_midpoint == 45.0


# ============================================================
# 边界与异常情况
# ============================================================
class TestEdgeCases:
    """测试 Sigmoid 映射的边界和异常情况"""

    def test_extreme_feat_percentile_0(self):
        """0%分位：最低得分"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("VOL", 5.0, 0.0, 250, 200)
        results = mapper.map_batch([qr])
        assert results[0].sigmoid_score < 25.0

    def test_extreme_greed_percentile_1(self):
        """100%分位：最高得分"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("ADR", 5.0, 1.0, 250, 200)
        results = mapper.map_batch([qr])
        # ADR 不是反向因子
        assert results[0].sigmoid_score > 75.0

    def test_monotonic_increasing(self):
        """Sigmoid 映射是非递减的（输入分位数越大，得分越高）"""
        mapper = SigmoidMapper()
        scores = []
        for pct in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            qr = FactorQuantileResult("VOL", 0.0, pct, 250, 200)
            results = mapper.map_batch([qr])
            scores.append(results[0].sigmoid_score)
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], \
                f"单调性违反：{scores[i]} > {scores[i+1]} at percentile index {i}"

    def test_single_float_percentile(self):
        """float 类型分位数正常工作"""
        mapper = SigmoidMapper()
        qr = FactorQuantileResult("VOL", 18.0, 0.73, 250, 200)  # type: ignore
        results = mapper.map_batch([qr])
        assert 0.0 <= results[0].sigmoid_score <= 100.0
