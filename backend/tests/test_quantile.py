"""
V5.0 分位数计算测试 — test_quantile.py
覆盖 QuantileNorm.calc_percentile / normalize_batch / fallback
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.engine.quantile import QuantileNorm
from app.engine.factor_engine.base import FactorRawValue, FactorQuantileResult


# ============================================================
# 测试 fixture 和辅助函数
# ============================================================

def make_raw(factor_name: str, raw_value: float, index_code: str = "SH000300") -> FactorRawValue:
    """快捷创建 FactorRawValue"""
    return FactorRawValue(
        factor_name=factor_name,
        index_code=index_code,
        trade_date="20260614",
        raw_value=raw_value,
        direction="fear",
    )


# ============================================================
# calc_percentile 单元测试
# ============================================================

class TestCalcPercentile:
    """测试 QuantileNorm.calc_percentile()"""

    def setup_method(self):
        """每个测试前创建 QuantileNorm 实例"""
        # 模拟一个 AsyncSession
        self.mock_session = MagicMock()
        # 完整构造 QuantileNorm
        self.norm = QuantileNorm(self.mock_session)

    @pytest.mark.asyncio
    async def test_normal_percentile_calculation(self):
        """正常场景：当前值在历史高分位"""
        from app.core.config import settings
        # 构造 300 个数据点（> min_samples 252）
        series = [float(i) for i in range(1, 301)]  # 1.0 ~ 300.0
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(300.0, "SH000300", "VOL")
        # 300.0 是最大值，分位接近 1.0
        assert pct is not None
        assert 0.98 < pct <= 1.0

    @pytest.mark.asyncio
    async def test_low_percentile(self):
        """当前值在历史低分位"""
        from app.core.config import settings
        # 1.0 是最小值，pct 应接近 0
        series = [float(i) for i in range(1, 301)]
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(1.0, "SH000300", "VOL")
        assert pct is not None
        assert 0.0 <= pct < 0.02

    @pytest.mark.asyncio
    async def test_midpoint_percentile(self):
        """当前值在历史中位数附近"""
        from app.core.config import settings
        series = [float(i) for i in range(1, 301)]
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(150.0, "SH000300", "VOL")
        assert pct is not None
        assert 0.48 < pct < 0.52

    @pytest.mark.asyncio
    async def test_series_below_min_samples_returns_none(self):
        """样本数 < min_samples 时返回 None"""
        from app.core.config import settings
        # 只返回 min_samples - 1 个样本
        series = [float(i) for i in range(settings.V5_QUANTILE_MIN_SAMPLES - 1)]
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(50.0, "SH000300", "VOL")
        # 样本不足 → 调用方应使用 fallback
        assert pct is None

    @pytest.mark.asyncio
    async def test_empty_series_returns_none(self):
        """空序列返回 None"""
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=[])):
            pct = await self.norm.calc_percentile(50.0, "SH000300", "VOL")
        assert pct is None

    @pytest.mark.asyncio
    async def test_none_series_returns_none(self):
        """None 序列返回 None"""
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=None)):
            pct = await self.norm.calc_percentile(50.0, "SH000300", "VOL")
        assert pct is None

    @pytest.mark.asyncio
    async def test_exactly_min_samples(self):
        """样本数 == min_samples 边界"""
        from app.core.config import settings
        # 大于 min_samples 才能计算（边界检查是 < 252）
        series = [float(i) for i in range(settings.V5_QUANTILE_MIN_SAMPLES + 1)]
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(50.0, "SH000300", "VOL")
        # 边界值 + 1 应可计算
        assert pct is not None

    @pytest.mark.asyncio
    async def test_percentile_clamped_to_zero_one(self):
        """分位数返回值应 ≤ 1.0"""
        from app.core.config import settings
        # 300 个点
        series = [float(i) for i in range(1, 301)]
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(300.0, "SH000300", "VOL")
        # 不应超过 1.0
        assert pct is not None
        assert pct <= 1.0
        assert pct >= 0.0

    @pytest.mark.asyncio
    async def test_all_same_values_returns_valid(self):
        """所有历史值相同时 → 分位数有效"""
        from app.core.config import settings
        series = [50.0] * 300
        with patch.object(self.norm._store, 'get_series', new=AsyncMock(return_value=series)):
            pct = await self.norm.calc_percentile(50.0, "SH000300", "VOL")
        # scipy percentileofscore 对全相同值返回 100 (因为 50.0 == 50.0)
        # 我们只验证返回有效值
        assert pct is not None
        assert 0.0 <= pct <= 1.0


# ============================================================
# normalize_batch 单元测试
# ============================================================

class TestNormalizeBatch:
    """测试 QuantileNorm.normalize_batch()"""

    def setup_method(self):
        self.mock_session = MagicMock()
        self.norm = QuantileNorm(self.mock_session)

    @pytest.mark.asyncio
    async def test_normal_batch_processing(self):
        """14 因子批量处理：所有因子都有足够历史数据"""
        # 14 个原始值
        raws = [make_raw(f"F{i:02d}", float(i * 10)) for i in range(1, 15)]

        async def mock_calc(raw_value, index_code, factor_name):
            # 模拟每个因子都返回合理的分位数
            return 0.5

        with patch.object(self.norm, 'calc_percentile', new=mock_calc), \
             patch.object(self.norm, '_get_sample_count', new=AsyncMock(return_value=1000)):
            results = await self.norm.normalize_batch(raws)

        assert len(results) == 14
        for r in results:
            assert r.percentile == 0.5
            assert r.window_size == self.norm._window_days
            assert r.available_samples == 1000

    @pytest.mark.asyncio
    async def test_fallback_when_insufficient_data(self):
        """样本不足时使用 fallback (0.50)"""
        raws = [make_raw("VOL", 18.0)]

        async def mock_calc_none(raw_value, index_code, factor_name):
            return None  # 样本不足

        with patch.object(self.norm, 'calc_percentile', new=mock_calc_none), \
             patch.object(self.norm, '_get_sample_count', new=AsyncMock(return_value=10)):
            results = await self.norm.normalize_batch(raws)

        assert len(results) == 1
        assert results[0].percentile == 0.50  # fallback default
        assert results[0].available_samples == 10

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        """空批量处理返回空列表"""
        results = await self.norm.normalize_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_mixed_data_availability(self):
        """部分因子有数据，部分无数据 → 混合结果"""
        raws = [
            make_raw("VOL", 18.0),  # 有数据
            make_raw("ADR", 0.5),   # 无数据 → fallback
            make_raw("ERP", 0.05),  # 有数据
        ]

        call_count = [0]

        async def mock_calc(raw_value, index_code, factor_name):
            call_count[0] += 1
            if factor_name == "ADR":
                return None
            return 0.5

        with patch.object(self.norm, 'calc_percentile', new=mock_calc), \
             patch.object(self.norm, '_get_sample_count', new=AsyncMock(return_value=100)):
            results = await self.norm.normalize_batch(raws)

        assert len(results) == 3
        # 第一个有数据
        assert results[0].percentile == 0.5
        # 第二个 fallback
        assert results[1].percentile == 0.50
        # 第三个有数据
        assert results[2].percentile == 0.5

    @pytest.mark.asyncio
    async def test_batch_preserves_factor_name(self):
        """批量处理保留 factor_name"""
        raws = [
            make_raw("VOL", 1.0),
            make_raw("ADR", 2.0),
            make_raw("ERP", 3.0),
        ]

        async def mock_calc(raw_value, index_code, factor_name):
            return 0.5

        with patch.object(self.norm, 'calc_percentile', new=mock_calc), \
             patch.object(self.norm, '_get_sample_count', new=AsyncMock(return_value=100)):
            results = await self.norm.normalize_batch(raws)

        assert [r.factor_name for r in results] == ["VOL", "ADR", "ERP"]
        assert [r.raw_value for r in results] == [1.0, 2.0, 3.0]


# ============================================================
# _fallback_percentile 单元测试
# ============================================================

class TestFallbackPercentile:
    """测试 QuantileNorm._fallback_percentile()"""

    def setup_method(self):
        self.mock_session = MagicMock()
        self.norm = QuantileNorm(self.mock_session)

    def test_fear_factor_returns_midpoint(self):
        """fear 方向因子的 fallback 值为 0.50"""
        raw = FactorRawValue(
            factor_name="VOL", index_code="SH000300",
            trade_date="20260614", raw_value=18.0, direction="fear"
        )
        assert self.norm._fallback_percentile(raw) == 0.50

    def test_greed_factor_returns_midpoint(self):
        """greed 方向因子的 fallback 值为 0.50"""
        raw = FactorRawValue(
            factor_name="ADR", index_code="SH000300",
            trade_date="20260614", raw_value=0.5, direction="greed"
        )
        assert self.norm._fallback_percentile(raw) == 0.50

    def test_fallback_value_in_valid_range(self):
        """fallback 值应在 [0, 1] 范围内"""
        raw = FactorRawValue(
            factor_name="TEST", index_code="SH000300",
            trade_date="20260614", raw_value=0.0, direction="fear"
        )
        val = self.norm._fallback_percentile(raw)
        assert 0.0 <= val <= 1.0


# ============================================================
# _get_sample_count 单元测试
# ============================================================

class TestGetSampleCount:
    """测试 QuantileNorm._get_sample_count()"""

    def setup_method(self):
        self.mock_session = MagicMock()
        self.norm = QuantileNorm(self.mock_session)

    @pytest.mark.asyncio
    async def test_normal_count(self):
        """正常获取样本数"""
        with patch.object(self.norm._store, 'get_series_count', new=AsyncMock(return_value=1260)):
            count = await self.norm._get_sample_count("SH000300", "VOL")
        assert count == 1260

    @pytest.mark.asyncio
    async def test_zero_count(self):
        """样本数为 0"""
        with patch.object(self.norm._store, 'get_series_count', new=AsyncMock(return_value=0)):
            count = await self.norm._get_sample_count("SH000300", "VOL")
        assert count == 0

    @pytest.mark.asyncio
    async def test_exception_returns_zero(self):
        """异常时返回 0"""
        with patch.object(self.norm._store, 'get_series_count', new=AsyncMock(side_effect=Exception("DB error"))):
            count = await self.norm._get_sample_count("SH000300", "VOL")
        assert count == 0
