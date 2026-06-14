"""
Sigmoid 映射层 — V5.0 层2
因子特异 Sigmoid 映射：分位数(0-1) → 得分(0-100)
⚠️ 反向因子（ERP）需要在映射后做 100 - score
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


# 反向因子：映射后需要 100 - score
REVERSE_FACTORS = {"ERP"}


class SigmoidMapper:
    """Sigmoid 映射器"""

    def map_batch(
        self,
        quantile_results: list[FactorQuantileResult],
    ) -> list[FactorSigmoidResult]:
        """
        批量 Sigmoid 映射
        输入：11 个 FactorQuantileResult
        输出：11 个 FactorSigmoidResult
        """
        results: list[FactorSigmoidResult] = []
        for qr in quantile_results:
            # 获取该因子的 Sigmoid 参数
            c, k = self._get_params(qr.factor_name)

            # 应用 Sigmoid
            score = self.apply_sigmoid(qr.percentile, c, k)

            # ⚠️ 反向因子处理：ERP 高原始值 → 低恐惧分
            if qr.factor_name in REVERSE_FACTORS:
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
        """获取因子特异的 Sigmoid 参数 (c, k)"""
        # 从 settings 读取（架构 §7.5 附录）
        param_map = {
            "VOL":  (0.50, 3.0),
            "ADR":  (0.50, 2.5),
            "ERP":  (0.50, 4.0),
            "FLOW": (0.50, 2.0),
            "ETF":  (0.50, 2.0),
            "NHNL": (0.60, 2.5),
            "TURN": (0.40, 3.0),
            "POS":  (0.50, 1.8),
            "NBF":  (0.50, 2.5),
            "PCR":  (0.30, 4.0),
            "NEWF": (0.50, 2.0),
        }
        return param_map.get(factor_name, (0.50, 3.0))

    def _slope_at_midpoint(self, c: float, k: float) -> float:
        """计算中点处斜率：dy/dx = k * y * (1 - y/100)，其中 y = 50"""
        y = 50.0
        return round(k * y * (1.0 - y / 100.0), 4)
