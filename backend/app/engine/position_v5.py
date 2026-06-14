"""
仓位建议引擎 — V5.0
5×7 仓位矩阵 + 置信度修正 + 市场体制修正 + 交易成本校验 + 7天频率限制
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from app.engine.signal_mapper import SignalMapper
from app.core.config import settings


class PositionEngineV5:
    """V5.0 仓位建议引擎"""

    # 仓位等级 → 百分比映射
    LEVEL_TO_PCT: dict[str, float] = {
        "empty": 0.0,
        "light": 0.25,
        "mid": 0.50,
        "heavy": 0.75,
        "full": 1.0,
    }

    LEVELS: list[str] = ["empty", "light", "mid", "heavy", "full"]

    def __init__(self, session) -> None:
        self._session = session
        self._matrix = settings.V5_POSITION_MATRIX
        self._level_pct = settings.V5_POSITION_LEVEL_PCT
        self._conf_adj = settings.V5_CONFIDENCE_POSITION_ADJ
        self._cost_threshold = settings.V5_COST_THRESHOLD_PCT
        self._freq_days = settings.V5_FREQUENCY_LIMIT_DAYS

    async def calculate(
        self,
        user_id: str,
        fund_code: str,
        current_position_pct: float,
        signal_level: str,
        confidence_stars: int,
    ) -> dict:
        """
        计算仓位调整建议
        输入：user_id, fund_code, current_position_pct, signal_level, confidence_stars
        输出：PositionAdvice dict
        """
        # 1. 确定当前仓位等级
        current_level = self._pct_to_level(current_position_pct)

        # 2. 矩阵查表
        signal_idx = self._signal_to_idx(signal_level)
        current_idx = self.LEVELS.index(current_level)
        target_level = self._matrix[current_idx][signal_idx]

        # 3. 置信度修正
        conf_factor = self._conf_adj.get(confidence_stars, 0.25)
        target_pct = self.LEVEL_TO_PCT[target_level]
        current_pct = current_position_pct
        if target_pct > current_pct:
            # 加仓：置信度修正
            adjusted_pct = current_pct + (target_pct - current_pct) * conf_factor
        elif target_pct < current_pct:
            # 减仓：置信度修正
            adjusted_pct = current_pct - (current_pct - target_pct) * conf_factor
        else:
            adjusted_pct = target_pct

        # 4. 市场体制修正（简化：牛市可稍激进，熊市更保守）
        # TODO：从 composite 获取 regime
        # adjusted_pct = self._apply_regime_adj(adjusted_pct, regime)

        # 5. 交易成本校验
        cost_rejected = False
        if abs(adjusted_pct - current_pct) < self._cost_threshold:
            cost_rejected = True
            adjusted_pct = current_pct  # 不操作

        # 6. 7天频率检查
        frequency_blocked = False
        last_execute = await self._get_last_execute_date(user_id, fund_code)
        if last_execute:
            days_since = (date.today() - last_execute).days
            if days_since < self._freq_days:
                frequency_blocked = True
                adjusted_pct = current_pct  # 不操作

        # 7. 生成建议原因
        reason = self._generate_reason(
            signal_level, confidence_stars, current_level, target_level,
            cost_rejected, frequency_blocked,
        )

        # 8. 确定操作类型
        if abs(adjusted_pct - current_pct) < 0.01:
            action = "hold"
        elif adjusted_pct > current_pct:
            action = "increase"
        else:
            action = "decrease"

        return {
            "fund_code": fund_code,
            "current_position_pct": round(current_pct, 4),
            "target_position_pct": round(adjusted_pct, 4),
            "action": action,
            "signal_level": signal_level,
            "confidence_stars": confidence_stars,
            "matrix_result": {"current": current_level, "target": target_level},
            "confidence_adj_factor": conf_factor,
            "regime_adj_factor": 1.0,  # TODO
            "cost_rejected": cost_rejected,
            "frequency_blocked": frequency_blocked,
            "reason": reason,
        }

    def _pct_to_level(self, pct: float) -> str:
        """百分比 → 仓位等级"""
        if pct < 0.125:
            return "empty"
        if pct < 0.375:
            return "light"
        if pct < 0.625:
            return "mid"
        if pct < 0.875:
            return "heavy"
        return "full"

    def _signal_to_idx(self, level: str) -> int:
        """信号等级 → 列索引"""
        order = ["S+", "S", "A", "B", "C", "D", "E"]
        try:
            return order.index(level)
        except ValueError:
            return 3  # 默认 B

    async def _get_last_execute_date(
        self, user_id: str, fund_code: str,
    ) -> Optional[date]:
        """获取上次执行日期"""
        try:
            from sqlalchemy import select
            from app.models.position_execution import PositionExecution
            stmt = (
                select(PositionExecution.execute_date)
                .where(
                    PositionExecution.user_id == user_id,
                    PositionExecution.fund_code == fund_code,
                )
                .order_by(PositionExecution.execute_date.desc())
                .limit(1)
            )
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    def _generate_reason(
        self,
        signal_level: str,
        confidence_stars: int,
        current_level: str,
        target_level: str,
        cost_rejected: bool,
        frequency_blocked: bool,
    ) -> str:
        """生成建议原因文案"""
        if cost_rejected:
            return "调整幅度小于交易成本阈值（1.5%），建议暂不操作"
        if frequency_blocked:
            return "7天内已执行过仓位调整，建议等待"

        signal_labels = {
            "S+": "极度恐惧", "S": "恐惧", "A": "偏恐惧",
            "B": "中性", "C": "偏贪婪", "D": "贪婪", "E": "极度贪婪",
        }
        label = signal_labels.get(signal_level, signal_level)
        stars_str = "⭐" * confidence_stars

        return (
            f"当前信号：{label}（{signal_level}），"
            f"置信度：{stars_str}，"
            f"建议仓位从「{current_level}」调整至「{target_level}」"
        )
