"""
聚合层 — V5.0 层3
加权求和 + 分歧度动态加权（factor_std → penalty → 向50回归）
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.engine.factor_engine.base import (
    FactorSigmoidResult,
    DivergenceInfo,
    CompositeScore,
)
from app.core.config import settings


class AggregatorV5:
    """V5.0 聚合器"""

    def __init__(self) -> None:
        self._weights = self._load_weights()
        self._penalty_min = settings.V5_DIVERGENCE_PENALTY_MIN
        self._penalty_max = settings.V5_DIVERGENCE_PENALTY_MAX
        self._std_threshold = settings.V5_DIVERGENCE_STD_THRESHOLD

    def aggregate(
        self,
        sigmoid_results: list[FactorSigmoidResult],
    ) -> CompositeScore:
        """
        聚合 11 因子 Sigmoid 得分
        流程：加权求和 × 惩罚系数 → final_score
        """
        # 1. 计算分歧度
        divergence = self.calc_divergence(sigmoid_results)

        # 2. 计算惩罚系数
        penalty = self.calc_penalty(divergence.factor_std)

        # 3. 加权求和
        weighted_sum = 0.0
        total_weight = 0.0
        for sr in sigmoid_results:
            w = self._weights.get(sr.factor_name, 0.0)
            weighted_sum += sr.sigmoid_score * w
            total_weight += w

        if total_weight <= 0:
            raw_score = 50.0
        else:
            raw_score = weighted_sum / total_weight

        # 4. 应用惩罚（分歧大 → 向50回归）
        final_score = raw_score * penalty + 50.0 * (1.0 - penalty)
        final_score = max(0.0, min(100.0, final_score))

        # 5. 检测市场体制
        regime = self.calc_regime(sigmoid_results)

        return CompositeScore(
            score=round(final_score, 4),
            signal_level="",  # 由 signal_mapper 填充
            confidence_stars=0,  # 由 confidence 填充
            confidence_detail={},
            divergence=divergence,
            factor_results={sr.factor_name: sr for sr in sigmoid_results},
            triggered_defenses=[],
        )

    def calc_divergence(
        self,
        sigmoid_results: list[FactorSigmoidResult],
    ) -> DivergenceInfo:
        """
        计算 11 因子得分的标准差（分歧度）
        """
        scores = [sr.sigmoid_score for sr in sigmoid_results]
        std = float(np.std(scores))
        mean = float(np.mean(scores))

        # 找出最低分和最高分因子
        min_sr = min(sigmoid_results, key=lambda sr: sr.sigmoid_score)
        max_sr = max(sigmoid_results, key=lambda sr: sr.sigmoid_score)

        # 惩罚系数
        penalty = self.calc_penalty(std)

        # 市场体制检测
        regime = self.calc_regime(sigmoid_results)

        return DivergenceInfo(
            factor_std=round(std, 6),
            factor_mean=round(mean, 4),
            min_factor=min_sr.factor_name,
            max_factor=max_sr.factor_name,
            penalty_factor=round(penalty, 4),
            regime=regime,
        )

    def calc_penalty(self, factor_std: float) -> float:
        """
        分歧惩罚系数：factor_std 越大 → penalty 越小 → 最终得分越靠近 50
        penalty ∈ [0.5, 1.0]
        """
        # 线性映射：std 0 → 1.0,  std 0.35 → 0.5
        penalty = self._penalty_max - (factor_std / self._std_threshold) * (
            self._penalty_max - self._penalty_min
        )
        return max(self._penalty_min, min(self._penalty_max, penalty))

    def calc_regime(self, sigmoid_results: list[FactorSigmoidResult]) -> str:
        """
        检测当前市场体制
        返回：bull/bear/sideways/extreme_volatility
        """
        scores = [sr.sigmoid_score for sr in sigmoid_results]
        mean = np.mean(scores)
        std = np.std(scores)

        # 极端波动：std > 0.35
        if std > self._std_threshold:
            return "extreme_volatility"

        # 牛市：均值 > 60
        if mean > 60:
            return "bull"

        # 熊市：均值 < 40
        if mean < 40:
            return "bear"

        # 震荡市
        return "sideways"

    def _load_weights(self) -> dict[str, float]:
        """从配置加载因子权重"""
        cfg = settings.V5_FACTOR_CONFIG
        return {name: info["weight"] for name, info in cfg.items()}
