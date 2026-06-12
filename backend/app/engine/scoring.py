"""
7大因子评分函数
每个因子返回 0-100 分，50 分为中性

因子列表：
1. 波动率评分 (Volatility) — 倒U型，极端波动触发反转标记
2. 换手率评分 (Turnover) — 倒U型，适度活跃最佳
3. 涨跌家数比评分 (Adv/Decline) — 倒U型，过偏=过热/恐慌
4. 新高新低评分 (New High) — 单调递增但有天花板
5. 融资融券评分 (Margin) — 融资占优=看多，融券占优=看空
6. 债券权益比评分 (Bond/Equity) — 股债跷跷板
7. RSI评分 (RSI) — 单调递减，超买=低分，超卖=高分
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FactorScore:
    """因子评分结果"""
    factor_name: str
    raw_value: float
    score: float  # 0-100
    label: str  # extreme_fear/fear/neutral/greed/extreme_greed
    is_extreme: bool = False
    extreme_type: str = ""  # oversold/overbought


# ============================================================
# 因子1: 波动率评分
# 逻辑：倒U型。适度波动(15-25%)最佳，过低=死水(恐慌)，过高=恐慌/狂热
# ============================================================
def score_volatility(volatility: float) -> FactorScore:
    """
    波动率评分（含极端反转标记）

    Args:
        volatility: 年化波动率(%)

    Returns:
        FactorScore: 评分结果

    评分逻辑:
        - <5%:  死水一潭，可能是恐慌底部 → 20分 (extreme_fear)
        - 5-10%: 低波动 → 35分
        - 10-15%: 温和波动 → 45分
        - 15-25%: 适度波动，最佳区间 → 55-65分
        - 25-35%: 较高波动 → 45分
        - 35-50%: 高波动 → 30分 (extreme_greed/panic)
        - >50%:  极端波动 → 15分，标记 is_extreme
    """
    if volatility < 5:
        score = 20.0
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "oversold"
    elif volatility < 10:
        score = 35.0
        label = "fear"
        is_extreme = False
        extreme_type = ""
    elif volatility < 15:
        score = 45.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif volatility < 25:
        score = 55.0 + (volatility - 15) * 1.0  # 55-65
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif volatility < 35:
        score = 45.0
        label = "greed"
        is_extreme = False
        extreme_type = ""
    elif volatility < 50:
        score = 30.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"
    else:
        score = 15.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="波动率",
        raw_value=volatility,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


# ============================================================
# 因子2: 换手率评分
# 逻辑：倒U型。2-5% 最佳，过低=无人参与，过高=投机过热
# ============================================================
def score_turnover(turnover_ratio: float) -> FactorScore:
    """
    换手率评分

    Args:
        turnover_ratio: 换手率(%)

    Returns:
        FactorScore: 评分结果

    评分逻辑:
        - <0.5%: 极度低迷 → 25分
        - 0.5-1%: 低迷 → 40分
        - 1-2%: 温和活跃 → 50分
        - 2-5%: 活跃，最佳 → 60-70分
        - 5-8%: 较热 → 50分
        - 8-12%: 过热 → 35分
        - >12%: 极度投机 → 20分
    """
    if turnover_ratio < 0.5:
        score = 25.0
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "oversold"
    elif turnover_ratio < 1.0:
        score = 40.0
        label = "fear"
        is_extreme = False
        extreme_type = ""
    elif turnover_ratio < 2.0:
        score = 50.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif turnover_ratio < 5.0:
        score = 60.0 + (turnover_ratio - 2.0) * 3.33  # 60-70
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif turnover_ratio < 8.0:
        score = 50.0
        label = "greed"
        is_extreme = False
        extreme_type = ""
    elif turnover_ratio < 12.0:
        score = 35.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"
    else:
        score = 20.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="换手率",
        raw_value=turnover_ratio,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


# ============================================================
# 因子3: 涨跌家数比评分
# 逻辑：倒U型。1:1附近最佳，一边倒=极端
# ============================================================
def score_adv_decline(adv_ratio: float) -> FactorScore:
    """
    涨跌家数比评分（倒U型）

    Args:
        adv_ratio: 上涨家数/下跌家数

    Returns:
        FactorScore: 评分结果

    评分逻辑:
        - <0.3: 极度恐慌 → 10分
        - 0.3-0.6: 恐慌 → 30分
        - 0.6-0.8: 偏弱 → 45分
        - 0.8-1.2: 均衡，最佳 → 65-75分
        - 1.2-1.5: 偏强 → 55分
        - 1.5-2.5: 过热 → 40分
        - >2.5: 极度狂热 → 15分
    """
    if adv_ratio < 0.3:
        score = 10.0
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "oversold"
    elif adv_ratio < 0.6:
        score = 30.0
        label = "fear"
        is_extreme = False
        extreme_type = ""
    elif adv_ratio < 0.8:
        score = 45.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif adv_ratio < 1.2:
        score = 65.0 + (adv_ratio - 0.8) * 25.0  # 65-75
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif adv_ratio < 1.5:
        score = 55.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif adv_ratio < 2.5:
        score = 40.0
        label = "greed"
        is_extreme = False
        extreme_type = ""
    else:
        score = 15.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="涨跌比",
        raw_value=adv_ratio,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


# ============================================================
# 因子4: 新高新低评分
# 逻辑：单调递增但有天花板
# ============================================================
def score_new_high(new_high_ratio: float) -> FactorScore:
    """
    新高新低评分

    Args:
        new_high_ratio: 创N日新高股票占比(%)

    Returns:
        FactorScore: 评分结果

    评分逻辑:
        - <1%: 极度弱势 → 15分
        - 1-3%: 弱势 → 30分
        - 3-5%: 偏弱 → 45分
        - 5-8%: 正常 → 55分
        - 8-12%: 偏强 → 65分
        - 12-20%: 强势 → 75分
        - >20%: 过强（可能是顶部信号）→ 60分
    """
    if new_high_ratio < 1.0:
        score = 15.0
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "oversold"
    elif new_high_ratio < 3.0:
        score = 30.0
        label = "fear"
        is_extreme = False
        extreme_type = ""
    elif new_high_ratio < 5.0:
        score = 45.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif new_high_ratio < 8.0:
        score = 55.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif new_high_ratio < 12.0:
        score = 65.0
        label = "greed"
        is_extreme = False
        extreme_type = ""
    elif new_high_ratio < 20.0:
        score = 75.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"
    else:
        score = 60.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="新高占比",
        raw_value=new_high_ratio,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


# ============================================================
# 因子5: 融资融券评分
# ============================================================
def score_margin(margin_data: dict) -> FactorScore:
    """
    融资融券评分

    Args:
        margin_data: 包含以下字段:
            - margin_balance: 融资余额(亿)
            - short_balance: 融券余额(亿)
            - net_margin_flow: 融资净流入(亿)

    Returns:
        FactorScore: 评分结果

    评分逻辑：
        融资净流入 > 0 且融资/融券比合理 → 偏乐观
        融资大幅流出 → 偏悲观
        融券大幅增加 → 偏悲观（做空力量增强）
    """
    margin_balance = margin_data.get("margin_balance", 0)
    short_balance = margin_data.get("short_balance", 0)
    net_margin_flow = margin_data.get("net_margin_flow", 0)

    # 融资融券比
    if short_balance > 0:
        ratio = margin_balance / short_balance
    else:
        ratio = 100.0  # 无融券=极度乐观

    # 综合评分
    score = 50.0

    # 融资净流入影响 (±20分)
    if net_margin_flow > 50:
        score += 15.0
    elif net_margin_flow > 10:
        score += 8.0
    elif net_margin_flow > -10:
        score += 0.0
    elif net_margin_flow > -50:
        score -= 8.0
    else:
        score -= 15.0

    # 融资融券比影响 (±15分)
    if ratio > 50:
        score += 10.0
    elif ratio > 20:
        score += 5.0
    elif ratio > 10:
        score += 0.0
    elif ratio > 5:
        score -= 5.0
    else:
        score -= 10.0

    score = max(5.0, min(95.0, score))

    if score < 25:
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "oversold"
    elif score < 40:
        label = "fear"
        is_extreme = False
        extreme_type = ""
    elif score < 60:
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif score < 75:
        label = "greed"
        is_extreme = False
        extreme_type = ""
    else:
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="融资融券",
        raw_value=net_margin_flow,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


# ============================================================
# 因子6: 债券权益比评分（股债跷跷板）
# ============================================================
def score_bond_equity(bond_yield: float, equity_yield: float) -> FactorScore:
    """
    债券权益比评分

    Args:
        bond_yield: 10年期国债收益率(%)
        equity_yield: 股票市场盈利收益率(1/PE, %)

    Returns:
        FactorScore: 评分结果

    评分逻辑：
        股债收益差 = equity_yield - bond_yield
        >2%: 股票极具吸引力 → 高分
        1-2%: 股票有吸引力 → 偏高分
        0-1%: 中性 → 50分
        -1-0%: 债券更有吸引力 → 偏低分
        <-1%: 债券极具吸引力 → 低分
    """
    spread = equity_yield - bond_yield

    if spread > 3.0:
        score = 85.0
        label = "extreme_greed"  # 股票极度便宜
        is_extreme = True
        extreme_type = "oversold"  # 股市可能超跌
    elif spread > 2.0:
        score = 70.0
        label = "greed"
        is_extreme = False
        extreme_type = ""
    elif spread > 1.0:
        score = 58.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif spread > 0.0:
        score = 50.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif spread > -1.0:
        score = 42.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif spread > -2.0:
        score = 30.0
        label = "fear"
        is_extreme = False
        extreme_type = ""
    else:
        score = 15.0
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="股债比",
        raw_value=spread,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


# ============================================================
# 因子7: RSI评分
# 逻辑：单调递减。RSI越高(超买)分越低，RSI越低(超卖)分越高
# ============================================================
def score_rsi(rsi_value: float) -> FactorScore:
    """
    RSI评分（单调递减）

    Args:
        rsi_value: RSI(14) 值

    Returns:
        FactorScore: 评分结果

    评分逻辑:
        - <20: 极度超卖，绝佳买点 → 90分
        - 20-30: 超卖，好买点 → 75分
        - 30-40: 偏弱 → 60分
        - 40-60: 正常区间 → 50-55分
        - 60-70: 偏强 → 40分
        - 70-80: 超买 → 25分
        - >80: 极度超买 → 10分
    """
    if rsi_value < 20:
        score = 90.0
        label = "extreme_fear"
        is_extreme = True
        extreme_type = "oversold"
    elif rsi_value < 30:
        score = 75.0
        label = "fear"
        is_extreme = False
        extreme_type = ""
    elif rsi_value < 40:
        score = 60.0
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif rsi_value < 60:
        score = 55.0 - (rsi_value - 40) * 0.25  # 55 -> 50
        label = "neutral"
        is_extreme = False
        extreme_type = ""
    elif rsi_value < 70:
        score = 40.0
        label = "greed"
        is_extreme = False
        extreme_type = ""
    elif rsi_value < 80:
        score = 25.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"
    else:
        score = 10.0
        label = "extreme_greed"
        is_extreme = True
        extreme_type = "overbought"

    return FactorScore(
        factor_name="RSI",
        raw_value=rsi_value,
        score=round(score, 1),
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )
