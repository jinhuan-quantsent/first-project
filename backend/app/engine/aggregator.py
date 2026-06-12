"""
情绪聚合引擎
综合7大因子评分，生成市场情绪判断

核心概念：
- 综合评分: 7因子加权平均 → 0-100分
- 情绪标签: extreme_fear/fear/neutral/greed/extreme_greed
- Top3因子: 风险优先原则（低分因子优先展示）
- 指数分化度: 多指数间评分标准差
- 一句结论: 基于评分+趋势的自然语言总结
"""
from dataclasses import dataclass, field
from typing import Optional

from app.engine.scoring import FactorScore


# ============================================================
# 因子权重配置
# ============================================================
DEFAULT_WEIGHTS: dict[str, float] = {
    "波动率": 0.15,
    "换手率": 0.10,
    "涨跌比": 0.15,
    "新高占比": 0.12,
    "融资融券": 0.18,
    "股债比": 0.15,
    "RSI": 0.15,
}


# 指数市值权重（用于计算多指数综合情绪）
INDEX_MARKET_WEIGHTS: dict[str, float] = {
    "SH000001": 0.25,  # 上证综指
    "SH000300": 0.30,  # 沪深300
    "SZ399001": 0.25,  # 深证成指
    "SZ399006": 0.20,  # 创业板指
}


@dataclass
class CompositeResult:
    """综合情绪结果"""
    index_code: str = ""
    index_name: str = ""
    composite_score: float = 50.0
    sentiment_label: str = "neutral"
    factor_scores: dict[str, FactorScore] = field(default_factory=dict)
    top3_factors: list[FactorScore] = field(default_factory=list)
    conclusion: str = ""
    operation_advice: str = ""
    divergence_index: float = 0.0
    trend_direction: str = "stable"
    trend_strength: float = 0.0
    is_extreme: bool = False
    abnormal_signals: list[str] = field(default_factory=list)


# ============================================================
# 加权综合评分
# ============================================================
def calculate_composite_score(
    factor_scores: dict[str, FactorScore],
    weights: Optional[dict[str, float]] = None,
) -> float:
    """
    计算7因子加权综合评分

    Args:
        factor_scores: {因子名: FactorScore}
        weights: 自定义权重，默认使用 DEFAULT_WEIGHTS

    Returns:
        float: 0-100 综合评分
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    total_score = 0.0
    total_weight = 0.0

    for factor_name, factor_score in factor_scores.items():
        weight = weights.get(factor_name, 0.1)
        total_score += factor_score.score * weight
        total_weight += weight

    if total_weight > 0:
        return round(total_score / total_weight, 1)
    return 50.0


# ============================================================
# Top3 因子（风险优先）
# ============================================================
def select_top3_factors(factor_scores: dict[str, FactorScore]) -> list[FactorScore]:
    """
    选择 Top3 因子（风险优先原则）

    规则：
    1. 有极端标记的因子优先
    2. 偏离中性(50分)越远越优先
    3. 低分(恐慌)略优先于高分(贪婪) — 风险规避

    Args:
        factor_scores: {因子名: FactorScore}

    Returns:
        list[FactorScore]: Top3 因子列表
    """
    factors = list(factor_scores.values())

    # 排序：极端优先 > 偏离度 > 偏低分优先
    def sort_key(f: FactorScore) -> tuple[int, float, float]:
        extreme_priority = 0 if f.is_extreme else 1
        deviation = abs(f.score - 50.0)
        # 低分加权：恐慌信号比贪婪信号更有参考价值
        risk_bias = 1.1 if f.score < 50 else 0.9
        return (extreme_priority, -deviation * risk_bias, f.score)

    sorted_factors = sorted(factors, key=sort_key)
    return sorted_factors[:3]


# ============================================================
# 情绪标签映射
# ============================================================
def get_sentiment_label(score: float) -> str:
    """
    根据综合评分映射情绪标签

    Args:
        score: 0-100 综合评分

    Returns:
        str: extreme_fear / fear / neutral / greed / extreme_greed
    """
    if score < 20:
        return "extreme_fear"
    elif score < 40:
        return "fear"
    elif score < 60:
        return "neutral"
    elif score < 80:
        return "greed"
    else:
        return "extreme_greed"


SENTIMENT_LABEL_CN: dict[str, str] = {
    "extreme_fear": "极度恐慌",
    "fear": "恐慌",
    "neutral": "中性",
    "greed": "乐观",
    "extreme_greed": "极度乐观",
}


# ============================================================
# 操作建议
# ============================================================
def get_operation_advice(score: float) -> str:
    """
    根据综合评分生成操作建议

    Args:
        score: 0-100 综合评分

    Returns:
        str: 操作建议文字
    """
    if score < 15:
        return "【极度恐慌】市场处于恐慌底部区域，建议分批建仓，左侧布局优质标的。仓位可提升至70-80%。"
    elif score < 25:
        return "【恐慌】市场情绪低迷，可能是阶段性底部。建议小仓位试探性买入，仓位控制在50-60%。"
    elif score < 35:
        return "【偏恐慌】市场信心不足，建议观望为主，逢低可小幅加仓。仓位控制在40-50%。"
    elif score < 45:
        return "【偏弱】市场略偏谨慎，建议持有现有仓位，等待更明确信号。仓位控制在40-50%。"
    elif score < 55:
        return "【中性】市场情绪均衡，建议维持中性仓位，关注结构机会。仓位控制在40-60%。"
    elif score < 65:
        return "【偏乐观】市场情绪偏暖，可适度参与，注意控制风险。仓位控制在50-65%。"
    elif score < 75:
        return "【乐观】市场情绪积极，趋势向好，可积极参与但注意不要追高。仓位控制在60-70%。"
    elif score < 85:
        return "【偏热】市场情绪较高，短期可能超买。建议逐步减仓锁定利润。仓位控制在40-50%。"
    else:
        return "【极度乐观】市场情绪过热，警惕回调风险。建议大幅减仓至30%以下，等待调整。"


# ============================================================
# 单指数情绪计算
# ============================================================
def calculate_index_sentiment(
    index_code: str,
    index_name: str,
    factor_scores: dict[str, FactorScore],
    previous_score: Optional[float] = None,
) -> CompositeResult:
    """
    计算单个指数的完整情绪分析

    Args:
        index_code: 指数代码
        index_name: 指数名称
        factor_scores: 7因子评分字典
        previous_score: 前一交易日综合评分（用于趋势判断）

    Returns:
        CompositeResult: 完整情绪分析结果
    """
    # 综合评分
    composite_score = calculate_composite_score(factor_scores)
    sentiment_label = get_sentiment_label(composite_score)

    # Top3 因子
    top3 = select_top3_factors(factor_scores)

    # 趋势判断
    if previous_score is not None:
        delta = composite_score - previous_score
        if delta > 5:
            trend_direction = "up"
            trend_strength = min(abs(delta) * 2, 100)
        elif delta < -5:
            trend_direction = "down"
            trend_strength = min(abs(delta) * 2, 100)
        else:
            trend_direction = "stable"
            trend_strength = abs(delta) * 2
    else:
        trend_direction = "stable"
        trend_strength = 0.0

    # 极端检测
    is_extreme = any(f.is_extreme for f in factor_scores.values())
    abnormal_signals = [
        f"{f.factor_name}: {f.extreme_type}"
        for f in factor_scores.values()
        if f.is_extreme
    ]

    # 结论
    conclusion = generate_conclusion(composite_score, sentiment_label, trend_direction)

    # 操作建议
    operation_advice = get_operation_advice(composite_score)

    return CompositeResult(
        index_code=index_code,
        index_name=index_name,
        composite_score=composite_score,
        sentiment_label=sentiment_label,
        factor_scores=factor_scores,
        top3_factors=top3,
        conclusion=conclusion,
        operation_advice=operation_advice,
        divergence_index=0.0,
        trend_direction=trend_direction,
        trend_strength=round(trend_strength, 1),
        is_extreme=is_extreme,
        abnormal_signals=abnormal_signals,
    )


# ============================================================
# 多指数市值加权综合情绪
# ============================================================
def calculate_composite_sentiment(
    index_results: dict[str, CompositeResult],
    weights: Optional[dict[str, float]] = None,
) -> CompositeResult:
    """
    多指数市值加权综合情绪

    Args:
        index_results: {指数代码: CompositeResult}
        weights: 指数权重，默认使用 INDEX_MARKET_WEIGHTS

    Returns:
        CompositeResult: 综合情绪
    """
    if weights is None:
        weights = INDEX_MARKET_WEIGHTS

    total_score = 0.0
    total_weight = 0.0

    for code, result in index_results.items():
        w = weights.get(code, 0.25)
        total_score += result.composite_score * w
        total_weight += w

    if total_weight > 0:
        composite_score = round(total_score / total_weight, 1)
    else:
        composite_score = 50.0

    sentiment_label = get_sentiment_label(composite_score)
    divergence = calculate_divergence(index_results)

    # 收集所有因子
    all_factors: dict[str, FactorScore] = {}
    for result in index_results.values():
        all_factors.update(result.factor_scores)

    top3 = select_top3_factors(all_factors)

    return CompositeResult(
        index_code="COMPOSITE",
        index_name="综合情绪",
        composite_score=composite_score,
        sentiment_label=sentiment_label,
        factor_scores=all_factors,
        top3_factors=top3,
        conclusion=generate_conclusion(composite_score, sentiment_label, "stable"),
        operation_advice=get_operation_advice(composite_score),
        divergence_index=divergence,
    )


# ============================================================
# 指数分化度
# ============================================================
def calculate_divergence(index_results: dict[str, CompositeResult]) -> float:
    """
    计算指数分化度

    使用各指数评分的标准差来衡量分化程度：
    - <5: 高度一致
    - 5-10: 温和分化
    - 10-20: 明显分化
    - >20: 严重分化

    Args:
        index_results: {指数代码: CompositeResult}

    Returns:
        float: 0-100 分化度指数
    """
    scores = [r.composite_score for r in index_results.values()]
    if len(scores) < 2:
        return 0.0

    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    std_dev = variance ** 0.5

    # 映射到 0-100
    divergence = min(std_dev * 4, 100)
    return round(divergence, 1)


# ============================================================
# 一句结论
# ============================================================
def generate_conclusion(score: float, label: str, trend: str) -> str:
    """
    生成一句结论

    Args:
        score: 综合评分
        label: 情绪标签
        trend: 趋势方向 up/down/stable

    Returns:
        str: 一句话市场总结
    """
    cn_label = SENTIMENT_LABEL_CN.get(label, "中性")

    trend_text = {
        "up": "情绪回暖，",
        "down": "情绪转弱，",
        "stable": "",
    }.get(trend, "")

    if label == "extreme_fear":
        return f"{trend_text}市场处于{cn_label}状态（{score}分），恐慌情绪蔓延，或是中长期布局良机"
    elif label == "fear":
        return f"{trend_text}市场{cn_label}（{score}分），信心不足，建议谨慎观望"
    elif label == "neutral":
        return f"{trend_text}市场情绪{cn_label}（{score}分），多空均衡，关注结构性机会"
    elif label == "greed":
        return f"{trend_text}市场{cn_label}（{score}分），情绪积极，趋势向好但需注意风险"
    else:
        return f"{trend_text}市场{cn_label}（{score}分），短期可能超买，警惕回调风险"
