"""
情绪MACD引擎 — V5.0
计算综合情绪分数的MACD指标，用于：
1. 置信度持续性评分（同向天数）
2. 信号趋势二阶确认（MACD金叉/死叉）
3. 防线3辅助判断（价格-情绪背离时的趋势确认）

MACD参数：快线12日，慢线26日，信号线9日（经典参数）
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.core.config import settings


class SentimentMACD:
    """情绪MACD计算器"""

    # 经典MACD参数
    FAST_PERIOD: int = 12
    SLOW_PERIOD: int = 26
    SIGNAL_PERIOD: int = 9

    def compute(
        self,
        score_series: list[float],
    ) -> dict:
        """
        计算情绪分数的MACD指标

        输入：最近N天的综合情绪分数序列（按时间升序）
        输出：{
            "macd_line": float,       # MACD线（快线-慢线）
            "signal_line": float,     # 信号线（MACD的9日EMA）
            "histogram": float,       # 柱状图（MACD-信号线）
            "trend": str,             # "bullish" / "bearish" / "neutral"
            "cross": str | None,      # "golden_cross" / "death_cross" / None
            "same_direction_days": int, # MACD与信号同向的连续天数
            "momentum": float,        # 动量（MACD变化率）
        }
        """
        if len(score_series) < self.SLOW_PERIOD + self.SIGNAL_PERIOD:
            return self._insufficient_data(len(score_series))

        scores = np.array(score_series, dtype=float)

        # 1. 计算EMA
        ema_fast = self._ema(scores, self.FAST_PERIOD)
        ema_slow = self._ema(scores, self.SLOW_PERIOD)

        # 2. MACD线 = 快线EMA - 慢线EMA
        # 对齐：EMA长度 = len(scores) - period + 1
        # 对齐后取 min(len(ema_fast), len(ema_slow))
        min_len = min(len(ema_fast), len(ema_slow))
        macd_line = ema_fast[-min_len:] - ema_slow[-min_len:]

        # 3. 信号线 = MACD的9日EMA
        if len(macd_line) < self.SIGNAL_PERIOD:
            return self._insufficient_data(len(score_series))

        signal_line = self._ema(macd_line, self.SIGNAL_PERIOD)

        # 4. 柱状图 = MACD - 信号线
        min_len2 = min(len(macd_line), len(signal_line))
        histogram = macd_line[-min_len2:] - signal_line[-min_len2:]

        # 5. 判断趋势
        current_macd = float(macd_line[-1]) if len(macd_line) > 0 else 0.0
        current_signal = float(signal_line[-1]) if len(signal_line) > 0 else 0.0
        current_hist = float(histogram[-1]) if len(histogram) > 0 else 0.0

        if current_macd > 0 and current_hist > 0:
            trend = "bullish"
        elif current_macd < 0 and current_hist < 0:
            trend = "bearish"
        else:
            trend = "neutral"

        # 6. 判断交叉
        cross = None
        if len(histogram) >= 2:
            prev_hist = float(histogram[-2])
            curr_hist = float(histogram[-1])
            if prev_hist <= 0 and curr_hist > 0:
                cross = "golden_cross"
            elif prev_hist >= 0 and curr_hist < 0:
                cross = "death_cross"

        # 7. 同向连续天数
        same_direction_days = 0
        if len(histogram) > 0:
            sign = 1 if current_hist >= 0 else -1
            for i in range(len(histogram) - 1, -1, -1):
                if (float(histogram[i]) >= 0 and sign > 0) or (float(histogram[i]) < 0 and sign < 0):
                    same_direction_days += 1
                else:
                    break

        # 8. 动量（MACD变化率）
        momentum = 0.0
        if len(macd_line) >= 2:
            prev_macd = float(macd_line[-2])
            if abs(prev_macd) > 0.01:
                momentum = round((current_macd - prev_macd) / abs(prev_macd) * 100, 2)

        return {
            "macd_line": round(current_macd, 4),
            "signal_line": round(current_signal, 4),
            "histogram": round(current_hist, 4),
            "trend": trend,
            "cross": cross,
            "same_direction_days": same_direction_days,
            "momentum": momentum,
        }

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """计算指数移动平均"""
        if len(data) < period:
            return np.array([])

        # 初始值用SMA
        sma = np.mean(data[:period])
        ema_values = [sma]
        multiplier = 2.0 / (period + 1)

        for i in range(period, len(data)):
            ema_values.append(
                (data[i] - ema_values[-1]) * multiplier + ema_values[-1]
            )

        return np.array(ema_values)

    def _insufficient_data(self, available: int) -> dict:
        """数据不足时的降级返回"""
        return {
            "macd_line": 0.0,
            "signal_line": 0.0,
            "histogram": 0.0,
            "trend": "neutral",
            "cross": None,
            "same_direction_days": 0,
            "momentum": 0.0,
            "insufficient_data": True,
            "available_days": available,
            "required_days": self.SLOW_PERIOD + self.SIGNAL_PERIOD,
        }
