"""
价格-情绪背离检测器 — V5.0
检测价格与情绪方向不一致的背离信号：
- Bearish Divergence：价格创新高，但情绪分数下降 → 上涨动力衰竭，风险信号
- Bullish Divergence：价格创新低，但情绪分数上升 → 下跌动力衰竭，机会信号

用于置信度防线3和信号二阶确认

V5.0 增强:
  - 新增 detect_bottom_divergence(): 基于双低点比较的底背离检测
    用于 S+ 逆向信号验证（价格新低但情绪分数未新低）
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


# ============================================================
# 底背离检测函数（V5.0 新增）
# 用于 S+ 逆向信号验证：价格新低但情绪分数未新低
# ============================================================

def _find_local_minima(
    values: list[float],
    window: int = 5,
) -> list[int]:
    """找出局部最小值的索引。

    一个点 i 是局部最小值，当且仅当它是 [i-window, i+window] 范围内的最小值。
    """
    n = len(values)
    minima = []
    for i in range(window, n - window):
        left = values[i - window:i]
        right = values[i + 1:i + 1 + window]
        if all(values[i] <= v for v in left) and all(values[i] <= v for v in right):
            minima.append(i)
    return minima


def detect_bottom_divergence(
    prices: list[float],
    scores: list[float],
    window: int = 20,
    min_interval: int = 10,
) -> dict | None:
    """
    检测底背离信号。

    底背离定义：
      - 价格创新低（后一个低点 < 前一个低点）
      - 但情绪分数未创新低（后低点的分数 > 前低点的分数）
      - 说明下跌动能减弱，可能见底反弹

    Args:
        prices: 收盘价序列（最近N日，oldest first）
        scores: 情绪分数序列（与prices对齐）
        window: 检测窗口，用于寻找局部低点和比较
        min_interval: 两个低点间的最小间隔（交易日）

    Returns:
        底背离信号字典，或 None（无背离）:
        {
            'divergence': True,
            'price_low_1': float,     # 前低点价格
            'price_low_2': float,     # 当前低点价格（更低）
            'score_at_low_1': float,  # 前低点时情绪分
            'score_at_low_2': float,  # 当前低点时情绪分（更高）
            'low_1_idx': int,         # 前低点索引
            'low_2_idx': int,         # 当前低点索引
            'strength': 'weak' | 'moderate' | 'strong'
        }
    """
    n = min(len(prices), len(scores))
    if n < window + min_interval:
        return None

    # 对齐截断
    prices = list(prices[-n:])
    scores = list(scores[-n:])

    # 寻找价格的局部最小值
    lookback = min(window, n // 3)
    minima_indices = _find_local_minima(prices, window=max(3, lookback // 2))

    if len(minima_indices) < 2:
        # 如果没找到足够的局部最小值，用滑动窗口找最低点
        # 将序列分成两半，各自找最低点
        half = n // 2
        # 前半段最低点
        seg1 = prices[:half]
        low_1_idx = seg1.index(min(seg1))
        # 后半段最低点
        seg2 = prices[half:]
        low_2_idx = half + seg2.index(min(seg2))

        if low_2_idx - low_1_idx < min_interval:
            return None
        minima_indices = [low_1_idx, low_2_idx]

    # 从局部最小值中找底背离对
    # 遍历所有低点对，找最近的一对满足底背离条件
    best_pair = None
    for i in range(len(minima_indices) - 1):
        for j in range(i + 1, len(minima_indices)):
            idx_1 = minima_indices[i]
            idx_2 = minima_indices[j]

            # 间隔检查
            if idx_2 - idx_1 < min_interval:
                continue

            price_low_1 = prices[idx_1]
            price_low_2 = prices[idx_2]
            score_at_low_1 = scores[idx_1]
            score_at_low_2 = scores[idx_2]

            # 底背离条件：价格新低（low_2 < low_1），但情绪分更高（score_2 > score_1）
            if price_low_2 < price_low_1 and score_at_low_2 > score_at_low_1:
                score_diff = score_at_low_2 - score_at_low_1
                # 选择情绪分差异最大的对
                if best_pair is None or score_diff > best_pair["score_diff"]:
                    best_pair = {
                        "divergence": True,
                        "price_low_1": float(price_low_1),
                        "price_low_2": float(price_low_2),
                        "score_at_low_1": float(score_at_low_1),
                        "score_at_low_2": float(score_at_low_2),
                        "low_1_idx": int(idx_1),
                        "low_2_idx": int(idx_2),
                        "score_diff": float(score_diff),
                    }

    if best_pair is None:
        return None

    # 强度判定
    score_diff = best_pair.pop("score_diff")
    if score_diff < 3:
        strength = "weak"
    elif score_diff <= 8:
        strength = "moderate"
    else:
        strength = "strong"

    best_pair["strength"] = strength
    return best_pair
