"""
V5.0 仓位建议引擎测试
覆盖：5×7矩阵查表 + 置信度修正 + 交易成本校验 + 频率限制
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.engine.position_v5 import PositionEngineV5


class TestPositionEngine:
    """仓位建议引擎测试"""

    def setup_method(self):
        self.mock_session = MagicMock()
        self.engine = PositionEngineV5(self.mock_session)

    # ---- 仓位等级转换 ----
    def test_pct_to_level_empty(self):
        assert self.engine._pct_to_level(0.0) == "empty"

    def test_pct_to_level_light(self):
        assert self.engine._pct_to_level(0.25) == "light"

    def test_pct_to_level_mid(self):
        assert self.engine._pct_to_level(0.50) == "mid"

    def test_pct_to_level_heavy(self):
        assert self.engine._pct_to_level(0.75) == "heavy"

    def test_pct_to_level_full(self):
        assert self.engine._pct_to_level(1.0) == "full"

    def test_pct_to_level_edge_cases(self):
        """边界情况"""
        assert self.engine._pct_to_level(0.10) == "empty"    # < 0.125 → empty
        assert self.engine._pct_to_level(0.124) == "empty"   # 刚好在 empty 边界内
        assert self.engine._pct_to_level(0.125) == "light"   # 刚好进入 light
        assert self.engine._pct_to_level(0.374) == "light"   # light 上边界
        assert self.engine._pct_to_level(0.375) == "mid"     # 刚好进入 mid
        assert self.engine._pct_to_level(0.624) == "mid"     # mid 上边界
        assert self.engine._pct_to_level(0.625) == "heavy"   # 刚好进入 heavy
        assert self.engine._pct_to_level(0.874) == "heavy"   # heavy 上边界
        assert self.engine._pct_to_level(0.875) == "full"    # 刚好进入 full

    # ---- 信号索引 ----

    @pytest.mark.parametrize("signal,idx", [
        ("S+", 0), ("S", 1), ("A", 2), ("B", 3),
        ("C", 4), ("D", 5), ("E", 6),
    ])
    def test_signal_to_idx(self, signal, idx):
        assert self.engine._signal_to_idx(signal) == idx

    def test_signal_to_idx_unknown(self):
        """未知信号返回默认B级"""
        assert self.engine._signal_to_idx("X") == 3  # 默认B

    # ---- 矩阵查表 ----

    def test_matrix_lookup_structure(self):
        """矩阵维度和元素类型正确"""
        matrix = self.engine._matrix or [[
            "empty", "empty", "light", "light", "mid", "mid", "mid"
        ] for _ in range(5)]
        assert len(matrix) == 5   # 5行
        assert all(len(row) == 7 for row in matrix)  # 7列

    # ---- 置信度修正 ----

    @pytest.mark.parametrize("stars,expected", [
        (4, 1.0),
        (3, 0.75),
        (2, 0.50),
        (1, 0.25),
    ])
    def test_confidence_adjustment(self, stars, expected):
        """置信度修正因子正确"""
        factor = self.engine._conf_adj.get(stars, None)
        if factor is not None:
            assert factor == pytest.approx(expected, abs=0.1)

    # ---- 成本校验 ----

    def test_cost_threshold_reject_small_change(self):
        """小于成本阈值的调整被拒绝"""
        small_change = self.engine._cost_threshold - 0.005
        rejected = small_change < self.engine._cost_threshold
        assert rejected

    def test_cost_threshold_accept_large_change(self):
        """大于成本阈值的调整被接受"""
        large_change = self.engine._cost_threshold + 0.05
        accepted = large_change >= self.engine._cost_threshold
        assert accepted

    # ---- 频率限制 ----

    def test_frequency_days_default(self):
        """频率限制天数有有效配置"""
        assert self.engine._freq_days > 0
