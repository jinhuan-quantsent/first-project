"""
P2-6: 因子配置单一源收尾测试

验证：
1. V5_FACTOR_CONFIG 是 weight / sigmoid_c / sigmoid_k 的唯一来源
2. BaseFactor.__init__ 自动从 config 同步
3. V5_FACTOR_META 仅保留 label/source 辅助信息（无 weight）
4. 所有 14 因子 direction 与 V5_FACTOR_META 一致
"""
import pytest

from app.core.config import settings
from app.engine.factor_history import V5_FACTOR_META
from app.engine.factor_engine import get_all_factors


class TestSingleSourceOfTruth:
    """P2-6: 单一真相源验证"""

    def test_config_has_all_14_factors(self):
        """V5_FACTOR_CONFIG 包含 14 因子"""
        assert len(settings.V5_FACTOR_CONFIG) == 14

    def test_factor_class_weights_match_config(self):
        """Factor 类的 weight 属性自动从 config 同步"""
        factors = get_all_factors()
        for f in factors:
            cfg = settings.V5_FACTOR_CONFIG.get(f.name)
            assert cfg is not None, f"Factor {f.name} not in V5_FACTOR_CONFIG"
            assert f.weight == cfg["weight"], (
                f"Factor {f.name} weight={f.weight} != config weight={cfg['weight']}"
            )
            assert f.sigmoid_c == cfg["sigmoid_c"], (
                f"Factor {f.name} sigmoid_c={f.sigmoid_c} != config={cfg['sigmoid_c']}"
            )
            assert f.sigmoid_k == cfg["sigmoid_k"], (
                f"Factor {f.name} sigmoid_k={f.sigmoid_k} != config={cfg['sigmoid_k']}"
            )

    def test_total_weight_within_tolerance(self):
        """所有因子权重和应接近 0.92（V5.0 设计）"""
        factors = get_all_factors()
        total = sum(f.weight for f in factors)
        # 0.92 是 V5.0 设计值
        assert 0.91 <= total <= 0.93, f"Total weight {total} not in [0.91, 0.93]"


class TestMetaAsAuxiliary:
    """P2-6: V5_FACTOR_META 仅作辅助信息（label / source）"""

    def test_meta_count_matches_config(self):
        """V5_FACTOR_META 数量 = V5_FACTOR_CONFIG 数量"""
        assert len(V5_FACTOR_META) == len(settings.V5_FACTOR_CONFIG) == 14

    def test_meta_has_no_weight(self):
        """V5_FACTOR_META 不应包含 weight（避免双重真相源）"""
        for meta in V5_FACTOR_META:
            assert "weight" not in meta, (
                f"Factor {meta['name']} has weight in V5_FACTOR_META "
                f"(should only be in V5_FACTOR_CONFIG)"
            )
            assert "sigmoid_c" not in meta, (
                f"Factor {meta['name']} has sigmoid_c in V5_FACTOR_META"
            )
            assert "sigmoid_k" not in meta, (
                f"Factor {meta['name']} has sigmoid_k in V5_FACTOR_META"
            )

    def test_meta_direction_matches_config(self):
        """V5_FACTOR_META.direction 与 V5_FACTOR_CONFIG.direction 一致"""
        for meta in V5_FACTOR_META:
            cfg = settings.V5_FACTOR_CONFIG[meta["name"]]
            assert meta["direction"] == cfg["direction"], (
                f"Factor {meta['name']}: meta direction={meta['direction']} "
                f"!= config direction={cfg['direction']}"
            )

    def test_meta_names_match_config(self):
        """V5_FACTOR_META 的 name 集合 = V5_FACTOR_CONFIG 键集合"""
        meta_names = {m["name"] for m in V5_FACTOR_META}
        config_names = set(settings.V5_FACTOR_CONFIG.keys())
        assert meta_names == config_names


class TestMetaAuxiliaryFunctions:
    """P2-6: 辅助函数正常工作"""

    def test_get_factor_meta_returns_dict(self):
        from app.engine.factor_history import get_factor_meta
        meta = get_factor_meta("VOL")
        assert meta is not None
        assert meta["name"] == "VOL"
        assert meta["direction"] == "fear"
        assert "weight" not in meta

    def test_get_factor_meta_returns_none_for_unknown(self):
        from app.engine.factor_history import get_factor_meta
        meta = get_factor_meta("UNKNOWN_FACTOR")
        assert meta is None

    def test_get_all_factor_names_returns_14(self):
        from app.engine.factor_history import get_all_factor_names
        names = get_all_factor_names()
        assert len(names) == 14
        assert "VOL" in names
        assert "INDUSTRY_DIVERGENCE" in names
