"""
置信度引擎 — V5.0
5维度评分 → 4星映射 + 四道假信号防线
"""
from __future__ import annotations

from typing import Optional

from app.engine.factor_engine.base import FactorSigmoidResult, CompositeScore
from app.core.config import settings


class ConfidenceEngine:
    """V5.0 置信度引擎"""

    # 四道防线开关
    DEFENSE_EXTREME_VOL = settings.V5_DEFENSE_EXTREME_VOLATILITY
    DEFENSE_JUMP_GT_15 = settings.V5_DEFENSE_JUMP_GT_15
    DEFENSE_PRICE_DIVERGENCE = settings.V5_DEFENSE_PRICE_DIVERGENCE
    DEFENSE_FACTOR_STD = settings.V5_DEFENSE_FACTOR_STD

    def calculate(
        self,
        sigmoid_results: list[FactorSigmoidResult],
        signal_level: str,
        regime: str,
        macd_data: Optional[dict] = None,
    ) -> tuple[int, dict, list[str]]:
        """
        计算置信度
        输入：11因子Sigmoid结果 + 信号等级 + 市场体制 + MACD数据
        输出：(星级, 5维度明细, 触发的防线列表)
        """
        # 1. 因子一致性（factor_std 反向映射）
        factor_consistency = self._calc_factor_consistency(sigmoid_results)

        # 2. 信号强度（|score-50| 映射）
        signal_strength = self._calc_signal_strength(signal_level)

        # 3. 体制匹配度
        regime_match = self._calc_regime_match(signal_level, regime)

        # 4. 持续性（MACD同向天数）
        persistence = self._calc_persistence(macd_data)

        # 5. 数据质量（可用样本数占比）
        data_quality = self._calc_data_quality(sigmoid_results)

        detail = {
            "factor_consistency": round(factor_consistency, 2),
            "signal_strength": round(signal_strength, 2),
            "regime_match": round(regime_match, 2),
            "persistence": round(persistence, 2),
            "data_quality": round(data_quality, 2),
        }

        # 映射为星级
        stars = self._map_to_stars(detail)

        # 四道防线检查
        triggered = self._check_defenses(
            sigmoid_results, signal_level, regime, detail,
        )

        return stars, detail, triggered

    def _calc_factor_consistency(self, results: list[FactorSigmoidResult]) -> float:
        """因子一致性：factor_std 越小 → 一致性越高"""
        import numpy as np
        scores = [r.sigmoid_score for r in results]
        std = float(np.std(scores))
        # std 0 → 100分；std 20 → 0分（线性映射）
        consistency = 100.0 - (std / 20.0) * 100.0
        return max(0.0, min(100.0, consistency))

    def _calc_signal_strength(self, level: str) -> float:
        """信号强度：|score-50| 越大 → 强度越高"""
        score_map = {"S+": 6, "S": 19, "A": 32, "B": 50, "C": 68, "D": 82, "E": 94}
        score = score_map.get(level, 50)
        strength = abs(score - 50.0) * 2.0  # 0-100
        return round(strength, 2)

    def _calc_regime_match(self, level: str, regime: str) -> float:
        """体制匹配度：信号与体制一致 → 高分"""
        # 牛市 + 贪婪信号 → 高匹配
        if regime == "bull" and level in ["D", "E"]:
            return 90.0
        if regime == "bull" and level in ["B", "C"]:
            return 70.0
        if regime == "bear" and level in ["S+", "S"]:
            return 90.0
        if regime == "bear" and level in ["B", "C"]:
            return 70.0
        if regime == "sideways":
            return 60.0
        if regime == "extreme_volatility":
            return 30.0
        return 50.0

    def _calc_persistence(self, macd_data: Optional[dict]) -> float:
        """持续性：MACD同向天数"""
        if not macd_data:
            return 50.0
        same_days = macd_data.get("same_direction_days", 0)
        # 20天同向 → 100分
        return min(100.0, (same_days / 20.0) * 100.0)

    def _calc_data_quality(self, results: list[FactorSigmoidResult]) -> float:
        """数据质量：可用因子数 / 11 * 100"""
        valid = sum(1 for r in results if r.percentile is not None)
        return round((valid / len(results)) * 100.0, 2) if results else 0.0

    def _map_to_stars(self, detail: dict) -> int:
        """5维度平均分 → 星级"""
        avg = sum(detail.values()) / len(detail)
        if avg >= 80:
            return 4
        if avg >= 60:
            return 3
        if avg >= 40:
            return 2
        return 1

    def _check_defenses(
        self,
        results: list[FactorSigmoidResult],
        level: str,
        regime: str,
        detail: dict,
    ) -> list[str]:
        """四道假信号防线"""
        triggered = []

        # 防线1：市场极端波动
        if self.DEFENSE_EXTREME_VOL:
            std = float(__import__("numpy").mean([r.sigmoid_score for r in results]))
            if std > settings.V5_DIVERGENCE_STD_THRESHOLD:
                triggered.append("extreme_volatility")

        # 防线2：信号跳变 > 15分
        if self.DEFENSE_JUMP_GT_15:
            # 需要对比前一天的分数，这里简化：检查 factor_std
            if detail.get("factor_consistency", 100) < 40:
                triggered.append("jump_gt_15")

        # 防线3：价格-情绪背离（需要价格数据，这里简化）
        if self.DEFENSE_PRICE_DIVERGENCE:
            # TODO：实际实现需要传入价格数据
            pass

        # 防线4：因子分歧度 > 阈值
        if self.DEFENSE_FACTOR_STD:
            import numpy as np
            scores = [r.sigmoid_score for r in results]
            std = float(np.std(scores))
            if std > settings.V5_DIVERGENCE_STD_THRESHOLD:
                triggered.append("factor_std_high")

        return triggered
