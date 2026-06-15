"""
价格-情绪背离检测器 — V5.0
检测价格与情绪方向不一致的背离信号：
- Bearish Divergence：价格创新高，但情绪分数下降 → 上涨动力衰竭，风险信号
- Bullish Divergence：价格创新低，但情绪分数上升 → 下跌动力衰竭，机会信号

用于置信度防线3和信号二阶确认
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.core.config import settings


class DivergenceDetector:
    """价格-情绪背离检测器"""

    # 检测窗口
    LOOKBACK_DAYS: int = 20  # 回看20天
    MIN_TREND_DAYS: int = 5  # 最少5天趋势才判定

    def detect(
        self,
        price_series: list[float],
        sentiment_series: list[float],
    ) -> dict:
        """
        检测价格-情绪背离

        输入：
          price_series: 最近N天的收盘价序列（按时间升序）
          sentiment_series: 最近N天的综合情绪分数序列（按时间升序）

        输出：{
            "divergence_type": str | None,  # "bearish" / "bullish" / None
            "strength": float,               # 背离强度 0-100
            "price_trend": str,              # "up" / "down" / "flat"
            "sentiment_trend": str,          # "up" / "down" / "flat"
            "description": str,              # 中文描述
        }
        """
        if len(price_series) < self.MIN_TREND_DAYS or len(sentiment_series) < self.MIN_TREND_DAYS:
            return self._insufficient_data(len(price_series))

        # 取最近的数据
        n = min(len(price_series), len(sentiment_series), self.LOOKBACK_DAYS)
        prices = np.array(price_series[-n:], dtype=float)
        sentiments = np.array(sentiment_series[-n:], dtype=float)

        # 1. 计算价格趋势（线性回归斜率）
        price_slope, price_r = self._linear_regression(prices)
        sentiment_slope, sentiment_r = self._linear_regression(sentiments)

        # 2. 判定趋势方向
        price_trend = self._classify_trend(price_slope, price_r)
        sentiment_trend = self._classify_trend(sentiment_slope, sentiment_r)

        # 3. 检测背离
        divergence_type = None
        strength = 0.0

        if price_trend == "up" and sentiment_trend == "down":
            # Bearish divergence: 价格涨 + 情绪跌
            divergence_type = "bearish"
            strength = self._calc_divergence_strength(price_slope, sentiment_slope, price_r, sentiment_r)
        elif price_trend == "down" and sentiment_trend == "up":
            # Bullish divergence: 价格跌 + 情绪涨
            divergence_type = "bullish"
            strength = self._calc_divergence_strength(sentiment_slope, price_slope, sentiment_r, price_r)
        elif price_trend == "up" and sentiment_trend == "flat":
            # 价格涨但情绪持平 → 弱bearish
            divergence_type = "bearish"
            strength = min(30.0, abs(price_slope) * 100)
        elif price_trend == "down" and sentiment_trend == "flat":
            # 价格跌但情绪持平 → 弱bullish
            divergence_type = "bullish"
            strength = min(30.0, abs(price_slope) * 100)

        # 4. 生成描述
        description = self._generate_description(divergence_type, strength, price_trend, sentiment_trend)

        return {
            "divergence_type": divergence_type,
            "strength": round(strength, 2),
            "price_trend": price_trend,
            "sentiment_trend": sentiment_trend,
            "description": description,
        }

    def _linear_regression(self, data: np.ndarray) -> tuple[float, float]:
        """线性回归，返回(斜率, R²)"""
        n = len(data)
        if n < 2:
            return 0.0, 0.0

        x = np.arange(n, dtype=float)
        x_mean = np.mean(x)
        y_mean = np.mean(data)

        ss_xy = np.sum((x - x_mean) * (data - y_mean))
        ss_xx = np.sum((x - x_mean) ** 2)
        ss_yy = np.sum((data - y_mean) ** 2)

        if ss_xx == 0 or ss_yy == 0:
            return 0.0, 0.0

        slope = ss_xy / ss_xx
        r_squared = (ss_xy ** 2) / (ss_xx * ss_yy)

        # 归一化斜率（按数据均值，方便跨量纲比较）
        normalized_slope = slope / max(abs(y_mean), 0.01)

        return float(normalized_slope), float(r_squared)

    def _classify_trend(self, slope: float, r_squared: float) -> str:
        """根据斜率和R²判定趋势方向"""
        # R²过低 → 趋势不明确
        if r_squared < 0.3:
            return "flat"

        if slope > 0.01:  # 归一化斜率阈值
            return "up"
        elif slope < -0.01:
            return "down"
        else:
            return "flat"

    def _calc_divergence_strength(
        self,
        dominant_slope: float,
        divergent_slope: float,
        dominant_r: float,
        divergent_r: float,
    ) -> float:
        """计算背离强度（0-100）"""
        # 强度 = 主趋势强度 × 背离趋势强度 × R²加权
        trend_strength = min(abs(dominant_slope) * 50, 50)
        confidence = (dominant_r + divergent_r) / 2.0
        strength = trend_strength * confidence * 2  # 缩放到0-100
        return min(100.0, max(0.0, strength))

    def _generate_description(
        self,
        divergence_type: Optional[str],
        strength: float,
        price_trend: str,
        sentiment_trend: str,
    ) -> str:
        """生成背离描述"""
        if divergence_type is None:
            return "价格与情绪方向一致，无背离信号"

        trend_labels = {"up": "上涨", "down": "下跌", "flat": "持平"}

        if divergence_type == "bearish":
            base = f"⚠️ 看跌背离：价格{trend_labels[price_trend]}但情绪{trend_labels[sentiment_trend]}"
            if strength > 60:
                return f"{base}，背离强度{strength:.0f}%（强）— 上涨动力衰竭风险高"
            elif strength > 30:
                return f"{base}，背离强度{strength:.0f}%（中）— 需关注上涨持续性"
            else:
                return f"{base}，背离强度{strength:.0f}%（弱）— 暂不构成风险信号"
        else:  # bullish
            base = f"💡 看涨背离：价格{trend_labels[price_trend]}但情绪{trend_labels[sentiment_trend]}"
            if strength > 60:
                return f"{base}，背离强度{strength:.0f}%（强）— 下跌动力衰竭，可能是布局机会"
            elif strength > 30:
                return f"{base}，背离强度{strength:.0f}%（中）— 下跌可能接近尾声"
            else:
                return f"{base}，背离强度{strength:.0f}%（弱）— 暂不构成反转信号"

    def _insufficient_data(self, available: int) -> dict:
        """数据不足时的降级返回"""
        return {
            "divergence_type": None,
            "strength": 0.0,
            "price_trend": "flat",
            "sentiment_trend": "flat",
            "description": f"数据不足（{available}天），需要至少{self.MIN_TREND_DAYS}天",
        }
