"""
板块情绪评分引擎 V5.0
将东方财富/腾讯的原始板块行情数据，转换为推荐引擎所需的情绪格式

输入：eastmoney.get_sector_list() 返回的 raw items
输出：recommendations.generate_recommendations() 所需的 dict list
"""
import logging
from typing import Optional

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


def _map_sector_group(name: str) -> str:
    """板块名称 → 行业分组"""
    for kw, grp in _GROUP_MAP.items():
        if kw in name:
            return grp
    return "综合"


def _sentiment_label(score: float) -> str:
    """情绪分数 → 情绪标签"""
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


def score_sector(item: dict) -> dict:
    """
    将单条原始板块行情转换为情绪评分格式

    输入 item 格式（来自 eastmoney.get_sector_list）：
        code, name, price, change_pct, change_amt, volume, amount, turnover, high, low

    输出格式（匹配 recommendations.generate_recommendations 输入）：
        sector_code, sector_name, sector_group,
        sentiment_score, sentiment_label,
        momentum_5d, momentum_20d, strength_index,
        sector_return, turnover_ratio
    """
    name = item.get("name", "")
    chg = float(item.get("change_pct") or 0)
    turnover = float(item.get("turnover") or 0)

    # ── 情绪分数 ──
    # 涨跌幅权重60%，换手率权重40%
    # 涨跌幅映射：0% → 50分, ±10% → 0~100分
    chg_score = 50 + chg * 5
    # 换手率映射：2% → 50分, >7% → 100分, <0.5% → 0分
    turnover_score = min(100, max(0, 50 + (turnover - 2) * 10))
    sentiment_score = round(chg_score * 0.6 + turnover_score * 0.4, 1)
    sentiment_score = max(5, min(95, sentiment_score))

    # ── 动量 ──
    # 5日动量近似（当前日涨跌幅的1.5倍，后续可接入历史数据精确计算）
    momentum_5d = round(chg * 1.5, 1)
    # 20日动量近似（当前日涨跌幅的3倍）
    momentum_20d = round(chg * 3, 1)

    # ── 强度指数 ──
    strength_index = max(5, min(100, round(50 + chg * 10, 1)))

    return {
        "sector_code": item.get("code", ""),
        "sector_name": name,
        "sector_group": _map_sector_group(name),
        "sentiment_score": sentiment_score,
        "sentiment_label": _sentiment_label(sentiment_score),
        "momentum_5d": momentum_5d,
        "momentum_20d": momentum_20d,
        "strength_index": strength_index,
        "sector_return": chg,
        "turnover_ratio": turnover,
        "fund_flow": 0.0,
    }


async def score_sectors(raw_items: list[dict]) -> list[dict]:
    """
    批量转换板块数据

    Args:
        raw_items: get_sector_list() 返回的 items 列表

    Returns:
        情绪评分后的板块列表
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
    logger.info("板块情绪评分完成: %d 个板块", len(scored))
    return scored
