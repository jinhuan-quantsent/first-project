"""
信号映射器 — V5.0
7级信号映射 + 防跳变规则
"""
from __future__ import annotations

from app.engine.sigmoid import SigmoidMapper
from app.core.config import settings


class SignalMapper:
    """7级信号映射器"""

    # 信号等级顺序（用于防跳变计算）
    LEVELS: list[str] = ["S+", "S", "A", "B", "C", "D", "E"]

    # 信号边界（6个边界划分7级）
    BOUNDARIES: list[int] = None  # 运行时从 settings 加载

    def __init__(self) -> None:
        self.BOUNDARIES = settings.V5_SIGNAL_BOUNDARIES
        self._anti_jump_small_diff = settings.V5_ANTI_JUMP_SMALL_DIFF
        self._anti_jump_large_diff = settings.V5_ANTI_JUMP_LARGE_DIFF
        self._consecutive_days = settings.V5_ANTI_JUMP_CONSECUTIVE_DAYS

    def map(
        self,
        score: float,
        prev_level: str | None = None,
        score_diff: float | None = None,
        consecutive_same: int = 0,
    ) -> tuple[str, bool]:
        """
        映射综合分为7级信号
        输入：score (0-100), prev_level, score_diff, consecutive_same
        输出：(signal_level, jump_blocked)
        """
        # 1. 初步映射
        level = self._score_to_level(score)

        # 2. 防跳变检查
        if prev_level is not None and prev_level in self.LEVELS:
            level, blocked = self._anti_jump_check(
                level, prev_level, score_diff, consecutive_same,
            )
        else:
            blocked = False

        return level, blocked

    def _score_to_level(self, score: float) -> str:
        """根据边界划分7级"""
        for i, boundary in enumerate(self.BOUNDARIES):
            if score <= boundary:
                return self.LEVELS[i]
        return self.LEVELS[-1]  # > 80 → E

    def _anti_jump_check(
        self,
        new_level: str,
        prev_level: str,
        score_diff: float | None,
        consecutive_same: int,
    ) -> tuple[str, bool]:
        """
        防跳变规则：
        1. 单日分差 < 10 → 最多变1级
        2. 单日分差 ≥ 10 → 最多变2级
        3. 连续N天同向 → 额外1级
        """
        new_idx = self.LEVELS.index(new_level)
        prev_idx = self.LEVELS.index(prev_level)

        raw_diff = abs(new_idx - prev_idx)

        # 规则1&2：基于分数差限制
        if score_diff is not None:
            if abs(score_diff) < self._anti_jump_small_diff:
                max_diff = 1
            else:
                max_diff = 2
        else:
            max_diff = 2  # 默认最多2级

        # 规则3：连续同向额外1级
        if consecutive_same >= self._consecutive_days:
            max_diff += 1

        # 应用限制
        if raw_diff > max_diff:
            direction = 1 if new_idx > prev_idx else -1
            limited_idx = prev_idx + direction * max_diff
            limited_idx = max(0, min(len(self.LEVELS) - 1, limited_idx))
            return self.LEVELS[limited_idx], True

        return new_level, False

    def get_conclusion(self, level: str) -> str:
        """根据信号等级生成一句话结论"""
        conclusions = {
            "S+": "市场极度恐慌，投资者情绪崩溃，可能是长期布局良机",
            "S":  "市场恐慌情绪明显，恐慌性抛售增多，可关注超跌机会",
            "A":  "市场偏恐慌，谨慎情绪主导，可小仓位试探",
            "B":  "市场情绪中性，多空力量均衡，建议持仓观望",
            "C":  "市场偏贪婪，乐观情绪升温，可考虑逐步减仓",
            "D":  "市场贪婪情绪明显，追涨氛围浓厚，建议控制仓位",
            "E":  "市场极度贪婪，投资者狂热，高风险区域建议减仓",
        }
        return conclusions.get(level, "市场情绪待观察")
