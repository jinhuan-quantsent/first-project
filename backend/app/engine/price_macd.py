"""
价格MACD引擎 — L1
基于收盘价计算经典MACD(12/26/9)，用于：
1. 价格趋势二阶确认（DIF/DEA金叉/死叉）
2. 与情绪MACD形成价格-情绪背离检测的基础
3. 前端价格MACD可视化

MACD参数：快线12日，慢线26日，信号线9日（经典参数）
EMA实现参考 trend_guard._calculate_ema，SMA初始化 + 乘数 2/(period+1)
"""
from __future__ import annotations

import numpy as np


class PriceMACD:
    """价格MACD计算器（经典12/26/9参数）"""

    FAST_PERIOD: int = 12
    SLOW_PERIOD: int = 26
    SIGNAL_PERIOD: int = 9

    def compute(
        self,
        prices: list[float],
    ) -> dict:
        """
        计算价格MACD指标

        输入：最近N天的收盘价序列（按时间升序）
        输出：{
            "macd_line": float,       # DIF（快线EMA - 慢线EMA）
            "signal_line": float,     # DEA（DIF的9日EMA）
            "histogram": float,       # HIST（DIF - DEA）
            "trend": str,             # "bullish" / "bearish" / "neutral"
            "cross": str | None,      # "golden_cross" / "death_cross" / None
            "same_direction_days": int, # DIF与DEA同向的连续天数
            "momentum": float,        # 动量（HIST变化率）
        }
        """
        if len(prices) < self.SLOW_PERIOD + self.SIGNAL_PERIOD:
            return self._insufficient_data(len(prices))

        data = np.array(prices, dtype=float)

        # 1. 计算EMA
        ema_fast = self._ema(data, self.FAST_PERIOD)
        ema_slow = self._ema(data, self.SLOW_PERIOD)

        # 2. DIF = 快线EMA - 慢线EMA（尾部对齐）
        min_len = min(len(ema_fast), len(ema_slow))
        dif = ema_fast[-min_len:] - ema_slow[-min_len:]

        # 3. DEA = DIF的9日EMA
        if len(dif) < self.SIGNAL_PERIOD:
            return self._insufficient_data(len(prices))

        dea = self._ema(dif, self.SIGNAL_PERIOD)

        # 4. HIST = DIF - DEA（尾部对齐）
        min_len2 = min(len(dif), len(dea))
        dif_aligned = dif[-min_len2:]
        dea_aligned = dea[-min_len2:]
        hist = dif_aligned - dea_aligned

        current_dif = float(dif_aligned[-1])
        current_dea = float(dea_aligned[-1])
        current_hist = float(hist[-1])

        # 5. 判断趋势（DIF与DEA的位置关系）
        if current_dif > current_dea:
            trend = "bullish"
        elif current_dif < current_dea:
            trend = "bearish"
        else:
            trend = "neutral"

        # 6. 判断交叉（DIF穿越DEA）
        cross = None
        if min_len2 >= 2:
            prev_dif = float(dif_aligned[-2])
            prev_dea = float(dea_aligned[-2])
            if prev_dif <= prev_dea and current_dif > current_dea:
                cross = "golden_cross"
            elif prev_dif >= prev_dea and current_dif < current_dea:
                cross = "death_cross"

        # 7. 同向连续天数（DIF和DEA同正或同负）
        same_direction_days = 0
        for i in range(min_len2 - 1, -1, -1):
            d = float(dif_aligned[i])
            s = float(dea_aligned[i])
            if (d > 0 and s > 0) or (d < 0 and s < 0):
                same_direction_days += 1
            else:
                break

        # 8. 动量（HIST变化率）
        momentum = 0.0
        if min_len2 >= 2:
            prev_hist = float(hist[-2])
            if abs(prev_hist) > 0:
                momentum = (current_hist - prev_hist) / abs(prev_hist)

        return {
            "macd_line": round(current_dif, 4),
            "signal_line": round(current_dea, 4),
            "histogram": round(current_hist, 4),
            "trend": trend,
            "cross": cross,
            "same_direction_days": same_direction_days,
            "momentum": round(momentum, 4),
        }

    def compute_history(
        self,
        prices: list[float],
    ) -> list[dict]:
        """
        计算完整的价格MACD历史序列（DIF/DEA/HIST），供前端可视化。

        返回与输入序列尾部对齐的列表，每个元素:
            {"dif": float, "dea": float, "hist": float}

        数据不足时返回空列表。
        """
        if len(prices) < self.SLOW_PERIOD + self.SIGNAL_PERIOD:
            return []

        data = np.array(prices, dtype=float)

        # 1. 计算EMA
        ema_fast = self._ema(data, self.FAST_PERIOD)
        ema_slow = self._ema(data, self.SLOW_PERIOD)

        # 2. DIF = 快线EMA - 慢线EMA（尾部对齐）
        min_len = min(len(ema_fast), len(ema_slow))
        dif = ema_fast[-min_len:] - ema_slow[-min_len:]

        if len(dif) < self.SIGNAL_PERIOD:
            return []

        # 3. DEA = DIF的9日EMA
        dea = self._ema(dif, self.SIGNAL_PERIOD)

        # 4. HIST = DIF - DEA（尾部对齐）
        min_len2 = min(len(dif), len(dea))
        dif_series = dif[-min_len2:]
        dea_series = dea[-min_len2:]
        hist_series = dif_series - dea_series

        # 5. 构建结果列表
        result = []
        for i in range(min_len2):
            result.append({
                "dif": round(float(dif_series[i]), 4),
                "dea": round(float(dea_series[i]), 4),
                "hist": round(float(hist_series[i]), 4),
            })
        return result

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """计算指数移动平均（SMA初始化 + 乘数 2/(period+1)）"""
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
