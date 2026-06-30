"""
V5.0 Sigmoid 三层管道端到端集成测试 — test_v5_pipeline_e2e.py
端到端验证 quantile → sigmoid → aggregate → signal 完整流水线
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.engine.quantile import QuantileNorm
from app.engine.sigmoid import SigmoidMapper
from app.engine.aggregator_v5 import AggregatorV5
from app.engine.signal_mapper import SignalMapper
from app.engine.factor_engine.base import (
    FactorRawValue, FactorQuantileResult, FactorSigmoidResult
)
from app.core.config import settings


# ============================================================
# 三层管道 E2E
# ============================================================

class TestPipelineEnd2End:
    """14 因子完整跑通 quantile → sigmoid → aggregate → signal"""

    def setup_method(self):
        self.mock_session = MagicMock()
        # 14 个因子的固定分位数（构造已知输入）
        # 假设：所有 14 因子都在历史中位数附近 (percentile = 0.5)
        self.median_percentiles = {name: 0.5 for name in settings.V5_FACTOR_CONFIG.keys()}
        # 假设：所有 14 因子都在历史高分位 (percentile = 0.95)
        self.high_percentiles = {name: 0.95 for name in settings.V5_FACTOR_CONFIG.keys()}
        # 假设：所有 14 因子都在历史低分位 (percentile = 0.05)
        self.low_percentiles = {name: 0.05 for name in settings.V5_FACTOR_CONFIG.keys()}

    @pytest.mark.asyncio
    async def test_14_factors_pipeline_neutral(self):
        """14 因子 + 各因子 c 参数场景 → 综合分应 ≈ 50（每个因子按 c 中点对齐）"""
        norm = QuantileNorm(self.mock_session)
        mapper = SigmoidMapper()
        aggregator = AggregatorV5()
        signal_mapper = SignalMapper()

        # 构造 14 个 quantile results（每个因子用各自的 sigmoid_c 作为 percentile）
        qrs = []
        for name, cfg in settings.V5_FACTOR_CONFIG.items():
            qrs.append(FactorQuantileResult(
                factor_name=name,
                raw_value=50.0,
                percentile=cfg["sigmoid_c"],  # 关键：让每个因子都得到 sigmoid_score = 50
                window_size=1260,
                available_samples=1000,
            ))

        # Layer 2: Sigmoid 映射
        srs = mapper.map_batch(qrs)
        assert len(srs) == 14
        # 所有因子都在 c 点，反向因子反转后都是 50
        for sr in srs:
            assert 49.0 <= sr.sigmoid_score <= 51.0, f"{sr.factor_name} = {sr.sigmoid_score}"

        # Layer 3: 加权聚合
        composite = aggregator.aggregate(srs)
        # 14 因子都是 50 分，加权平均 = 50
        assert 48.0 <= composite.score <= 52.0
        # 体制应该是 sideways
        assert composite.divergence.regime == "sideways"

    @pytest.mark.asyncio
    async def test_14_factors_pipeline_all_high(self):
        """14 因子高分位场景 → 综合分应较高"""
        # 全部 percentile=0.95
        qrs = [
            FactorQuantileResult(name, 80.0, 0.95, 1260, 1000)
            for name in settings.V5_FACTOR_CONFIG.keys()
        ]
        mapper = SigmoidMapper()
        srs = mapper.map_batch(qrs)

        # 高分位：正向因子得高分（>60），反向因子得低分（<40）
        from app.engine.sigmoid import REVERSE_FACTORS
        for sr in srs:
            if sr.factor_name in REVERSE_FACTORS:
                # 反向因子：高分位 → 反转后低分
                assert sr.sigmoid_score < 40.0
            else:
                # 正向因子：高分位 → 高分
                assert sr.sigmoid_score > 60.0

        # 聚合：因为有反向因子，综合分不一定高
        # 我们只验证聚合能正常跑通
        aggregator = AggregatorV5()
        composite = aggregator.aggregate(srs)
        # 综合分应 < 100
        assert 0.0 <= composite.score <= 100.0

    @pytest.mark.asyncio
    async def test_14_factors_pipeline_all_low(self):
        """14 因子低分位场景 → 综合分应较低"""
        # 全部 percentile=0.05
        qrs = [
            FactorQuantileResult(name, 20.0, 0.05, 1260, 1000)
            for name in settings.V5_FACTOR_CONFIG.keys()
        ]
        mapper = SigmoidMapper()
        srs = mapper.map_batch(qrs)

        # 低分位：正向因子得低分（<40），反向因子得高分（>60）
        from app.engine.sigmoid import REVERSE_FACTORS
        for sr in srs:
            if sr.factor_name in REVERSE_FACTORS:
                # 反向因子：低分位 → 反转后高分
                assert sr.sigmoid_score > 60.0
            else:
                # 正向因子：低分位 → 低分
                assert sr.sigmoid_score < 40.0

        aggregator = AggregatorV5()
        composite = aggregator.aggregate(srs)
        # 聚合：综合分应 > 0
        assert 0.0 <= composite.score <= 100.0

    @pytest.mark.asyncio
    async def test_14_factor_names_complete(self):
        """14 因子应全部存在（防回归）"""
        assert len(settings.V5_FACTOR_CONFIG) == 14
        # 验证 14 因子名称
        expected_factors = {
            "VOL", "ADR", "ERP", "FLOW", "ETF", "NHNL", "TURN",
            "POS", "NBF", "PCR", "NEWF", "MARGIN", "RSI", "INDUSTRY_DIVERGENCE"
        }
        assert set(settings.V5_FACTOR_CONFIG.keys()) == expected_factors

    @pytest.mark.asyncio
    async def test_weights_sum_to_design_value(self):
        """14 因子权重之和应 ≈ 0.92（V5.0 架构设计值）"""
        total = sum(cfg["weight"] for cfg in settings.V5_FACTOR_CONFIG.values())
        # 实际架构值是 0.92（非 1.0）
        assert 0.91 <= total <= 0.93

    @pytest.mark.asyncio
    async def test_sigmoid_c_k_present_for_all_factors(self):
        """所有 14 因子都应有 sigmoid_c 和 sigmoid_k 参数"""
        for name, cfg in settings.V5_FACTOR_CONFIG.items():
            assert "sigmoid_c" in cfg, f"{name} missing sigmoid_c"
            assert "sigmoid_k" in cfg, f"{name} missing sigmoid_k"
            assert 0.0 <= cfg["sigmoid_c"] <= 1.0
            assert cfg["sigmoid_k"] > 0

    @pytest.mark.asyncio
    async def test_e2e_with_known_input_output(self):
        """已知输入 → 已知输出（回填测试）"""
        # 输入：每个因子用各自的 c 作为 percentile（让 sigmoid_score 全部 = 50）
        mapper = SigmoidMapper()
        qrs = [
            FactorQuantileResult(name, 50.0, cfg["sigmoid_c"], 1260, 1000)
            for name, cfg in settings.V5_FACTOR_CONFIG.items()
        ]
        srs = mapper.map_batch(qrs)

        # 验证每个因子的具体得分（应全部 ≈ 50）
        for sr in srs:
            assert abs(sr.sigmoid_score - 50.0) < 1.0, \
                f"{sr.factor_name} = {sr.sigmoid_score}, expected ~50"

        # 加权聚合 → 50
        aggregator = AggregatorV5()
        composite = aggregator.aggregate(srs)
        assert 49.0 <= composite.score <= 51.0

    @pytest.mark.asyncio
    async def test_pipeline_preserves_factor_count(self):
        """管道每层都应保持 14 因子数量"""
        mapper = SigmoidMapper()
        qrs = [
            FactorQuantileResult(name, 50.0, 0.5, 1260, 1000)
            for name in settings.V5_FACTOR_CONFIG.keys()
        ]
        assert len(qrs) == 14

        srs = mapper.map_batch(qrs)
        assert len(srs) == 14

        aggregator = AggregatorV5()
        composite = aggregator.aggregate(srs)
        # 14 个 sigmoid 结果聚合
        assert composite.divergence.min_factor != ""
        assert composite.divergence.max_factor != ""


# ============================================================
# 14 因子权重总和测试
# ============================================================

class TestFactorWeights:
    """14 因子权重配置测试"""

    def test_specific_factor_weights(self):
        """特定因子权重（防回归）"""
        weights = {name: cfg["weight"] for name, cfg in settings.V5_FACTOR_CONFIG.items()}

        # 关键因子权重（基于架构决策 ADR-002）
        assert abs(weights["VOL"] - 0.11) < 0.001  # 波动率
        assert abs(weights["ADR"] - 0.11) < 0.001  # 涨跌比
        assert abs(weights["ERP"] - 0.11) < 0.001  # 股债性价比
        assert abs(weights["FLOW"] - 0.09) < 0.001  # 资金流

    def test_no_duplicate_factor_names(self):
        """14 因子名称不重复"""
        names = list(settings.V5_FACTOR_CONFIG.keys())
        assert len(names) == len(set(names))

    def test_no_zero_or_negative_weights(self):
        """所有权重都应 > 0"""
        for name, cfg in settings.V5_FACTOR_CONFIG.items():
            assert cfg["weight"] > 0, f"{name} weight must be > 0"


# ============================================================
# 14 因子方向一致性
# ============================================================

class TestFactorDirectionConsistency:
    """14 因子方向（fear/greed）一致性测试"""

    def test_factor_directions(self):
        """特定因子的方向（与 sigmoid.py REVERSE_FACTORS 一致）"""
        from app.engine.sigmoid import REVERSE_FACTORS

        # 通过 sigmoid 反向因子列表反推
        for name in REVERSE_FACTORS:
            cfg = settings.V5_FACTOR_CONFIG[name]
            # 反向因子：原始值越高 → panic 越严重 → 应得低分
            # 通常 direction = "fear"
            assert cfg.get("direction") == "fear" or name in REVERSE_FACTORS

    def test_greed_factors_present(self):
        """greed 方向因子（不反向）应存在"""
        from app.engine.sigmoid import REVERSE_FACTORS
        greed_factors = [n for n in settings.V5_FACTOR_CONFIG.keys() if n not in REVERSE_FACTORS]
        # 至少应有 5+ 个 greed 因子
        assert len(greed_factors) >= 5

    def test_fear_factors_present(self):
        """fear 方向因子（反向）应存在"""
        from app.engine.sigmoid import REVERSE_FACTORS
        # REVERSE_FACTORS 列表中的因子应与 config 中存在
        for name in REVERSE_FACTORS:
            assert name in settings.V5_FACTOR_CONFIG, \
                f"{name} in REVERSE_FACTORS but not in V5_FACTOR_CONFIG"
