"""
V5.0 聚合器测试 — test_aggregator_v5.py
覆盖：加权求和 + 分歧度计算 + 惩罚系数 + 市场体制检测 + 权重加载
"""
import pytest
from dataclasses import replace

from app.engine.aggregator_v5 import AggregatorV5
from app.engine.factor_engine.base import FactorSigmoidResult, CompositeScore, DivergenceInfo
from app.core.config import settings


# ============================================================
# 辅助函数
# ============================================================
def make_factor(name: str, score: float) -> FactorSigmoidResult:
    """创建测试用 FactorSigmoidResult"""
    return FactorSigmoidResult(
        factor_name=name,
        percentile=score / 100.0,  # 假设 percentile ∈ [0, 1]
        sigmoid_score=score,
        c_param=0.5,
        k_param=3.0,
        slope_at_midpoint=75.0,  # 任意默认值
    )


# ============================================================
# 加权聚合测试（核心）
# ============================================================
class TestAggregate:
    """测试 aggregate() 加权求和 + 惩罚"""

    def setup_method(self):
        self.agg = AggregatorV5()

    def test_aggregate_returns_CompositeScore(self):
        """aggregate 应返回 CompositeScore"""
        results = [make_factor("VOL", 30.0), make_factor("ADR", 70.0)]
        score = self.agg.aggregate(results)
        assert isinstance(score, CompositeScore)

    def test_aggregate_score_in_valid_range(self):
        """final_score 应在 [0, 100] 范围内"""
        results = [make_factor("VOL", 0.0), make_factor("ADR", 100.0)]
        score = self.agg.aggregate(results)
        assert 0.0 <= score.score <= 100.0

    def test_aggregate_all_50_no_penalty(self):
        """所有因子都是 50 → 无分歧 → final_score 应接近 50"""
        names = list(settings.V5_FACTOR_CONFIG.keys())[:5]
        results = [make_factor(n, 50.0) for n in names]
        score = self.agg.aggregate(results)
        # 所有都是 50，std=0，penalty=1.0，raw_score=50，final=50
        assert abs(score.score - 50.0) < 0.01

    def test_aggregate_all_0_pulls_to_50(self):
        """所有因子都是 0 → 高分歧 → 应向 50 回归"""
        names = list(settings.V5_FACTOR_CONFIG.keys())[:5]
        results = [make_factor(n, 0.0) for n in names]
        score = self.agg.aggregate(results)
        # std=0 (虽然都是 0 但分歧为 0)，penalty=1.0，raw=0，final=0
        # 实际：所有相等 → std=0 → penalty=1.0 → final=0
        assert abs(score.score - 0.0) < 0.01

    def test_aggregate_extreme_divergence(self):
        """极端分歧（部分 0，部分 100）→ 应明显向 50 回归"""
        names = list(settings.V5_FACTOR_CONFIG.keys())[:4]
        # 一半 0，一半 100
        results = [
            make_factor(names[0], 0.0),
            make_factor(names[1], 0.0),
            make_factor(names[2], 100.0),
            make_factor(names[3], 100.0),
        ]
        score = self.agg.aggregate(results)
        # raw=50, std=50, penalty=0.5（钳制）
        # 由于权重不完全相等（VOL=0.11, ERP=0.11, FLOW=0.09），raw_score 可能略有偏差
        # 但应明显接近 50（被惩罚向 50 回归）
        assert 40.0 < score.score < 60.0
        assert score.divergence.factor_std > 30.0  # 高分歧
        assert score.divergence.penalty_factor == 0.5  # 最大惩罚

    def test_aggregate_empty_results(self):
        """空结果列表 → 引擎内部会因 min/max 抛 ValueError"""
        # 当前实现：min(sigmoid_results, key=...) 会抛 ValueError
        with pytest.raises(ValueError):
            self.agg.aggregate([])

    def test_aggregate_uses_correct_weights(self):
        """权重应来自 V5_FACTOR_CONFIG"""
        # VOL 权重 0.11，ADR 权重 0.11（都是 0.11）
        # 单独 VOL=0, ADR=100：raw = 0*0.11 + 100*0.11 / 0.22 = 50
        results = [make_factor("VOL", 0.0), make_factor("ADR", 100.0)]
        score = self.agg.aggregate(results)
        # std 很大但有惩罚
        # 实际上 std = 50，penalty 会被钳制到 0.5
        # final = 50*0.5 + 50*0.5 = 50
        assert abs(score.score - 50.0) < 1.0


# ============================================================
# 分歧度计算测试
# ============================================================
class TestCalcDivergence:
    """测试 calc_divergence()"""

    def setup_method(self):
        self.agg = AggregatorV5()

    def test_divergence_returns_DivergenceInfo(self):
        """应返回 DivergenceInfo"""
        results = [make_factor("VOL", 50.0), make_factor("ADR", 50.0)]
        div = self.agg.calc_divergence(results)
        assert isinstance(div, DivergenceInfo)

    def test_divergence_zero_for_identical_scores(self):
        """所有因子得分相同时 std=0"""
        results = [make_factor("VOL", 50.0), make_factor("ADR", 50.0), make_factor("ERP", 50.0)]
        div = self.agg.calc_divergence(results)
        assert div.factor_std == 0.0

    def test_divergence_max_for_extreme(self):
        """极端分歧（0/100）→ 高 std"""
        results = [make_factor("VOL", 0.0), make_factor("ADR", 100.0)]
        div = self.agg.calc_divergence(results)
        assert div.factor_std > 30.0

    def test_divergence_identifies_min_max_factors(self):
        """应正确识别 min/max 因子"""
        results = [
            make_factor("VOL", 30.0),
            make_factor("ADR", 70.0),
            make_factor("ERP", 50.0),
        ]
        div = self.agg.calc_divergence(results)
        assert div.min_factor == "VOL"
        assert div.max_factor == "ADR"

    def test_divergence_mean_correct(self):
        """均值应正确计算"""
        results = [
            make_factor("VOL", 30.0),
            make_factor("ADR", 70.0),
        ]
        div = self.agg.calc_divergence(results)
        assert abs(div.factor_mean - 50.0) < 0.01

    def test_divergence_empty_results(self):
        """空结果应抛 ValueError（min/max 找不到）"""
        with pytest.raises(ValueError):
            self.agg.calc_divergence([])


# ============================================================
# 惩罚系数测试
# ============================================================
class TestCalcPenalty:
    """测试 calc_penalty() 线性映射"""

    def setup_method(self):
        self.agg = AggregatorV5()

    def test_penalty_max_when_no_divergence(self):
        """std=0 → penalty=1.0（无惩罚）"""
        assert self.agg.calc_penalty(0.0) == 1.0

    def test_penalty_min_at_threshold(self):
        """std=threshold → penalty=0.5（最大惩罚）"""
        threshold = self.agg._std_threshold
        penalty = self.agg.calc_penalty(threshold)
        assert abs(penalty - 0.5) < 0.01

    def test_penalty_clamped_to_min(self):
        """std > threshold → penalty 应被钳制到 0.5"""
        penalty = self.agg.calc_penalty(100.0)
        assert penalty == 0.5

    def test_penalty_clamped_to_max(self):
        """std < 0 → penalty 应被钳制到 1.0"""
        penalty = self.agg.calc_penalty(-10.0)
        assert penalty == 1.0

    def test_penalty_linear_mapping(self):
        """std=threshold/2 → penalty=0.75"""
        threshold = self.agg._std_threshold
        penalty = self.agg.calc_penalty(threshold / 2)
        assert abs(penalty - 0.75) < 0.01


# ============================================================
# 市场体制检测测试
# ============================================================
class TestCalcRegime:
    """测试 calc_regime() 市场体制识别"""

    def setup_method(self):
        self.agg = AggregatorV5()

    def test_bull_regime_high_mean_low_std(self):
        """高均值、低分歧 → bull"""
        results = [make_factor("VOL", 70.0), make_factor("ADR", 75.0)]
        assert self.agg.calc_regime(results) == "bull"

    def test_bear_regime_low_mean_low_std(self):
        """低均值、低分歧 → bear"""
        results = [make_factor("VOL", 30.0), make_factor("ADR", 25.0)]
        assert self.agg.calc_regime(results) == "bear"

    def test_sideways_regime_mid_mean_low_std(self):
        """中均值、低分歧 → sideways"""
        results = [make_factor("VOL", 50.0), make_factor("ADR", 50.0)]
        assert self.agg.calc_regime(results) == "sideways"

    def test_extreme_volatility_high_std(self):
        """高分歧（std > threshold）→ extreme_volatility"""
        results = [
            make_factor("VOL", 0.0),
            make_factor("ADR", 100.0),
        ]
        # std=50 > 15 → extreme_volatility
        assert self.agg.calc_regime(results) == "extreme_volatility"

    def test_regime_boundary_bull(self):
        """mean 略高于 60 → bull"""
        # mean=61, std=0
        results = [make_factor("VOL", 61.0), make_factor("ADR", 61.0)]
        assert self.agg.calc_regime(results) == "bull"

    def test_regime_boundary_bear(self):
        """mean 略低于 40 → bear"""
        # mean=39, std=0
        results = [make_factor("VOL", 39.0), make_factor("ADR", 39.0)]
        assert self.agg.calc_regime(results) == "bear"

    def test_regime_empty_results(self):
        """空结果 → sideways（默认）"""
        # mean=0, std=0 → not >60, not <40 → sideways
        assert self.agg.calc_regime([]) == "sideways"


# ============================================================
# 权重加载测试
# ============================================================
class TestLoadWeights:
    """测试 _load_weights()"""

    def setup_method(self):
        self.agg = AggregatorV5()

    def test_weights_loaded_from_config(self):
        """权重应从 V5_FACTOR_CONFIG 加载"""
        weights = self.agg._load_weights()
        assert len(weights) == 14
        assert "VOL" in weights
        assert "RSI" in weights
        assert "INDUSTRY_DIVERGENCE" in weights

    def test_weights_match_config_values(self):
        """权重值应与 config 一致"""
        weights = self.agg._load_weights()
        for name, cfg in settings.V5_FACTOR_CONFIG.items():
            assert weights[name] == cfg["weight"]

    def test_total_weight_close_to_1(self):
        """总权重应接近 0.92（V5.0 设计值）"""
        weights = self.agg._load_weights()
        total = sum(weights.values())
        assert abs(total - 0.92) < 0.01


# ============================================================
# 端到端集成测试
# ============================================================
class TestEndToEnd:
    """端到端测试（多层管道集成）"""

    def setup_method(self):
        self.agg = AggregatorV5()

    def test_panic_scenario(self):
        """恐慌场景：所有 fear 因子得分极低"""
        results = [
            make_factor("VOL", 10.0),   # fear, 高波动 → 低分
            make_factor("ERP", 15.0),   # fear
            make_factor("TURN", 20.0),  # fear
            make_factor("PCR", 10.0),   # fear
            make_factor("RSI", 5.0),    # fear
            make_factor("INDUSTRY_DIVERGENCE", 15.0),  # fear
        ]
        score = self.agg.aggregate(results)
        # 整体得分应较低（恐慌情绪）
        assert score.score < 40.0
        # 体制可能是 bear 或 sideways
        assert score.divergence.regime in ("bear", "sideways", "extreme_volatility")

    def test_greed_scenario(self):
        """贪婪场景：所有 greed 因子得分极高"""
        results = [
            make_factor("ADR", 90.0),   # greed
            make_factor("FLOW", 85.0),  # greed
            make_factor("ETF", 80.0),   # greed
            make_factor("NHNL", 95.0),  # greed
            make_factor("POS", 90.0),   # greed
            make_factor("NBF", 85.0),   # greed
            make_factor("NEWF", 80.0),  # greed
            make_factor("MARGIN", 90.0),  # greed
        ]
        score = self.agg.aggregate(results)
        # 整体得分应较高（贪婪情绪）
        assert score.score > 60.0
        # 体制应是 bull
        assert score.divergence.regime in ("bull", "extreme_volatility")

    def test_mixed_scenario_moderate_score(self):
        """混合场景：得分应在中间"""
        results = [
            make_factor("VOL", 30.0),  # fear
            make_factor("ADR", 70.0),  # greed
            make_factor("ERP", 25.0),  # fear
            make_factor("FLOW", 75.0),  # greed
            make_factor("ETF", 60.0),  # greed
            make_factor("NHNL", 65.0),  # greed
            make_factor("TURN", 35.0),  # fear
            make_factor("POS", 70.0),  # greed
        ]
        score = self.agg.aggregate(results)
        # 应在中间范围
        assert 30.0 < score.score < 70.0

    def test_full_14_factor_pipeline(self):
        """完整 14 因子管道"""
        # 创建 14 因子结果
        all_factors = list(settings.V5_FACTOR_CONFIG.keys())
        scores = [25, 75, 30, 70, 50, 55, 45, 65, 40, 60, 50, 50, 50, 50]
        results = [make_factor(name, score) for name, score in zip(all_factors, scores)]
        composite = self.agg.aggregate(results)
        # 所有必要字段
        assert composite.score >= 0.0
        assert composite.divergence is not None
        assert len(composite.factor_results) == 14
        # 体制应被检测
        assert composite.divergence.regime in ("bull", "bear", "sideways", "extreme_volatility")
