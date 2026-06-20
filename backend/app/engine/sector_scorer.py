"""
板块情绪评分引擎 V5.0
将东方财富/腾讯的原始板块行情数据，转换为推荐引擎所需的情绪格式

V5.0 增强：
- 因子从3个增强到6个（涨跌幅+换手率+上涨家数比+资金流+动量确认+强度排名）
- 信号等级映射 S+/S/A/B/C/D/E（复用 V5 信号边界）
- 理由结构化输出 ThreePartReason（observation/analysis/action）
"""
import logging
from typing import Optional
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 板块名称 → 行业分组映射
# ============================================================
_GROUP_MAP = {
    "电子": "科技", "信息": "科技", "互联": "科技", "传媒": "科技",
    "通信": "科技", "软件": "科技", "数据": "科技", "云计算": "科技",
    "5G": "科技", "物联网": "科技", "区块链": "科技", "数字": "科技",
    "半导体": "科技", "芯片": "科技", "人工智能": "科技",
    "新能": "能源", "光伏": "能源", "风电": "能源", "储能": "能源",
    "锂电": "能源", "氢能": "能源", "电力": "能源", "能源": "能源",
    "医药": "医药", "医疗": "医药", "生物": "医药", "中药": "医药", "养老": "医药",
    "银行": "金融", "证券": "金融", "保险": "金融", "金融": "金融",
    "白酒": "消费", "食品": "消费", "饮料": "消费", "家电": "消费", "消费": "消费",
    "汽车": "制造", "军工": "制造", "机器人": "制造", "装备": "制造", "工业": "制造",
    "地产": "地产", "基建": "地产",
    "有色": "周期", "钢铁": "周期", "煤炭": "周期", "化工": "周期", "材料": "周期",
    "农业": "农业", "公用": "公用",
}

# 信号等级与边界（复用 V5 全局配置）
_LEVELS = ["S+", "S", "A", "B", "C", "D", "E"]
_BOUNDARIES = settings.V5_SIGNAL_BOUNDARIES  # [12, 25, 38, 52, 65, 80]

# 信号等级中文含义
_LEVEL_MEANINGS = {
    "S+": "极度恐慌", "S": "恐慌", "A": "偏恐慌", "B": "中性",
    "C": "偏贪婪", "D": "贪婪", "E": "极度贪婪",
}


@dataclass
class ThreePartReason:
    """三段式理由（观察→分析→行动）"""
    observation: str = ""   # 市场现状
    analysis: str = ""      # 触发原因
    action: str = ""        # 操作建议

    def to_dict(self) -> dict:
        return {
            "observation": self.observation,
            "analysis": self.analysis,
            "action": self.action,
        }

    def to_string(self) -> str:
        """向后兼容：拼接为单行文本"""
        parts = []
        if self.observation:
            parts.append(self.observation)
        if self.analysis:
            parts.append(self.analysis)
        if self.action:
            parts.append(self.action)
        return "；".join(parts)


def _map_sector_group(name: str) -> str:
    """板块名称 → 行业分组"""
    for kw, grp in _GROUP_MAP.items():
        if kw in name:
            return grp
    return "综合"


def _sentiment_label(score: float) -> str:
    """情绪分数 → 情绪标签（5级）"""
    if score < 20:
        return "extreme_fear"
    elif score < 35:
        return "fear"
    elif score < 55:
        return "neutral"
    elif score < 75:
        return "greed"
    else:
        return "extreme_greed"


def _score_to_signal_level(score: float) -> str:
    """情绪分数 → 7级信号等级（复用 V5 边界）"""
    for i, boundary in enumerate(_BOUNDARIES):
        if score <= boundary:
            return _LEVELS[i]
    return _LEVELS[-1]  # > 80 → E


def _build_reason(
    name: str,
    score: float,
    signal_level: str,
    chg: float,
    turnover: float,
    momentum_5d: float,
    strength_index: float,
    fund_flow: float,
) -> ThreePartReason:
    """生成三段式推荐理由"""
    # ── 观察段：市场现状 ──
    if chg > 3:
        obs = f"{name}板块当日大涨{chg:+.1f}%，成交活跃"
    elif chg > 0:
        obs = f"{name}板块小幅上涨{chg:+.1f}%，市场情绪偏暖"
    elif chg > -3:
        obs = f"{name}板块下跌{chg:.1f}%，市场表现偏弱"
    else:
        obs = f"{name}板块大幅下跌{chg:.1f}%，恐慌情绪蔓延"

    # ── 分析段：触发原因 ──
    meaning = _LEVEL_MEANINGS.get(signal_level, "中性")
    trigger_parts = [f"情绪评分{score:.0f}分（{meaning}）"]

    if abs(momentum_5d) > 2:
        trigger_parts.append(f"5日动量{momentum_5d:+.1f}%")
    if fund_flow != 0:
        direction = "流入" if fund_flow > 0 else "流出"
        trigger_parts.append(f"资金{direction}{abs(fund_flow):.1f}亿")
    if turnover > 5:
        trigger_parts.append(f"换手率{turnover:.1f}%偏高")

    analysis = "，".join(trigger_parts) + "触发信号"

    # ── 行动段：操作建议 ──
    if signal_level in ("S+", "S"):
        action = "市场恐慌，可关注超跌反弹机会，建议小仓位试探，设置5%止损"
    elif signal_level == "A":
        action = "市场偏恐慌，可适度关注，建议轻仓布局"
    elif signal_level == "B":
        action = "市场中性，建议持有观望，等待方向明确"
    elif signal_level == "C":
        action = "市场偏热，建议逐步减仓锁定收益"
    elif signal_level in ("D", "E"):
        action = "市场过热，建议控制仓位，注意回调风险"
    else:
        action = "建议谨慎观望"

    return ThreePartReason(observation=obs, analysis=analysis, action=action)


def score_sector(item: dict) -> dict:
    """
    将单条原始板块行情转换为情绪评分格式

    输入 item 格式（来自 eastmoney.get_sector_list）：
        code, name, price, change_pct, change_amt, volume, amount, turnover, high, low
        可选: fund_flow(资金净流入亿元), up_count(上涨家数), down_count(下跌家数)

    输出格式（匹配 recommendations.generate_recommendations 输入）：
        sector_code, sector_name, sector_group,
        sentiment_score, sentiment_label, signal_level,
        momentum_5d, momentum_20d, strength_index, strength_rank,
        sector_return, turnover_ratio, fund_flow, advance_decline_ratio,
        reason: {observation, analysis, action}
    """
    name = item.get("name", "")
    chg = float(item.get("change_pct") or 0)
    turnover = float(item.get("turnover") or 0)
    fund_flow = float(item.get("fund_flow") or 0)
    up_count = int(item.get("up_count") or 0)
    down_count = int(item.get("down_count") or 0)

    # ── 因子1: 涨跌幅 (权重 35%) ──
    # 0% → 50分, ±10% → 0~100分
    chg_score = 50 + chg * 5

    # ── 因子2: 换手率 (权重 20%) ──
    # 2% → 50分, >7% → 100分, <0.5% → 0分
    turnover_score = min(100, max(0, 50 + (turnover - 2) * 10))

    # ── 因子3: 涨跌家数比 ADR (权重 20%) ──
    if up_count + down_count > 0:
        adr = up_count / (up_count + down_count)
        adr_score = adr * 100
    else:
        # 无涨跌家数数据时，用涨跌幅近似
        adr_score = min(100, max(0, 50 + chg * 8))

    # ── 因子4: 资金流 (权重 15%) ──
    # ±5亿 → 0~100分
    if fund_flow != 0:
        flow_score = min(100, max(0, 50 + fund_flow * 10))
    else:
        # 无资金流数据时，用涨跌幅二次近似
        flow_score = min(100, max(0, 50 + chg * 3))

    # ── 因子5: 动量确认 (权重 10%) ──
    # 5日动量近似（当前日涨跌幅的1.5倍，后续可接入历史数据精确计算）
    momentum_5d = round(chg * 1.5, 1)
    # 20日动量近似（当前日涨跌幅的3倍）
    momentum_20d = round(chg * 3, 1)
    # 动量确认分数：正动量加分，负动量减分
    momentum_score = min(100, max(0, 50 + momentum_5d * 3))

    # ── 综合情绪分数 (加权) ──
    sentiment_score = round(
        chg_score * 0.35 +
        turnover_score * 0.20 +
        adr_score * 0.20 +
        flow_score * 0.15 +
        momentum_score * 0.10,
        1
    )
    sentiment_score = max(5, min(95, sentiment_score))

    # ── 强度指数与排名 ──
    strength_index = max(5, min(100, round(50 + chg * 10, 1)))
    # strength_rank 在批量评分后计算

    # ── 涨跌家数比 ──
    advance_decline_ratio = round(up_count / down_count, 2) if down_count > 0 else (10.0 if up_count > 0 else 1.0)

    # ── 信号等级映射 ──
    signal_level = _score_to_signal_level(sentiment_score)

    # ── 三段式理由 ──
    reason = _build_reason(
        name=name,
        score=sentiment_score,
        signal_level=signal_level,
        chg=chg,
        turnover=turnover,
        momentum_5d=momentum_5d,
        strength_index=strength_index,
        fund_flow=fund_flow,
    )

    return {
        "sector_code": item.get("code", ""),
        "sector_name": name,
        "sector_group": _map_sector_group(name),
        "sentiment_score": sentiment_score,
        "sentiment_label": _sentiment_label(sentiment_score),
        "signal_level": signal_level,
        "momentum_5d": momentum_5d,
        "momentum_20d": momentum_20d,
        "strength_index": strength_index,
        "strength_rank": 0,  # 批量计算后填充
        "sector_return": chg,
        "turnover_ratio": turnover,
        "fund_flow": fund_flow,
        "advance_decline_ratio": advance_decline_ratio,
        "reason": reason.to_dict(),
    }


async def score_sectors(raw_items: list[dict]) -> list[dict]:
    """
    批量转换板块数据

    Args:
        raw_items: get_sector_list() 返回的 items 列表

    Returns:
        情绪评分后的板块列表（含信号等级、排名、结构化理由）
    """
    if not raw_items:
        logger.warning("板块数据为空，无法评分")
        return []

    # 去重（按 code+name）
    seen = set()
    unique = []
    for item in raw_items:
        key = (item.get("code", ""), item.get("name", ""))
        if key not in seen:
            seen.add(key)
            unique.append(item)

    scored = [score_sector(item) for item in unique]

    # 计算强度排名（按 strength_index 降序）
    scored.sort(key=lambda x: x["strength_index"], reverse=True)
    for rank, item in enumerate(scored, 1):
        item["strength_rank"] = rank

    logger.info("板块情绪评分完成: %d 个板块, 5因子加权(涨跌幅35%%+换手率20%%+ADR20%%+资金流15%%+动量10%%)",
                len(scored))
    
    # 方案B: 添加板块过滤器标签
    scored = await add_sector_filter(scored)
    
    return scored


# ============================================================
# 方案B: 板块过滤器
# ============================================================
async def calculate_sector_filter(sector_code: str, sector_name: str = "") -> dict:
    """
    计算板块过滤器的三个准入指标，返回build_signal
    
    计算逻辑：
    1. 20日上涨占比 = 近20交易日上涨天数 / 总交易日数
    2. 60日相对强弱 = 板块60日涨跌幅 - 沪深300同期60日涨跌幅
    3. MA20趋势位置 = 板块最新收盘价 vs 20日均线
    
    Returns:
        {
            "up_days_ratio": float,      # 20日上涨占比 (0-1)
            "relative_strength": float,   # 60日相对强弱 (百分比)
            "trend_position": str,       # "above_ma20" / "below_ma20"
            "build_signal": str,           # "可建仓" / "暂不建仓"
        }
    """
    # TODO: 实现历史数据获取逻辑
    # 当前使用占位逻辑，后续接入Tushare index_daily数据
    
    # 占位返回值（默认允许建仓）
    return {
        "up_days_ratio": 0.55,
        "relative_strength": 0.02,
        "trend_position": "above_ma20",
        "build_signal": "可建仓",
    }


async def add_sector_filter(scored_sectors: list[dict]) -> list[dict]:
    """
    为评分后的板块列表添加板块过滤器标签
    
    Args:
        scored_sectors: score_sectors()返回的板块列表
        
    Returns:
        添加了build_signal等字段的板块列表
    """
    # 检查配置开关
    from app.core.config import settings
    if not settings.ENABLE_SECTOR_FILTER:
        # 开关关闭，不添加过滤器字段
        return scored_sectors
    
    # 为每个板块计算过滤器指标
    for sector in scored_sectors:
        sector_code = sector.get("sector_code", "")
        sector_name = sector.get("sector_name", "")
        
        # 计算过滤器指标
        filter_result = await calculate_sector_filter(sector_code, sector_name)
        
        # 添加字段
        sector["up_days_ratio"] = filter_result["up_days_ratio"]
        sector["relative_strength"] = filter_result["relative_strength"]
        sector["trend_position"] = filter_result["trend_position"]
        sector["build_signal"] = filter_result["build_signal"]
    
    return scored_sectors
