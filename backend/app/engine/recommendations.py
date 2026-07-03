"""
机会雷达推荐引擎 V5.0
基于板块情绪评分和双轨制过滤器，推荐投资机会

V5.0 架构:
  - 调用 sector_scorer.score_sectors() 获取所有板块评分
  - Gate3准入过滤: E信号 / 置信度≤1星 / excluded轨道 → 不进入推荐池
  - 按 track 分组: contrarian(逆向机会) > trend_follow(趋势机会) > excluded(不推荐)
  - contrarian 组: 按 score 升序 (越恐惧越有机会), 最多3个
  - trend_follow 组: 按 score 降序 (越贪婪趋势越强), 最多5个
  - 总推荐数 ≤ 8

向后兼容:
  - 保留 OpportunityItem / RecommendationResult / generate_warnings 接口
  - 旧版 generate_recommendations 接口保留, 内部调用 V5 版
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 申万一级行业代码 → 中文名称映射 (31个)
# ============================================================

SW_INDUSTRY_NAMES = {
    "801010": "农林牧渔",
    "801030": "基础化工",
    "801040": "钢铁",
    "801050": "有色金属",
    "801080": "电子",
    "801110": "家用电器",
    "801120": "食品饮料",
    "801130": "纺织服饰",
    "801140": "轻工制造",
    "801150": "医药生物",
    "801160": "公用事业",
    "801170": "交通运输",
    "801180": "房地产",
    "801200": "商贸零售",
    "801210": "社会服务",
    "801230": "综合",
    "801710": "建筑材料",
    "801720": "建筑装饰",
    "801730": "电力设备",
    "801740": "国防军工",
    "801750": "计算机",
    "801760": "传媒",
    "801770": "通信",
    "801780": "银行",
    "801790": "非银金融",
    "801880": "汽车",
    "801890": "机械设备",
    "801950": "煤炭",
    "801960": "石油石化",
    "801970": "环保",
    "801980": "美容护理",
}


# ============================================================
# 数据结构
# ============================================================

@dataclass
class OpportunityItem:
    """机会推荐项 (V5)"""
    sector_code: str
    sector_name: str
    sector_group: str
    sentiment_score: float
    sentiment_label: str
    signal_level: str = "B"
    confidence_stars: int = 0
    track: str = "excluded"            # trend_follow / contrarian / excluded
    momentum_5d: float = 0.0
    momentum_20d: float = 0.0
    strength_index: float = 50.0
    strength_rank: int = 0
    opportunity_type: str = "steady"   # 兼容旧字段: strong / rebound / steady / contrarian / trend_follow
    opportunity_reason: str = ""
    rank: int = 0                      # 推荐排名 (1=最佳)
    # V5 结构化理由
    reason: dict = field(default_factory=dict)
    # V5 因子明细
    factor_scores: dict = field(default_factory=dict)
    factor_completeness: float = 1.0
    cold_start: bool = False
    recommended_funds: list[str] = field(default_factory=list)


@dataclass
class RecommendationResult:
    """机会雷达结果 (V5)"""
    # V5 双轨制分组
    contrarian_opportunities: list[OpportunityItem] = field(default_factory=list)   # 逆向机会
    trend_follow_opportunities: list[OpportunityItem] = field(default_factory=list) # 趋势机会
    all_recommendations: list[OpportunityItem] = field(default_factory=list)        # 全部推荐 (contrarian + trend_follow)
    # 向后兼容字段 (旧版 API)
    strong_sectors: list[OpportunityItem] = field(default_factory=list)
    rebound_opportunities: list[OpportunityItem] = field(default_factory=list)
    steady_choices: list[OpportunityItem] = field(default_factory=list)
    top_picks: list[OpportunityItem] = field(default_factory=list)
    summary: str = ""
    # V5 新增
    total_count: int = 0
    contrarian_count: int = 0
    trend_follow_count: int = 0
    excluded_count: int = 0


# ============================================================
# V5 推荐引擎核心
# ============================================================

# 推荐数量上限
MAX_CONTRARIAN = 3     # 逆向机会精选
MAX_TREND_FOLLOW = 5   # 趋势机会
MAX_TOTAL = 8          # 总推荐上限


def generate_recommendations_v5(
    sector_data: list[dict],
    max_contrarian: int = MAX_CONTRARIAN,
    max_trend_follow: int = MAX_TREND_FOLLOW,
) -> RecommendationResult:
    """
    V5 推荐引擎 — 双轨制推荐

    Args:
        sector_data: sector_scorer.score_sectors() 返回的板块评分列表
        max_contrarian: 逆向轨道最大推荐数
        max_trend_follow: 正常轨道最大推荐数

    Returns:
        RecommendationResult
    """
    contrarian: list[OpportunityItem] = []
    trend_follow: list[OpportunityItem] = []
    excluded_count = 0

    for s in sector_data:
        track = s.get("track", "excluded")
        signal_level = s.get("signal_level", "B")
        confidence_stars = s.get("confidence_stars", 0)
        item = _dict_to_opportunity_item(s)

        # Gate3准入排除：E信号 / 置信度≤1 / excluded轨道 → 不进入推荐池
        if signal_level == "E" or confidence_stars <= 1 or track == "excluded":
            excluded_count += 1
        elif track == "contrarian":
            item.opportunity_type = "contrarian"
            contrarian.append(item)
        elif track == "trend_follow":
            item.opportunity_type = "trend_follow"
            trend_follow.append(item)
        else:
            excluded_count += 1

    # 逆向轨道: 按 score 升序 (越恐惧越有机会)
    contrarian.sort(key=lambda x: x.sentiment_score)
    contrarian = contrarian[:max_contrarian]

    # 正常轨道: 按 score 降序 (越贪婪趋势越强)
    trend_follow.sort(key=lambda x: x.sentiment_score, reverse=True)
    trend_follow = trend_follow[:max_trend_follow]

    # 总数限制
    if len(contrarian) + len(trend_follow) > MAX_TOTAL:
        # 优先保留 contrarian, 削减 trend_follow
        remaining = MAX_TOTAL - len(contrarian)
        trend_follow = trend_follow[:max(0, remaining)]

    # 合并推荐列表 (contrarian 优先)
    all_recs = contrarian + trend_follow
    for rank, item in enumerate(all_recs, 1):
        item.rank = rank

    # 向后兼容: 映射到旧版字段
    strong_sectors = [item for item in trend_follow if item.sentiment_score > 55]
    rebound_opportunities = list(contrarian)  # 逆向 = 超跌反弹
    steady_choices = [item for item in trend_follow if 40 <= item.sentiment_score <= 60]
    top_picks = all_recs[:5]

    # 生成总结
    summary = _build_summary(contrarian, trend_follow, excluded_count)

    result = RecommendationResult(
        contrarian_opportunities=contrarian,
        trend_follow_opportunities=trend_follow,
        all_recommendations=all_recs,
        strong_sectors=strong_sectors,
        rebound_opportunities=rebound_opportunities,
        steady_choices=steady_choices,
        top_picks=top_picks,
        summary=summary,
        total_count=len(all_recs),
        contrarian_count=len(contrarian),
        trend_follow_count=len(trend_follow),
        excluded_count=excluded_count,
    )

    logger.info(
        f"V5推荐引擎: contrarian={len(contrarian)}, trend_follow={len(trend_follow)}, "
        f"excluded={excluded_count}, total={len(all_recs)}"
    )

    return result


def _dict_to_opportunity_item(s: dict) -> OpportunityItem:
    """将 sector_scorer 输出的 dict 转换为 OpportunityItem"""
    sector_code = s.get("sector_code", "")
    sector_name = s.get("sector_name", "")

    # 如果名称为空, 尝试从映射表查找
    if not sector_name and sector_code:
        sector_name = SW_INDUSTRY_NAMES.get(sector_code, sector_code)

    return OpportunityItem(
        sector_code=sector_code,
        sector_name=sector_name,
        sector_group=s.get("sector_group", ""),
        sentiment_score=s.get("sentiment_score", 50.0),
        sentiment_label=s.get("sentiment_label", "中性"),
        signal_level=s.get("signal_level", "B"),
        confidence_stars=s.get("confidence_stars", 0),
        track=s.get("track", "excluded"),
        momentum_5d=s.get("momentum_5d", 0.0),
        momentum_20d=s.get("momentum_20d", 0.0),
        strength_index=s.get("strength_index", 50.0),
        strength_rank=s.get("strength_rank", 0),
        reason=s.get("reason", {}) if isinstance(s.get("reason"), dict) else {},
        factor_scores=s.get("factor_scores", {}) if isinstance(s.get("factor_scores"), dict) else {},
        factor_completeness=s.get("factor_completeness", 1.0),
        cold_start=s.get("cold_start", False),
    )


def _build_summary(contrarian: list[OpportunityItem], trend_follow: list[OpportunityItem],
                   excluded_count: int) -> str:
    """生成推荐总结"""
    parts = []

    if contrarian:
        names = ", ".join(s.sector_name for s in contrarian[:3])
        parts.append(f"逆向机会: {names} (极端恐惧+底背离)")

    if trend_follow:
        names = ", ".join(s.sector_name for s in trend_follow[:3])
        parts.append(f"趋势机会: {names} (趋势向上+信号确认)")

    if not contrarian and not trend_follow:
        if excluded_count > 0:
            return f"当前{excluded_count}个板块均未通过双轨制过滤器，无推荐机会，建议观望"
        return "当前市场无明显结构性机会，建议观望为主"

    return "；".join(parts)


# ============================================================
# 向后兼容: 旧版 generate_recommendations 接口
# ============================================================

def generate_recommendations(
    sector_data: list[dict],
    top_n: int = 5,
) -> RecommendationResult:
    """
    生成投资机会推荐 (向后兼容接口)

    V5 版本内部调用 generate_recommendations_v5, 然后映射到旧版字段:
    - strong_sectors: trend_follow 中 score > 55 的板块
    - rebound_opportunities: contrarian 轨道的板块
    - steady_choices: trend_follow 中 score 40-60 的板块
    - top_picks: all_recommendations 前5

    Args:
        sector_data: 板块数据列表 (sector_scorer.score_sectors() 输出)
        top_n: 每类推荐数量 (V5中由 max_contrarian/max_trend_follow 控制, 此参数保留兼容)

    Returns:
        RecommendationResult
    """
    # 检查数据是否包含 V5 字段 (track)
    has_v5_fields = any(s.get("track") for s in sector_data)

    if has_v5_fields:
        # V5 模式: 使用双轨制推荐
        return generate_recommendations_v5(
            sector_data,
            max_contrarian=min(top_n, MAX_CONTRARIAN),
            max_trend_follow=min(top_n, MAX_TREND_FOLLOW),
        )

    # 旧模式: 数据不包含 track 字段, 回退到旧逻辑
    return _generate_recommendations_legacy(sector_data, top_n)


def _generate_recommendations_legacy(
    sector_data: list[dict],
    top_n: int = 5,
) -> RecommendationResult:
    """旧版推荐逻辑 (无 track 字段时回退)"""
    strong: list[OpportunityItem] = []
    rebound: list[OpportunityItem] = []
    steady: list[OpportunityItem] = []

    for s in sector_data:
        score = s.get("sentiment_score", 50.0)
        momentum_5d = s.get("momentum_5d", 0.0)
        label = s.get("sentiment_label", "neutral")
        signal_level = s.get("signal_level", "B")

        item = _dict_to_opportunity_item(s)
        item.opportunity_type = "steady"

        if score > 60 and momentum_5d > 0:
            item.opportunity_type = "strong"
            strong.append(item)
        elif score < 35 and label in ("fear", "extreme_fear", "恐惧", "极度恐惧"):
            item.opportunity_type = "rebound"
            rebound.append(item)
        elif 40 <= score <= 60:
            item.opportunity_type = "steady"
            steady.append(item)

    strong.sort(key=lambda x: x.sentiment_score + x.momentum_5d, reverse=True)
    rebound.sort(key=lambda x: x.sentiment_score)
    steady.sort(key=lambda x: abs(x.sentiment_score - 50))

    strong = strong[:top_n]
    rebound = rebound[:top_n]
    steady = steady[:top_n]
    top_picks = strong[:2] + rebound[:2] + steady[:1]
    for rank, item in enumerate(top_picks, 1):
        item.rank = rank

    parts = []
    if strong:
        parts.append(f"强势板块关注: {', '.join(s.sector_name for s in strong[:3])}")
    if rebound:
        parts.append(f"超跌机会关注: {', '.join(r.sector_name for r in rebound[:3])}")
    if steady:
        parts.append(f"稳健配置关注: {', '.join(s.sector_name for s in steady[:2])}")
    summary = "；".join(parts) if parts else "当前市场无明显结构性机会，建议观望为主"

    return RecommendationResult(
        contrarian_opportunities=rebound,
        trend_follow_opportunities=strong + steady,
        all_recommendations=top_picks,
        strong_sectors=strong,
        rebound_opportunities=rebound,
        steady_choices=steady,
        top_picks=top_picks,
        summary=summary,
        total_count=len(top_picks),
        contrarian_count=len(rebound),
        trend_follow_count=len(strong) + len(steady),
        excluded_count=0,
    )


# ============================================================
# 风险警示生成 (保留原有逻辑, 适配V5字段)
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

    规则:
    - 过热 (overheated): 情绪分 > 75 且 5日动量 > 3% (贪婪+追涨)
    - 疲软 (weak): 情绪分 < 25 且 5日动量 < -3% (恐惧+下跌)

    Args:
        sector_data: 板块数据列表
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
        sector_code = s.get("sector_code", "")

        # 过热板块
        if score > 75 and momentum_5d > 3.0:
            warnings.append(SectorWarningItem(
                sector_name=sector_name,
                sector_code=sector_code,
                sentiment_score=score,
                momentum_5d=momentum_5d,
                warning_type="overheated",
                signal_level=signal_level,
                reason=f"板块情绪过热（{score:.0f}分），5日涨幅{momentum_5d:+.1f}%，追涨风险高，注意回调",
            ))
        # 疲软板块
        elif score < 25 and momentum_5d < -3.0:
            warnings.append(SectorWarningItem(
                sector_name=sector_name,
                sector_code=sector_code,
                sentiment_score=score,
                momentum_5d=momentum_5d,
                warning_type="weak",
                signal_level=signal_level,
                reason=f"板块持续疲软（{score:.0f}分），5日跌幅{momentum_5d:+.1f}%，下行趋势明显",
            ))

    type_order = {"overheated": 0, "weak": 1}
    warnings.sort(key=lambda w: (
        type_order.get(w.warning_type, 9),
        -abs(w.sentiment_score - 50),
    ))

    return warnings[:max_warnings]


# ============================================================
# 便捷函数: 一步到位生成推荐
# ============================================================

async def get_sector_recommendations() -> RecommendationResult:
    """
    一站式调用: 获取板块评分 → 生成推荐

    内部调用 sector_scorer.score_sectors() + generate_recommendations_v5()
    适合 API 端点直接调用

    Returns:
        RecommendationResult
    """
    from app.engine.sector_scorer import score_sectors

    sector_data = await score_sectors()
    if not sector_data:
        return RecommendationResult(summary="板块数据获取失败，请稍后重试")

    return generate_recommendations_v5(sector_data)
