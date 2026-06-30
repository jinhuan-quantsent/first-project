"""
板块情绪评分引擎 V5.0
将东方财富/腾讯的原始板块行情数据，转换为推荐引擎所需的情绪格式

V5.0 增强：
- 因子从3个增强到5个（涨跌幅+换手率+上涨家数比+资金流+动量确认）
- 信号等级映射 S+/S/A/B/C/D/E（复用 V5 信号边界）
- 理由结构化输出 ThreePartReason（observation/analysis/action）
- 方案B：板块过滤器（calculate_sector_filter, add_sector_filter）
"""
import logging
from typing import Optional
from dataclasses import dataclass, field

from app.core.config import settings
from app.engine.data_fetcher import fetch_sector_historical_data, fetch_fund_nav_history, fetch_index_hist

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
    """情绪分数 → 情绪标签（5级，中文）"""
    if score < 20:
        return "极度恐慌"
    elif score < 35:
        return "恐慌"
    elif score < 55:
        return "中性"
    elif score < 75:
        return "贪婪"
    else:
        return "极度贪婪"


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
    # 上涨家数/下跌家数，如果下跌家数为0，说明全线上涨，返回100.0（表示极端看涨）
    if down_count > 0:
        advance_decline_ratio = round(up_count / down_count, 2)
    elif up_count > 0:
        # 全线上涨，使用一个较大的值表示
        advance_decline_ratio = 100.0
    else:
        # 涨跌家数都为0，返回1.0（中性）
        advance_decline_ratio = 1.0

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
    return scored


# ── 方案B：板块过滤器 ────────────────────────────────────────────────────────────────

def calculate_sector_filter(sector_code: str, date: str = None) -> dict:
    """
    计算板块过滤器信号（方案B核心函数）
    
    依赖历史数据，计算三个维度：
    1. 20日上涨占比（市场广度）：up_days_ratio ≥ 0.5 → 通过
    2. 60日相对强弱（相对沪深300）：relative_strength ≥ -0.03 → 通过  
    3. MA20趋势位置：price > MA20 → 上升趋势
    
    返回：{
        "up_days_ratio": float,      # 20日上涨占比 (0-1)
        "relative_strength": float,  # 60日相对强弱（超额收益）
        "trend_position": str,       # 趋势位置（"上升" / "下降" / "震荡"）
        "build_signal": str          # 建仓信号（"适合建仓" / "谨慎建仓" / "暂不建仓"）
    }
    """
    try:
        # 获取20日历史数据
        history_20d = fetch_sector_historical_data(sector_code, 20)
        
        if not history_20d or len(history_20d) < 20:
            logger.warning(f"历史数据不足: {sector_code}, 仅有{len(history_20d) if history_20d else 0}条")
            return {
                "up_days_ratio": 0.0,
                "relative_strength": 0.0,
                "trend_position": "未知",
                "build_signal": "暂不建仓"  # 数据不足时保守处理
            }
        
        # 计算20日上涨占比
        up_days = sum(1 for d in history_20d if d.get("change_pct", 0) > 0)
        up_days_ratio = up_days / len(history_20d)
        
        # 计算MA20趋势位置（三维度判断规则）
        prices = [d.get("close", 0) for d in history_20d]
        current_price = prices[-1] if prices else 0
        
        # 需要至少20个价格点才能计算MA20
        if len(prices) >= 20:
            ma20 = sum(prices[-20:]) / 20
        else:
            ma20 = sum(prices) / len(prices) if prices else 0
        
        # ===== 三维度震荡判断规则 =====
        # 维度1：区间振幅约束（近20日收盘价累计涨跌幅绝对值 ≤ 5%）
        if len(prices) >= 20:
            amplitude_20d = abs((prices[-1] - prices[0]) / prices[0]) if prices[0] > 0 else 0
            dimension1_shock = amplitude_20d <= 0.05  # ≤ 5%
        else:
            dimension1_shock = False
        
        # 维度2：均线穿越频率（近20日收盘价穿越MA20次数 ≥ 3次）
        if len(prices) >= 20:
            crossings = 0
            ma20_series = []
            # 计算MA20序列（需要至少20个数据点）
            for i in range(19, len(prices)):
                ma20_i = sum(prices[i-19:i+1]) / 20
                ma20_series.append(ma20_i)
            
            # 统计穿越次数
            for i in range(1, len(ma20_series)):
                if (prices[19+i-1] <= ma20_series[i-1] and prices[19+i] > ma20_series[i]) or \
                   (prices[19+i-1] >= ma20_series[i-1] and prices[19+i] < ma20_series[i]):
                    crossings += 1
            
            dimension2_shock = crossings >= 3  # ≥ 3次
        else:
            dimension2_shock = False
        
        # 维度3：均线斜率约束（近10日MA20均线斜率绝对值 ≤ 0.3%）
        if len(prices) >= 30:  # 需要足够数据计算MA20序列的斜率
            # 计算近10日的MA20序列
            ma20_recent = []
            for i in range(len(prices) - 10, len(prices)):
                if i >= 19:  # 第20个数据点才能计算第一个MA20
                    ma20_i = sum(prices[i-19:i+1]) / 20
                    ma20_recent.append(ma20_i)
            
            if len(ma20_recent) >= 2:
                # 计算MA20斜率（最近一日相对10日前的变化率）
                ma20_slope = (ma20_recent[-1] - ma20_recent[0]) / ma20_recent[0] if ma20_recent[0] > 0 else 0
                dimension3_shock = abs(ma20_slope) <= 0.003  # ≤ 0.3%
            else:
                dimension3_shock = False
        else:
            dimension3_shock = False
        
        # 综合判断：满足2项及以上判定为震荡
        shock_score = sum([dimension1_shock, dimension2_shock, dimension3_shock])
        
        if shock_score >= 2:
            trend_position = "震荡"
        else:
            # 非震荡情况下判断上升/下降趋势
            if ma20 > 0:
                price_vs_ma20 = (current_price - ma20) / ma20
            else:
                price_vs_ma20 = 0
            
            # 计算短期趋势（最近5日涨跌幅）
            if len(prices) >= 5:
                short_trend = (prices[-1] - prices[-5]) / prices[-5] if prices[-5] > 0 else 0
            else:
                short_trend = 0
            
            # 趋势判断
            if current_price > ma20 and short_trend > 0:
                trend_position = "上升"
            elif current_price < ma20 and short_trend < 0:
                trend_position = "下降"
            else:
                # 不明确的情况，根据价格位置判断
                trend_position = "上升" if current_price > ma20 else "下降"
        
        # 记录调试信息
        logger.debug(f"震荡判断: 维度1(振幅≤5%)={dimension1_shock}, 维度2(穿越≥3次)={dimension2_shock}, 维度3(斜率≤0.3%)={dimension3_shock}, 得分={shock_score}, 结果={trend_position}")
        
        # 计算60日相对强弱（相对沪深300的超额收益）
        history_60d = fetch_sector_historical_data(sector_code, 60)
        if history_60d and len(history_60d) >= 2:
            start_price = history_60d[0].get("close", 0)
            end_price = history_60d[-1].get("close", 0)
            sector_change = (end_price - start_price) / start_price if start_price > 0 else 0
        else:
            sector_change = 0
        
        # 获取沪深300真实涨跌幅
        hs300_hist = fetch_index_hist("000300", 60)
        if hs300_hist and len(hs300_hist) >= 2:
            hs300_start = hs300_hist[0].get("close", 0)
            hs300_end = hs300_hist[-1].get("close", 0)
            hs300_change = (hs300_end - hs300_start) / hs300_start if hs300_start > 0 else 0
        else:
            # 如果获取失败，使用保守估计
            logger.warning("获取沪深300历史数据失败，使用保守估计")
            hs300_change = 0.0
        
        relative_strength = sector_change - hs300_change
        logger.info(f"相对强弱计算: 板块涨跌幅={sector_change:.3f}, 沪深300涨跌幅={hs300_change:.3f}, 相对强弱={relative_strength:.3f}")
        
        # 生成建仓信号
        config = settings
        threshold_up = config.SECTOR_FILTER_UP_DAYS_RATIO_THRESHOLD  # 0.5
        threshold_rs = config.SECTOR_FILTER_RELATIVE_STRENGTH_THRESHOLD  # -0.03
        
        if up_days_ratio >= threshold_up and relative_strength >= threshold_rs and trend_position == "上升":
            build_signal = "适合建仓"
        elif up_days_ratio >= threshold_up * 0.8 or relative_strength >= threshold_rs:
            build_signal = "谨慎建仓"
        else:
            build_signal = "暂不建仓"
        
        logger.info(f"板块过滤器计算完成: {sector_code}, up_ratio={up_days_ratio:.2f}, rs={relative_strength:.3f}, trend={trend_position}, signal={build_signal}")
        
        return {
            "up_days_ratio": round(up_days_ratio, 2),
            "relative_strength": round(relative_strength, 3),
            "trend_position": trend_position,
            "build_signal": build_signal
        }
        
    except Exception as e:
        logger.error(f"板块过滤器计算失败: {sector_code}, error={e}")
        return {
            "up_days_ratio": 0.0,
            "relative_strength": 0.0,
            "trend_position": "未知",
            "build_signal": "暂不建仓"  # 失败时保守处理
        }


def add_sector_filter(sectors: list[dict]) -> list[dict]:
    """
    为板块列表添加板块过滤器信号
    
    Args:
        sectors: 板块列表（已评分）
        
    Returns:
        添加了build_signal字段的板块列表
    """
    if not sectors:
        return sectors
    
    # 如果方案B未启用，跳过
    if not settings.ENABLE_SECTOR_FILTER:
        logger.info("方案B（板块过滤器）未启用，跳过")
        return sectors
    
    for sector in sectors:
        sector_code = sector.get("sector_code", "")
        if not sector_code:
            continue
        
        # 计算板块过滤器信号
        filter_result = calculate_sector_filter(sector_code)
        
        # 添加build_signal字段
        sector["build_signal"] = filter_result.get("build_signal", "暂不建仓")
        sector["trend_position"] = filter_result.get("trend_position", "未知")
        
        logger.debug(f"板块 {sector_code} 过滤器信号: {sector['build_signal']}")
    
    logger.info(f"板块过滤器信号添加完成: {len(sectors)} 个板块")
    return sectors
