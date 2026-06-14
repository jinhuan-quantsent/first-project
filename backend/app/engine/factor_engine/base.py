"""
因子引擎基类 + 核心数据结构 — V5.0
定义 BaseFactor 抽象基类与 6 个 dataclass
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


# ============================================================
# 数据结构（dataclass）
# ============================================================

@dataclass
class FactorRawValue:
    """因子原始值（从数据源获取后的初始值）"""
    factor_name: str           # 如 "VOL", "ERP"
    index_code: str            # 如 "SH000300"
    trade_date: str            # "2026-06-14"
    raw_value: float           # 原始计算值
    direction: Literal["fear", "greed"]  # 因子方向


@dataclass
class FactorQuantileResult:
    """层1输出：分位数标准化结果"""
    factor_name: str
    raw_value: float           # 原始值
    percentile: float          # 历史分位数 (0.0-1.0)
    window_size: int           # 滚动窗口天数
    available_samples: int     # 实际可用样本数


@dataclass
class FactorSigmoidResult:
    """层2输出：Sigmoid映射结果"""
    factor_name: str
    percentile: float          # 输入：分位数
    sigmoid_score: float       # 输出：Sigmoid映射后的得分 (0-100)
    c_param: float            # Sigmoid中点参数
    k_param: float            # Sigmoid斜率参数
    slope_at_midpoint: float  # 中点处斜率


@dataclass
class DivergenceInfo:
    """分歧度信息"""
    factor_std: float          # 11因子Sigmoid得分标准差
    factor_mean: float        # 均值
    min_factor: str           # 最低分因子名
    max_factor: str           # 最高分因子名
    penalty_factor: float     # 分歧惩罚系数 (0.5-1.0)
    regime: str               # 当前市场体制


@dataclass
class CompositeScore:
    """V5.0 最终情绪分"""
    score: float               # 0-100 综合情绪分
    signal_level: str         # S+/S/A/B/C/D/E
    confidence_stars: int     # 1-4 星
    confidence_detail: dict    # 5维度评分明细
    divergence: DivergenceInfo # 分歧度信息
    factor_results: dict[str, FactorSigmoidResult]  # 11因子明细
    triggered_defenses: list[str]  # 触发的假信号防线


# ============================================================
# 抽象基类
# ============================================================

class BaseFactor(ABC):
    """
    因子抽象基类
    每个因子实现三个方法：fetch_raw → validate → derive
    """

    # 子类必须覆盖的类属性
    name: str = ""           # 因子代号，如 "VOL"
    label: str = ""          # 中文名，如 "波动率"
    direction: Literal["fear", "greed"] = "fear"
    weight: float = 0.0
    sigmoid_c: float = 0.50
    sigmoid_k: float = 3.0

    # --- 方法1：获取原始值 ---
    @abstractmethod
    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        从 data_source 获取原始值，封装为 FactorRawValue
        失败时抛出 FactorCalcError，由引擎捕获并跳过
        """
        ...

    # --- 方法2：校验原始值 ---
    def validate(self, raw: FactorRawValue) -> bool:
        """
        校验原始值是否在合理范围内
        返回 False 时引擎将该因子得分设为 50（中性）
        """
        if raw.raw_value is None:
            return False
        return True

    # --- 方法3：衍生计算（可选）---
    def derive(self, raw: FactorRawValue) -> FactorRawValue:
        """
        对原始值做衍生计算（如ERP需要 equity_yield - bond_yield）
        默认原样返回
        """
        return raw

    # --- 工具：获取默认原始值 ---
    def _get_default_raw_value(self, index_code: str = "") -> float:
        """
        当 fetch_raw() 失败时的降级默认值
        子类应 override 返回该因子的合理默认值
        """
        return 50.0

    # --- 工具：Sigmoid 映射 ---
    def apply_sigmoid(self, x: float, c: float | None = None, k: float | None = None) -> float:
        """
        Sigmoid 映射：x ∈ [0, 1]（分位数）→ score ∈ [0, 100]
        公式：score = 100 / (1 + e^(-k * (x - c)))
        """
        import math
        c = c if c is not None else self.sigmoid_c
        k = k if k is not None else self.sigmoid_k
        score = 100.0 / (1.0 + math.exp(-k * (x - c)))
        return round(score, 4)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, direction={self.direction})>"
