"""
机会雷达推荐引擎
基于板块情绪评分和动量，推荐投资机会

输出维度：
- 强势板块（情绪高分 + 正动量）
- 超跌反弹机会（情绪低分 + 极端标记）
- 稳健配置（情绪中性 + 低波动）
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OpportunityItem:
    """机会推荐项"""
    sector_code: str
    sector_name: str
    sector_group: str
    sentiment_score: float
    sentiment_label: str
    momentum_5d: float
    momentum_20d: float
    strength_index: float
    opportunity_type: str  # strong / rebound / steady
    opportunity_reason: str
    recommended_funds: list[str] = field(default_factory=list)  # 推荐基金代码


@dataclass
class RecommendationResult:
    """机会雷达结果"""
    strong_sectors: list[OpportunityItem] = field(default_factory=list)
    rebound_opportunities: list[OpportunityItem] = field(default_factory=list)
    steady_choices: list[OpportunityItem] = field(default_factory=list)
    top_picks: list[OpportunityItem] = field(default_factory=list)
    summary: str = ""


def generate_recommendations(
    sector_data: list[dict],
    top_n: int = 5,
) -> RecommendationResult:
    """
    生成投资机会推荐

    Args:
        sector_data: 板块数据列表，每项包含:
            - sector_code, sector_name, sector_group
            - sentiment_score, sentiment_label
            - momentum_5d, momentum_20d
            - strength_index
        top_n: 每类推荐数量

    Returns:
        RecommendationResult: 推荐结果
    """
    strong: list[OpportunityItem] = []
    rebound: list[OpportunityItem] = []
    steady: list[OpportunityItem] = []

    for s in sector_data:
        score = s.get("sentiment_score", 50.0)
        momentum_5d = s.get("momentum_5d", 0.0)
        strength = s.get("strength_index", 50.0)
        label = s.get("sentiment_label", "neutral")

        item = OpportunityItem(
            sector_code=s.get("sector_code", ""),
            sector_name=s.get("sector_name", ""),
            sector_group=s.get("sector_group", ""),
            sentiment_score=score,
            sentiment_label=label,
            momentum_5d=momentum_5d,
            momentum_20d=s.get("momentum_20d", 0.0),
            strength_index=strength,
            opportunity_type="steady",
            opportunity_reason="",
        )

        # 强势板块：情绪分 > 60 且动量 > 0
        if score > 60 and momentum_5d > 0:
            item.opportunity_type = "strong"
            item.opportunity_reason = f"{item.sector_name}情绪积极（{score}分），5日动量{momentum_5d:+.1f}%，趋势向好"
            strong.append(item)

        # 超跌反弹：情绪分 < 35 且有极端标记
        elif score < 35 and label in ("fear", "extreme_fear"):
            item.opportunity_type = "rebound"
            item.opportunity_reason = f"{item.sector_name}情绪极度低迷（{score}分），可能存在超跌反弹机会"
            rebound.append(item)

        # 稳健配置：情绪中性 40-60 且强度适中
        elif 40 <= score <= 60:
            item.opportunity_type = "steady"
            item.opportunity_reason = f"{item.sector_name}情绪中性（{score}分），适合稳健配置"
            steady.append(item)

    # 排序
    strong.sort(key=lambda x: x.sentiment_score + x.momentum_5d, reverse=True)
    rebound.sort(key=lambda x: x.sentiment_score)  # 最低分优先
    steady.sort(key=lambda x: abs(x.sentiment_score - 50))  # 最接近50优先

    strong = strong[:top_n]
    rebound = rebound[:top_n]
    steady = steady[:top_n]

    # 综合推荐 Top Picks
    top_picks = strong[:2] + rebound[:2] + steady[:1]

    # 生成总结
    parts = []
    if strong:
        parts.append(f"强势板块关注: {', '.join(s.sector_name for s in strong[:3])}")
    if rebound:
        parts.append(f"超跌机会关注: {', '.join(r.sector_name for r in rebound[:3])}")
    if steady:
        parts.append(f"稳健配置关注: {', '.join(s.sector_name for s in steady[:2])}")

    summary = "；".join(parts) if parts else "当前市场无明显结构性机会，建议观望为主"

    return RecommendationResult(
        strong_sectors=strong,
        rebound_opportunities=rebound,
        steady_choices=steady,
        top_picks=top_picks,
        summary=summary,
    )
