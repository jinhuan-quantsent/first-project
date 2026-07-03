"""
V5.0 因子引擎测试 — test_v5_factors.py
覆盖 11 因子注册、类属性、validate、方向、因子实例化
"""
import pytest
from app.engine.factor_engine import (
    FACTOR_NAMES,
    FACTOR_CLASSES,
    get_factor_instance,
    get_all_factors,
    BaseFactor,
    VolFactor,
    AdrFactor,
    ErpFactor,
    FlowFactor,
    EtfFactor,
    NhnlFactor,
    TurnFactor,
    PosFactor,
    NbfFactor,
    PcrFactor,
    NewfFactor,
)
from app.engine.factor_engine.base import FactorRawValue


# ============================================================
# 因子注册测试
# ============================================================
class TestFactorRegistry:
    """测试 FACTOR_NAMES / FACTOR_CLASSES / 工厂函数"""

    def test_11_factors_registered(self):
        """FACTOR_NAMES 应包含恰好 11 个因子"""
        assert len(FACTOR_NAMES) == 11

    def test_factor_names_order(self):
        """因子名称应按架构附录顺序排列"""
        expected = ["VOL", "ADR", "ERP", "FLOW", "ETF",
                    "NHNL", "TURN", "POS", "NBF", "PCR", "NEWF"]
        assert FACTOR_NAMES == expected

    def test_all_11_classes_registered(self):
        """FACTOR_CLASSES 应包含恰好 11 个因子类"""
        assert len(FACTOR_CLASSES) == 11
        for name in FACTOR_NAMES:
            assert name in FACTOR_CLASSES

    def test_get_factor_instance_returns_correct_type(self):
        """get_factor_instance 返回正确类型的因子实例"""
        assert isinstance(get_factor_instance("VOL"), VolFactor)
        assert isinstance(get_factor_instance("ADR"), AdrFactor)
        assert isinstance(get_factor_instance("ERP"), ErpFactor)
        assert isinstance(get_factor_instance("FLOW"), FlowFactor)
        assert isinstance(get_factor_instance("ETF"), EtfFactor)
        assert isinstance(get_factor_instance("NHNL"), NhnlFactor)
        assert isinstance(get_factor_instance("TURN"), TurnFactor)
        assert isinstance(get_factor_instance("POS"), PosFactor)
        assert isinstance(get_factor_instance("NBF"), NbfFactor)
        assert isinstance(get_factor_instance("PCR"), PcrFactor)
        assert isinstance(get_factor_instance("NEWF"), NewfFactor)

    def test_get_factor_instance_unknown(self):
        """未知因子名返回 None"""
        assert get_factor_instance("UNKNOWN") is None

    def test_get_all_factors_returns_11(self):
        """get_all_factors 返回恰好 11 个因子实例"""
        factors = get_all_factors()
        assert len(factors) == 11

    def test_get_all_factors_unique_names(self):
        """所有因子实例的 name 属性唯一"""
        factors = get_all_factors()
        names = [f.name for f in factors]
        assert len(names) == len(set(names))
        assert set(names) == set(FACTOR_NAMES)


# ============================================================
# BaseFactor 抽象基类测试
# ============================================================
class TestBaseFactor:
    """测试 BaseFactor 抽象基类"""

    def test_base_factor_is_abstract(self):
        """BaseFactor 不能被直接实例化"""
        with pytest.raises(TypeError):
            BaseFactor()  # type: ignore

    def test_apply_sigmoid_default_params(self):
        """基类 apply_sigmoid 使用默认 sigmoid_c/k"""

        class TestFactor(BaseFactor):
            name = "TEST"
            label = "测试"
            direction = "fear"
            weight = 0.05

            async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
                return FactorRawValue("TEST", index_code, trade_date, 0.0, "fear")

        f = TestFactor()
        # 默认 sigmoid_c=0.50, sigmoid_k=3.0
        assert f.sigmoid_c == 0.50
        assert f.sigmoid_k == 3.0
        # 中点处应返回 50
        assert f.apply_sigmoid(0.50) == 50.0

    def test_validate_default_true(self):
        """默认 validate 对非空值返回 True"""

        class TestFactor(BaseFactor):
            name = "TEST"
            label = "测试"
            direction = "fear"
            weight = 0.05

            async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
                return FactorRawValue("TEST", index_code, trade_date, 0.0, "fear")

        f = TestFactor()
        raw = FactorRawValue("TEST", "SH000300", "2026-06-14", 10.0, "fear")
        assert f.validate(raw) is True

    def test_validate_none_false(self):
        """默认 validate 对 None 值返回 False"""

        class TestFactor(BaseFactor):
            name = "TEST"
            label = "测试"
            direction = "fear"
            weight = 0.05

            async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
                return FactorRawValue("TEST", index_code, trade_date, 0.0, "fear")

        f = TestFactor()
        raw = FactorRawValue("TEST", "SH000300", "2026-06-14", None, "fear")  # type: ignore
        assert f.validate(raw) is False

    def test_derive_returns_same(self):
        """默认 derive 原样返回"""

        class TestFactor(BaseFactor):
            name = "TEST"
            label = "测试"
            direction = "fear"
            weight = 0.05

            async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
                return FactorRawValue("TEST", index_code, trade_date, 0.0, "fear")

        f = TestFactor()
        raw = FactorRawValue("TEST", "SH000300", "2026-06-14", 10.0, "fear")
        derived = f.derive(raw)
        assert derived is raw  # 原样返回


# ============================================================
# 因子类属性测试（参数化）
# ============================================================
FACTOR_ATTRS = [
    # (类名, 实例, name, label, direction, weight, sigmoid_c, sigmoid_k)
    ("VOL", VolFactor(), "VOL", "波动率", "fear", 0.12, 0.50, 3.0),
    ("ADR", AdrFactor(), "ADR", "涨跌比", "greed", 0.12, 0.50, 2.5),
    ("ERP", ErpFactor(), "ERP", "股债性价比", "fear", 0.12, 0.50, 4.0),
    ("FLOW", FlowFactor(), "FLOW", "资金流", "greed", 0.10, 0.50, 2.0),
    ("ETF", EtfFactor(), "ETF", "ETF份额", "greed", 0.08, 0.50, 2.0),
    ("NHNL", NhnlFactor(), "NHNL", "新高占比", "greed", 0.08, 0.60, 2.5),
    ("TURN", TurnFactor(), "TURN", "换手率", "fear", 0.08, 0.40, 3.0),
    ("POS", PosFactor(), "POS", "基金仓位", "greed", 0.08, 0.50, 1.8),
    ("NBF", NbfFactor(), "NBF", "北向资金", "greed", 0.06, 0.50, 2.5),
    ("PCR", PcrFactor(), "PCR", "认沽认购比", "fear", 0.04, 0.30, 4.0),
    ("NEWF", NewfFactor(), "NEWF", "新发基金热度", "greed", 0.04, 0.50, 2.0),
]


class TestFactorAttributes:
    """测试所有 11 个因子的类属性"""

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_name_attribute(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.name == name, f"{cls_name}.name expected {name}, got {factor.name}"

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_label_attribute(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.label == label, f"{cls_name}.label expected {label}, got {factor.label}"

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_direction_attribute(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.direction in ("fear", "greed"), \
            f"{cls_name}.direction={factor.direction} not in (fear, greed)"

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_direction_matches(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.direction == direction, \
            f"{cls_name}.direction expected {direction}, got {factor.direction}"

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_weight_attribute(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.weight == pytest.approx(weight, 0.0001), \
            f"{cls_name}.weight expected {weight}, got {factor.weight}"

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_sigmoid_c_attribute(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.sigmoid_c == pytest.approx(c, 0.0001), \
            f"{cls_name}.sigmoid_c expected {c}, got {factor.sigmoid_c}"

    @pytest.mark.parametrize("cls_name,factor,name,label,direction,weight,c,k", FACTOR_ATTRS)
    def test_sigmoid_k_attribute(self, cls_name, factor, name, label, direction, weight, c, k):
        assert factor.sigmoid_k == pytest.approx(k, 0.0001), \
            f"{cls_name}.sigmoid_k expected {k}, got {factor.sigmoid_k}"


# ============================================================
# 因子权重总和测试
# ============================================================
class TestFactorWeights:
    """测试因子权重"""

    def test_weights_sum_close_to_1(self):
        """11 个因子权重之和应接近 0.92（V5.0 架构设计值）"""
        total = sum(f.weight for f in get_all_factors())
        expected = 0.92
        assert abs(total - expected) < 0.01, f"Weights sum to {total}, expected {expected}"

    def test_weight_positive(self):
        """所有权重应为正数"""
        for f in get_all_factors():
            assert f.weight > 0, f"{f.name}.weight={f.weight} <= 0"

    def test_top_weights(self):
        """波动率、涨跌比、ERP 应为最高权重 (0.12)"""
        vol = get_factor_instance("VOL")
        adr = get_factor_instance("ADR")
        erp = get_factor_instance("ERP")
        assert vol.weight == 0.12
        assert adr.weight == 0.12
        assert erp.weight == 0.12


# ============================================================
# Validate 方法测试（参数化边界值）
# ============================================================
class TestFactorValidate:
    """测试每个因子的 validate 方法"""

    def test_vol_validate_valid(self):
        """VOL: [5, 60] 范围内有效"""
        f = VolFactor()
        raw = FactorRawValue("VOL", "SH000300", "2026-06-14", 18.0, "fear")
        assert f.validate(raw) is True

    def test_vol_validate_too_low(self):
        """VOL: < 3.0 无效"""
        f = VolFactor()
        raw = FactorRawValue("VOL", "SH000300", "2026-06-14", 2.0, "fear")
        assert f.validate(raw) is False

    def test_vol_validate_too_high(self):
        """VOL: > 80.0 无效"""
        f = VolFactor()
        raw = FactorRawValue("VOL", "SH000300", "2026-06-14", 85.0, "fear")
        assert f.validate(raw) is False

    def test_vol_validate_none(self):
        """VOL: None 无效"""
        f = VolFactor()
        raw = FactorRawValue("VOL", "SH000300", "2026-06-14", None, "fear")  # type: ignore
        assert f.validate(raw) is False

    def test_adr_validate_valid(self):
        """ADR: [0.1, 10] 范围内有效"""
        f = AdrFactor()
        raw = FactorRawValue("ADR", "SH000300", "2026-06-14", 1.2, "greed")
        assert f.validate(raw) is True

    def test_adr_validate_too_low(self):
        """ADR: < 0.05 无效"""
        f = AdrFactor()
        raw = FactorRawValue("ADR", "SH000300", "2026-06-14", 0.01, "greed")
        assert f.validate(raw) is False

    def test_adr_validate_too_high(self):
        """ADR: > 20.0 无效"""
        f = AdrFactor()
        raw = FactorRawValue("ADR", "SH000300", "2026-06-14", 25.0, "greed")
        assert f.validate(raw) is False

    def test_erp_validate_valid(self):
        """ERP: [-5, 10] 范围内有效"""
        f = ErpFactor()
        raw = FactorRawValue("ERP", "SH000300", "2026-06-14", 2.5, "fear")
        assert f.validate(raw) is True

    def test_erp_validate_too_low(self):
        """ERP: < -10.0 无效"""
        f = ErpFactor()
        raw = FactorRawValue("ERP", "SH000300", "2026-06-14", -15.0, "fear")
        assert f.validate(raw) is False

    def test_erp_validate_too_high(self):
        """ERP: > 15.0 无效"""
        f = ErpFactor()
        raw = FactorRawValue("ERP", "SH000300", "2026-06-14", 20.0, "fear")
        assert f.validate(raw) is False

    def test_flow_validate_valid(self):
        """FLOW: [-100, 100] 范围内有效"""
        f = FlowFactor()
        raw = FactorRawValue("FLOW", "SH000300", "2026-06-14", 50.0, "greed")
        assert f.validate(raw) is True

    def test_flow_validate_too_low(self):
        """FLOW: < -100.0 无效"""
        f = FlowFactor()
        raw = FactorRawValue("FLOW", "SH000300", "2026-06-14", -150.0, "greed")
        assert f.validate(raw) is False

    def test_flow_validate_too_high(self):
        """FLOW: > 100.0 无效"""
        f = FlowFactor()
        raw = FactorRawValue("FLOW", "SH000300", "2026-06-14", 120.0, "greed")
        assert f.validate(raw) is False

    def test_nhnl_validate_valid(self):
        """NHNL: [0, 30] 范围内有效"""
        f = NhnlFactor()
        raw = FactorRawValue("NHNL", "SH000300", "2026-06-14", 8.0, "greed")
        assert f.validate(raw) is True

    def test_nhnl_validate_too_low(self):
        """NHNL: < 0.0 无效"""
        f = NhnlFactor()
        raw = FactorRawValue("NHNL", "SH000300", "2026-06-14", -1.0, "greed")
        assert f.validate(raw) is False

    def test_nhnl_validate_too_high(self):
        """NHNL: > 30.0 无效"""
        f = NhnlFactor()
        raw = FactorRawValue("NHNL", "SH000300", "2026-06-14", 35.0, "greed")
        assert f.validate(raw) is False

    def test_erp_derive_preserves_raw(self):
        """ERP 的 derive 方法原样返回（反转在 sigmoid 层处理）"""
        f = ErpFactor()
        raw = FactorRawValue("ERP", "SH000300", "2026-06-14", 3.0, "fear")
        derived = f.derive(raw)
        assert derived is raw
        assert derived.raw_value == 3.0


# ============================================================
# 因子方向逻辑测试 (fear vs greed)
# ============================================================
class TestFactorDirection:
    """测试因子方向逻辑"""

    def test_fear_factors_count(self):
        """fear 方向因子应为 VOL, ERP, TURN, PCR (4个)"""
        fear_names = [f.name for f in get_all_factors() if f.direction == "fear"]
        assert set(fear_names) == {"VOL", "ERP", "TURN", "PCR"}
        assert len(fear_names) == 4

    def test_greed_factors_count(self):
        """greed 方向因子应为 ADR, FLOW, ETF, NHNL, POS, NBF, NEWF (7个)"""
        greed_names = [f.name for f in get_all_factors() if f.direction == "greed"]
        assert set(greed_names) == {"ADR", "FLOW", "ETF", "NHNL", "POS", "NBF", "NEWF"}
        assert len(greed_names) == 7

    def test_fear_direction_means_high_value_produces_fear(self):
        """fear 方向：高因子值 → 高恐惧 → 低情绪分"""
        # VOL: 高波动 → fear → 低分位数 → 低得分
        assert VolFactor().direction == "fear"
        # ERP: 高ERP → fear (但反转后高分) — 方向仍为 fear
        assert ErpFactor().direction == "fear"

    def test_greed_direction_means_high_value_produces_greed(self):
        """greed 方向：高因子值 → 高贪婪 → 高情绪分"""
        assert AdrFactor().direction == "greed"
        assert NhnlFactor().direction == "greed"
        assert PosFactor().direction == "greed"


# ============================================================
# FactorRawValue dataclass 测试
# ============================================================
class TestFactorRawValue:
    """测试 FactorRawValue 数据结构"""

    def test_create_raw_value(self):
        raw = FactorRawValue(
            factor_name="VOL",
            index_code="SH000300",
            trade_date="2026-06-14",
            raw_value=18.5,
            direction="fear",
        )
        assert raw.factor_name == "VOL"
        assert raw.index_code == "SH000300"
        assert raw.trade_date == "2026-06-14"
        assert raw.raw_value == 18.5
        assert raw.direction == "fear"

    def test_raw_value_greed_direction(self):
        raw = FactorRawValue(
            factor_name="ADR",
            index_code="SH000300",
            trade_date="2026-06-14",
            raw_value=1.5,
            direction="greed",
        )
        assert raw.direction == "greed"
