"""
机会雷达推荐引擎
基于板块情绪评分和动量，推荐投资机会

V5.0 增强：
- opportunity_reason 从简单 string → 结构化 ThreePartReason
- 推荐理由包含观察→分析→行动三段
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
    signal_level: str = "B"
    momentum_5d: float = 0.0
    momentum_20d: float = 0.0
    strength_index: float = 50.0
    strength_rank: int = 0
    opportunity_type: str = "steady"  # strong / rebound / steady
    opportunity_reason: str = ""
    # V5 结构化理由
    reason: dict = field(default_factory=dict)  # {observation, analysis, action}
    recommended_funds: list[str] = field(default_factory=list)


@dataclass
class RecommendationResult:
    """机会雷达结果"""
    strong_sectors: list[OpportunityItem] = field(default_factory=list)
    rebound_opportunities: list[OpportunityItem] = field(default_factory=list)
    steady_choices: list[OpportunityItem] = field(default_factory=list)
    top_picks: list[OpportunityItem] = field(default_factory=list)
    summary: str = ""


def _build_strong_reason(item: OpportunityItem) -> tuple[str, dict]:
    """强势板块理由"""
    reason_dict = {
        "observation": f"{item.sector_name}板块情绪积极（{item.sentiment_score:.0f}分），5日动量{item.momentum_5d:+.1f}%，成交活跃",
        "analysis": f"情绪评分{item.sentiment_score:.0f}分，信号等级{item.signal_level}，资金持续流入，趋势向好",
        "action": f"趋势确认，可关注{item.sector_group}相关ETF，建议设置3%止损",
    }
    reason_str = f"{item.sector_name}情绪积极（{item.sentiment_score:.0f}分），5日动量{item.momentum_5d:+.1f}%，趋势向好"
    return reason_str, reason_dict


def _build_rebound_reason(item: OpportunityItem) -> tuple[str, dict]:
    """超跌反弹理由"""
    reason_dict = {
        "observation": f"{item.sector_name}板块情绪极度低迷（{item.sentiment_score:.0f}分），跌幅较大",
        "analysis": f"信号等级{item.signal_level}（恐慌），超卖信号明显，存在技术性反弹可能",
        "action": f"超跌反弹机会，建议小仓位试探，设置5%止损，不宜重仓",
    }
    reason_str = f"{item.sector_name}情绪极度低迷（{item.sentiment_score:.0f}分），可能存在超跌反弹机会"
    return reason_str, reason_dict


def _build_steady_reason(item: OpportunityItem) -> tuple[str, dict]:
    """稳健配置理由"""
    reason_dict = {
        "observation": f"{item.sector_name}板块情绪中性（{item.sentiment_score:.0f}分），波动较小",
        "analysis": f"信号等级{item.signal_level}（中性），多空力量均衡，无极端信号",
        "action": f"适合稳健配置，建议定投或分批建仓",
    }
    reason_str = f"{item.sector_name}情绪中性（{item.sentiment_score:.0f}分），适合稳健配置"
    return reason_str, reason_dict


def generate_recommendations(
    sector_data: list[dict],
    top_n: int = 5,
) -> RecommendationResult:
    """
    生成投资机会推荐

    Args:
        sector_data: 板块数据列表，每项包含:
            - sector_code, sector_name, sector_group
            - sentiment_score, sentiment_label, signal_level
            - momentum_5d, momentum_20d
            - strength_index, strength_rank
            - reason: {observation, analysis, action} (可选)
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
        signal_level = s.get("signal_level", "B")
        reason_data = s.get("reason", {})

        item = OpportunityItem(
            sector_code=s.get("sector_code", ""),
            sector_name=s.get("sector_name", ""),
            sector_group=s.get("sector_group", ""),
            sentiment_score=score,
            sentiment_label=label,
            signal_level=signal_level,
            momentum_5d=momentum_5d,
            momentum_20d=s.get("momentum_20d", 0.0),
            strength_index=strength,
            strength_rank=s.get("strength_rank", 0),
            opportunity_type="steady",
            opportunity_reason="",
            reason=reason_data if isinstance(reason_data, dict) else {},
        )

        # 强势板块：情绪分 > 60 且动量 > 0
        if score > 60 and momentum_5d > 0:
            item.opportunity_type = "strong"
            reason_str, reason_dict = _build_strong_reason(item)
            item.opportunity_reason = reason_str
            # 如果 sector_scorer 已提供结构化理由，优先使用
            if not item.reason:
                item.reason = reason_dict
            strong.append(item)

        # 超跌反弹：情绪分 < 35 且有极端标记
        elif score < 35 and label in ("fear", "extreme_fear"):
            item.opportunity_type = "rebound"
            reason_str, reason_dict = _build_rebound_reason(item)
            item.opportunity_reason = reason_str
            if not item.reason:
                item.reason = reason_dict
            rebound.append(item)

        # 稳健配置：情绪中性 40-60 且强度适中
        elif 40 <= score <= 60:
            item.opportunity_type = "steady"
            reason_str, reason_dict = _build_steady_reason(item)
            item.opportunity_reason = reason_str
            if not item.reason:
                item.reason = reason_dict
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


# ============================================================
# 风险警示生成
# ============================================================

@dataclass
class SectorWarningItem:
    """板块风险警示项"""
    sector_name: str
    sector_code: str
    sentiment_score: float
    momentum_5d: float
    warning_type: str  # "overheated" | "weak"
    signal_level: str = "B"
    reason: str = ""


def generate_warnings(
    sector_data: list[dict],
    max_warnings: int = 5,
) -> list[SectorWarningItem]:
    """
    生成板块风险警示

    规则：
    - 过热（overheated）：情绪分 > 75 且 5日动量 > 3%（贪婪+追涨）
    - 疲软（weak）：情绪分 < 25 且 5日动量 < -3%（恐慌+下跌）

    Args:
        sector_data: 与 generate_recommendations 相同的板块数据列表
        max_warnings: 最多返回的警示数量

    Returns:
        按严重度排序的风险警示列表
    """
    warnings: list[SectorWarningItem] = []

    for s in sector_data:
        score = s.get("sentiment_score", 50.0)
        momentum_5d = s.get("momentum_5d", 0.0)
        signal_level = s.get("signal_level", "B")
        sector_name = s.get("sector_name", "")

        # 过热板块：情绪分 > 75 且 5日动量 > 3%
        if score > 75 and momentum_5d > 3.0:
            warnings.append(SectorWarningItem(
                sector_name=sector_name,
                sector_code=s.get("sector_code", ""),
                sentiment_score=score,
                momentum_5d=momentum_5d,
                warning_type="overheated",
                signal_level=signal_level,
                reason=f"板块情绪过热（{score:.0f}分），5日涨幅{momentum_5d:+.1f}%，追涨风险高，注意回调",
            ))

        # 疲软板块：情绪分 < 25 且 5日动量 < -3%
        elif score < 25 and momentum_5d < -3.0:
            warnings.append(SectorWarningItem(
                sector_name=sector_name,
                sector_code=s.get("sector_code", ""),
                sentiment_score=score,
                momentum_5d=momentum_5d,
                warning_type="weak",
                signal_level=signal_level,
                reason=f"板块持续疲软（{score:.0f}分），5日跌幅{momentum_5d:+.1f}%，下行趋势明显",
            ))

    # 按严重度排序：过热优先（过热风险更大），同类型按情绪分极值排序
    type_order = {"overheated": 0, "weak": 1}
    warnings.sort(key=lambda w: (
        type_order.get(w.warning_type, 9),
        -abs(w.sentiment_score - 50),  # 越极端越靠前
    ))

    return warnings[:max_warnings]
