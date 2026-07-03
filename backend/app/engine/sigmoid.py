"""
Sigmoid 映射层 — V5.0 层2
因子特异 Sigmoid 映射：分位数(0-1) → 得分(0-100)
⚠️ 反向因子（direction=fear）需要在映射后做 100 - score
- ERP: 高ERP=股票便宜=恐惧低 → 反转后低分
- VOL: 高波动=恐惧 → 反转后低分
- TURN: 高换手=恐惧 → 反转后低分
- PCR: 高PCR=避险情绪=恐惧 → 反转后低分
- RSI: 高RSI=过热=恐惧 → 反转后低分
- INDUSTRY_DIVERGENCE: 高分歧=恐惧 → 反转后低分
"""
from __future__ import annotations

import math
from typing import Optional

from app.engine.factor_engine.base import (
    FactorQuantileResult,
    FactorSigmoidResult,
    DivergenceInfo,
)
from app.engine.factor_engine import FACTOR_NAMES
from app.core.config import settings


def _get_reverse_factors() -> set[str]:
    """从 settings.V5_FACTOR_CONFIG 动态获取反向因子集合（direction=fear）"""
    config = settings.V5_FACTOR_CONFIG
    return {
        name for name, meta in config.items()
        if meta.get("direction") == "fear"
    }


def _get_sigmoid_params() -> dict[str, tuple[float, float]]:
    """从 settings.V5_FACTOR_CONFIG 动态获取 sigmoid 参数 (c, k)"""
    config = settings.V5_FACTOR_CONFIG
    result = {}
    for name, meta in config.items():
        c = meta.get("sigmoid_c", 0.50)
        k = meta.get("sigmoid_k", 3.0)
        result[name] = (c, k)
    return result


class SigmoidMapper:
    """Sigmoid 映射器"""

    def map_batch(
        self,
        quantile_results: list[FactorQuantileResult],
    ) -> list[FactorSigmoidResult]:
        """
        批量 Sigmoid 映射
        输入：14 个 FactorQuantileResult
        输出：14 个 FactorSigmoidResult
        """
        reverse_factors = _get_reverse_factors()
        results: list[FactorSigmoidResult] = []
        for qr in quantile_results:
            # 获取该因子的 Sigmoid 参数
            c, k = self._get_params(qr.factor_name)

            # 应用 Sigmoid
            score = self.apply_sigmoid(qr.percentile, c, k)

            # ⚠️ 反向因子处理：fear方向因子高原始值 → 反转后低分（恐惧）
            if qr.factor_name in reverse_factors:
                score = 100.0 - score

            # 计算中点处斜率（用于调试）
            slope = self._slope_at_midpoint(c, k)

            results.append(FactorSigmoidResult(
                factor_name=qr.factor_name,
                percentile=qr.percentile,
                sigmoid_score=round(score, 4),
                c_param=c,
                k_param=k,
                slope_at_midpoint=slope,
            ))
        return results

    def apply_sigmoid(self, x: float, c: float = 0.50, k: float = 3.0) -> float:
        """
        Sigmoid 映射：x ∈ [0, 1]（分位数）→ score ∈ [0, 100]
        公式：score = 100 / (1 + e^(-k * (x - c)))
        """
        if x is None:
            x = 0.50
        x = max(0.0, min(1.0, x))  # clamp to [0, 1]
        exp_neg = math.exp(-k * (x - c))
        score = 100.0 / (1.0 + exp_neg)
        return round(score, 4)

    def _get_params(self, factor_name: str) -> tuple[float, float]:
        """从 settings 动态获取因子特异的 Sigmoid 参数 (c, k)"""
        params = _get_sigmoid_params()
        return params.get(factor_name, (0.50, 3.0))

    def _slope_at_midpoint(self, c: float, k: float) -> float:
        """计算中点处斜率：dy/dx = k * y * (1 - y/100)，其中 y = 50"""
        y = 50.0
        return round(k * y * (1.0 - y / 100.0), 4)
