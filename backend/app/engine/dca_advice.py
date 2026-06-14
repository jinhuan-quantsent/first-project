"""
定投调整建议引擎 — V5.0 P0
7级信号 → 定投倍数映射，配合仓位矩阵使用
"""
from __future__ import annotations

from dataclasses import dataclass, field


# 信号 → 定投倍数映射
SIGNAL_TO_MULTIPLIER: dict[str, float] = {
    "S+": 3.0,
    "S":  2.0,
    "A":  1.5,
    "B":  1.0,
    "C":  0.8,
    "D":  0.5,
    "E":  0.0,  # 赎回建议，建议暂停定投
}

# 信号 → 操作动作
SIGNAL_TO_ACTION: dict[str, str] = {
    "S+": "加倍定投",
    "S":  "加倍定投",
    "A":  "增额定投",
    "B":  "标准定投",
    "C":  "减额定投",
    "D":  "减额定投",
    "E":  "建议赎回",
}

# 信号 → 建议文案
SIGNAL_TO_DESCRIPTION: dict[str, str] = {
    "S+": "极度恐慌区域，历史数据显示定投长期收益最高；建议3倍定投，积极收集低价筹码",
    "S":  "恐慌情绪浓厚，市场大幅回调，定投性价比极高；建议2倍定投加速建仓",
    "A":  "偏恐慌区域，估值进入合理偏低区间；建议1.5倍定投适度加仓",
    "B":  "情绪中性，市场多空均衡；建议标准定投，保持纪律执行",
    "C":  "偏贪婪区域，估值逐步走高；建议0.8倍定投，降低买入成本",
    "D":  "贪婪情绪明显，追涨风险加大；建议0.5倍定投，大幅减少买入",
    "E":  "极度贪婪区域，崩盘风险显著提升；建议暂停定投并考虑分批赎回",
}


@dataclass
class DcaAdvice:
    """定投调整建议"""
    signal_level: str                       # 信号等级 S+~E
    multiplier: float                        # 定投倍数 (0.0~3.0)
    action: str                              # 操作描述
    advice_text: str                         # 详细建议文案
    is_redeem: bool = False                  # 是否触发赎回建议
    signal_index: int = 0                    # 信号在7级中的位置 (0=S+, 6=E)

    def to_dict(self) -> dict:
        return {
            "signal_level": self.signal_level,
            "multiplier": self.multiplier,
            "action": self.action,
            "advice_text": self.advice_text,
            "is_redeem": self.is_redeem,
        }


class DcaAdviceEngine:
    """定投调整建议引擎"""

    VALID_LEVELS: tuple[str, ...] = ("S+", "S", "A", "B", "C", "D", "E")

    def get_advice(self, signal_level: str) -> DcaAdvice:
        """
        根据信号等级生成定投调整建议
        Args:
            signal_level: 7级信号等级 (S+ ~ E)
        Returns:
            DcaAdvice 定投建议
        Raises:
            ValueError: 无效的信号等级
        """
        level = signal_level.strip().upper()
        if level not in self.VALID_LEVELS:
            raise ValueError(
                f"无效信号等级: '{signal_level}'，有效值为 {self.VALID_LEVELS}"
            )

        multiplier = SIGNAL_TO_MULTIPLIER[level]
        action = SIGNAL_TO_ACTION[level]
        advice_text = SIGNAL_TO_DESCRIPTION[level]
        is_redeem = level == "E"
        signal_index = self.VALID_LEVELS.index(level)

        return DcaAdvice(
            signal_level=level,
            multiplier=multiplier,
            action=action,
            advice_text=advice_text,
            is_redeem=is_redeem,
            signal_index=signal_index,
        )

    def get_multiplier(self, signal_level: str) -> float:
        """便捷方法：直接获取定投倍数"""
        return SIGNAL_TO_MULTIPLIER.get(signal_level.strip().upper(), 1.0)

    def is_valid_level(self, signal_level: str) -> bool:
        """检查信号等级是否有效"""
        return signal_level.strip().upper() in self.VALID_LEVELS

    @classmethod
    def all_levels(cls) -> list[str]:
        """返回所有有效信号等级"""
        return list(cls.VALID_LEVELS)
