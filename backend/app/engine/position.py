"""
仓位调整规则
根据综合情绪评分给出仓位建议

核心理念：
- 极度恐慌 → 高仓位（别人恐惧我贪婪）
- 恐慌 → 中高仓位
- 中性 → 中性仓位
- 乐观 → 中低仓位（逐步减仓）
- 极度乐观 → 低仓位（别人贪婪我恐惧）
"""
from dataclasses import dataclass


@dataclass
class PositionAdvice:
    """仓位建议"""
    current_score: float
    sentiment_label: str
    suggested_position: float  # 建议仓位(%)
    cash_reserve: float  # 建议现金(%)
    action: str  # 操作: increase / hold / reduce / heavy_reduce
    reason: str
    risk_level: str  # low / medium / high / extreme


def calculate_position(
    composite_score: float,
    sentiment_label: str,
    current_position: float = 50.0,
    max_single_change: float = 20.0,  # 单次最大调仓幅度
) -> PositionAdvice:
    """
    根据情绪评分计算建议仓位

    Args:
        composite_score: 综合情绪评分(0-100)
        sentiment_label: 情绪标签
        current_position: 当前仓位(%)
        max_single_change: 单次最大调仓幅度(%)

    Returns:
        PositionAdvice: 仓位建议
    """
    # 基础仓位映射（反向：低分=高仓位）
    if composite_score < 15:
        target_position = 80.0
        action = "increase"
        risk_level = "extreme"
        reason = "极度恐慌，市场可能处于底部区域，建议大幅加仓"
    elif composite_score < 25:
        target_position = 70.0
        action = "increase"
        risk_level = "high"
        reason = "市场恐慌，逢低分批加仓，左侧布局"
    elif composite_score < 35:
        target_position = 60.0
        action = "increase"
        risk_level = "medium"
        reason = "市场偏弱，可适度增加仓位，关注超跌机会"
    elif composite_score < 45:
        target_position = 50.0
        action = "hold"
        risk_level = "medium"
        reason = "市场略偏谨慎，建议维持当前仓位观察"
    elif composite_score < 55:
        target_position = 50.0
        action = "hold"
        risk_level = "low"
        reason = "市场中性，保持均衡配置"
    elif composite_score < 65:
        target_position = 45.0
        action = "reduce"
        risk_level = "medium"
        reason = "市场偏乐观，可小幅减仓锁定部分利润"
    elif composite_score < 75:
        target_position = 35.0
        action = "reduce"
        risk_level = "high"
        reason = "市场乐观，建议逐步减仓，落袋为安"
    elif composite_score < 85:
        target_position = 25.0
        action = "heavy_reduce"
        risk_level = "extreme"
        reason = "市场偏热，大幅减仓，仅保留核心仓位"
    else:
        target_position = 15.0
        action = "heavy_reduce"
        risk_level = "extreme"
        reason = "极度乐观，市场可能见顶，清仓式减仓"

    # 限制单次调仓幅度
    change = target_position - current_position
    if abs(change) > max_single_change:
        change = max_single_change if change > 0 else -max_single_change
        target_position = current_position + change

    target_position = max(10.0, min(90.0, target_position))
    cash_reserve = 100.0 - target_position

    return PositionAdvice(
        current_score=composite_score,
        sentiment_label=sentiment_label,
        suggested_position=round(target_position, 1),
        cash_reserve=round(cash_reserve, 1),
        action=action,
        reason=reason,
        risk_level=risk_level,
    )
