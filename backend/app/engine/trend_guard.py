"""
趋势卫士引擎 V5.0（方案B核心模块）

功能：
1. MA20 + MACD 双指标趋势判断
2. 震荡市静音机制（避免频繁交易）
3. 三阶清仓闸门（极端行情保护）
4. 趋势解读文案生成（供前端展示）

输入：基金代码 + 持仓成本
输出：趋势信号 + 操作建议 + 解读文案
"""
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# 基金分类映射表缓存
_FUND_CATEGORY_CACHE = None
_FUND_CATEGORY_PATH = os.path.join(
    os.path.dirname(__file__), "../data/fund_category_map.json"
)


def _load_fund_category_map() -> dict:
    """加载基金分类映射表（带缓存）"""
    global _FUND_CATEGORY_CACHE

    if _FUND_CATEGORY_CACHE is not None:
        return _FUND_CATEGORY_CACHE

    try:
        with open(_FUND_CATEGORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            _FUND_CATEGORY_CACHE = data
            logger.info("✅ 基金分类映射表加载成功")
            return data
    except Exception as e:
        logger.error(f"❌ 基金分类映射表加载失败: {e}")
        return {"categories": {}}


def _get_fund_category(fund_code: str) -> str:
    """
    根据基金代码获取分类

    返回："broad" | "sector" | "theme" | "unknown"
    """
    data = _load_fund_category_map()
    fund_mapping = data.get("fund_mapping", [])

    for item in fund_mapping:
        if item.get("code") == fund_code:
            return item.get("category", "unknown")

    # 未找到 → 默认返回 "sector"（最保守）
    logger.warning(f"基金 {fund_code} 未找到分类，默认使用 sector")
    return "sector"


def _get_clearance_thresholds(fund_code: str) -> dict:
    """
    根据基金类型获取清仓闸门阈值

    返回：{overheat, drawdown, panic} 阈值字典
    """
    data = _load_fund_category_map()
    category = _get_fund_category(fund_code)

    categories = data.get("categories", {})
    if category in categories:
        thresholds = categories[category].get("clear_threshold", {})
        return {
            "overheat": thresholds.get("overheat", 20.0) / 100,  # 转换为小数
            "drawdown": thresholds.get("drawdown", -10.0) / 100,
            "panic": thresholds.get("panic", 20.0)
        }

    # 默认值（sector）
    return {"overheat": 0.20, "drawdown": -0.10, "panic": 20.0}

# ============================================================
# 趋势卫士配置
# ============================================================

# MA20 趋势判断阈值
MA20_TREND_THRESHOLD = 0.02  # 价格相对MA20 ±2% 内视为震荡

# MACD 参数
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# 震荡市判断参数（与板块过滤器一致）
OSCILLATION_AMPLITUDE_MAX = 0.05  # 20日振幅 ≤ 5%
OSCILLATION_CROSSING_MIN = 3      # 穿越MA20 ≥ 3次
OSCILLATION_SLOPE_MAX = 0.003     # MA20斜率绝对值 ≤ 0.3%


def _get_price(d: dict) -> float:
    """兼容获取价格/净值：优先 close，其次 nav，默认 0"""
    return d.get("close", d.get("nav", 0))


# ============================================================
# 核心函数
# ============================================================

def calculate_position_v5(
    fund_code: str,
    cost_basis: float,
    current_position: float,
    date: str = None,
) -> Dict:
    """
    计算持仓建议（趋势卫士核心函数）

    Args:
        fund_code: 基金代码
        cost_basis: 持仓成本（元）
        current_position: 当前仓位（0-1）
        date: 计算日期（默认今天）

    Returns:
        {
            "trend_signal": "上升" | "下降" | "震荡",
            "macd_signal": "金叉" | "死叉" | "中性",
            "oscillation_silence": bool,  # 是否震荡静音
            "gate_triggered": dict | None,  # 触发的闸门（gate1/gate2/gate3）
            "operation_suggestion": str,     # 操作建议
            "trend_narrative": str,         # 趋势解读文案（供前端展示）
        }
    """
    logger.info(f"趋势卫士计算开始: {fund_code}")

    try:
        # 1. 获取历史数据
        from app.engine.data_fetcher import fetch_fund_nav_history, fetch_index_hist

        # 获取基金净值历史（60日）
        nav_history = fetch_fund_nav_history(fund_code, days=60)

        if not nav_history or len(nav_history) < 20:
            logger.warning(f"历史数据不足: {fund_code}, 仅{len(nav_history) if nav_history else 0}条")
            return _get_default_response("数据不足")

        # 2. 计算MA20趋势
        trend_signal = _calculate_ma20_trend(nav_history)

        # 3. 计算MACD信号
        macd_signal = _calculate_macd(nav_history)

        # 4. 判断震荡市（静音机制）
        oscillation_silence = _check_oscillation(nav_history)

        # 5. 三阶清仓闸门检查
        gate_triggered = _check_clearance_gates(
            fund_code, nav_history, current_position, cost_basis
        )

        # 6. 生成操作建议
        operation_suggestion = _generate_operation_suggestion(
            trend_signal, macd_signal, oscillation_silence, gate_triggered
        )

        # 7. 生成趋势解读文案（方案B P0-4 核心输出）
        trend_narrative = _generate_trend_narrative(
            trend_signal, macd_signal, oscillation_silence, gate_triggered, nav_history
        )

        logger.info(f"趋势卫士计算完成: {fund_code}, signal={trend_signal}, gate={gate_triggered}")

        return {
            "trend_signal": trend_signal,
            "macd_signal": macd_signal,
            "oscillation_silence": oscillation_silence,
            "gate_triggered": gate_triggered,
            "operation_suggestion": operation_suggestion,
            "trend_narrative": trend_narrative,
        }

    except Exception as e:
        logger.error(f"趋势卫士计算失败: {fund_code}, error={e}")
        return _get_default_response(f"计算失败: {str(e)}")


# ============================================================
# 内部函数：MA20趋势计算
# ============================================================

def _calculate_ma20_trend(nav_history: list) -> str:
    """
    计算MA20趋势位置

    返回："上升" | "下降" | "震荡"
    """
    if len(nav_history) < 20:
        return "震荡"

    # 提取收盘价（兼容 close/nav 双键）
    prices = [_get_price(d) for d in nav_history[-20:]]

    # 计算MA20
    ma20 = sum(prices) / len(prices)
    current_price = prices[-1]

    # 计算价格相对MA20位置
    if ma20 > 0:
        price_vs_ma20 = (current_price - ma20) / ma20
    else:
        return "震荡"

    # 计算短期趋势（5日涨跌幅）
    if len(prices) >= 5 and prices[-5] > 0:
        short_trend = (prices[-1] - prices[-5]) / prices[-5]
    else:
        short_trend = 0

    # 三维度震荡判断（与板块过滤器一致）
    # 维度1：区间振幅约束
    max_price = max(prices)
    min_price = min(prices)
    if max_price > 0:
        amplitude = (max_price - min_price) / min_price
    else:
        amplitude = 0

    # 维度2：均线穿越频率
    crossings = 0
    for i in range(1, len(prices)):
        if (prices[i-1] <= ma20 and prices[i] > ma20) or \
           (prices[i-1] >= ma20 and prices[i] < ma20):
            crossings += 1

    # 维度3：均线斜率约束
    if len(prices) >= 10:
        ma20_slope = (prices[-1] - prices[-10]) / prices[-10] / 10
    else:
        ma20_slope = 0

    # 综合判断（满足2项及以上 → 震荡）
    dimension1 = amplitude <= OSCILLATION_AMPLITUDE_MAX
    dimension2 = crossings >= OSCILLATION_CROSSING_MIN
    dimension3 = abs(ma20_slope) <= OSCILLATION_SLOPE_MAX

    oscillation_score = sum([dimension1, dimension2, dimension3])

    if oscillation_score >= 2:
        return "震荡"
    else:
        if current_price > ma20 and short_trend > 0:
            return "上升"
        elif current_price < ma20 and short_trend < 0:
            return "下降"
        else:
            return "下降" if current_price < ma20 else "上升"


# ============================================================
# 内部函数：MACD计算
# ============================================================

def _calculate_macd(nav_history: list) -> str:
    """
    计算MACD信号

    返回："金叉" | "死叉" | "中性"
    """
    if len(nav_history) < MACD_SLOW + MACD_SIGNAL:
        return "中性"

    # 提取收盘价（兼容 close/nav 双键）
    prices = [_get_price(d) for d in nav_history]

    # 计算EMA
    ema_fast = _calculate_ema(prices, MACD_FAST)
    ema_slow = _calculate_ema(prices, MACD_SLOW)

    # 计算DIF
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]

    # 计算DEA（DIF的EMA）
    dea = _calculate_ema(dif, MACD_SIGNAL)

    # 判断金叉/死叉
    if len(dif) < 2 or len(dea) < 2:
        return "中性"

    # 前一日和今日
    if dif[-2] < dea[-2] and dif[-1] > dea[-1]:
        return "金叉"  # 买入信号
    elif dif[-2] > dea[-2] and dif[-1] < dea[-1]:
        return "死叉"  # 卖出信号
    else:
        return "中性"


def _calculate_ema(prices: list, period: int) -> list:
    """计算EMA（指数移动平均）"""
    if len(prices) < period:
        return prices

    ema = []
    multiplier = 2 / (period + 1)

    # 第一个EMA = SMA
    ema.append(sum(prices[:period]) / period)

    # 后续EMA
    for i in range(period, len(prices)):
        ema.append((prices[i] - ema[-1]) * multiplier + ema[-1])

    return ema


# ============================================================
# 内部函数：震荡市判断
# ============================================================

def _check_oscillation(nav_history: list) -> bool:
    """
    检查是否震荡市（静音机制）

    返回：True = 震荡市（静音，不发送交易信号）
    """
    trend = _calculate_ma20_trend(nav_history)
    return trend == "震荡"


# ============================================================
# 内部函数：三阶清仓闸门
# ============================================================

def _check_clearance_gates(
    fund_code: str,
    nav_history: list,
    current_position: float,
    cost_basis: float,
) -> Optional[dict]:
    """
    检查三阶清仓闸门（动态阈值）

    返回：触发的闸门详情（包含阈值）或 None
    """
    # 获取动态阈值
    thresholds = _get_clearance_thresholds(fund_code)

    # 闸门1：市场过热（收益率 >= overheat_threshold）
    if len(nav_history) >= 1:
        current_nav = _get_price(nav_history[-1])
        if current_nav > 0 and cost_basis > 0:
            profit_ratio = (current_nav - cost_basis) / cost_basis
            if profit_ratio >= thresholds["overheat"]:
                logger.warning(f"闸门1触发: {fund_code}, 收益率={profit_ratio:.2%}, 阈值={thresholds['overheat']:.2%}")
                return {
                    "gate": "gate1",
                    "reason": f"市场过热（收益率 {profit_ratio:.1%} >= {thresholds['overheat']:.0%}）",
                    "threshold": thresholds["overheat"]
                }

    # 闸门2：回撤过大（回撤 >= |drawdown_threshold|）
    if len(nav_history) >= 20:
        max_nav = max([_get_price(d) for d in nav_history[-60:]])  # 最近60日最高
        current_nav = _get_price(nav_history[-1])
        if max_nav > 0:
            drawdown = (max_nav - current_nav) / max_nav
            if drawdown >= abs(thresholds["drawdown"]):
                logger.warning(f"闸门2触发: {fund_code}, 回撤={drawdown:.2%}, 阈值={abs(thresholds['drawdown']):.2%}")
                return {
                    "gate": "gate2",
                    "reason": f"回撤过大（回撤 {drawdown:.1%} >= {abs(thresholds['drawdown']):.0%}）",
                    "threshold": thresholds["drawdown"]
                }

    # 闸门3：极端恐慌（需要调用情绪分析，此处简化）
    # TODO: 实际实现需要调用 sentiment engine
    # if sentiment_score <= thresholds["panic"]:
    #     logger.warning(f"闸门3触发: {fund_code}, 情绪分={sentiment_score}, 阈值={thresholds['panic']}")
    #     return {
    #         "gate": "gate3",
    #         "reason": f"极端恐慌（情绪分 {sentiment_score} <= {thresholds['panic']}）",
    #         "threshold": thresholds["panic"]
    #     }

    return None


# ============================================================
# 内部函数：操作建议生成
# ============================================================

def _generate_operation_suggestion(
    trend_signal: str,
    macd_signal: str,
    oscillation_silence: bool,
    gate_triggered: Optional[dict],
) -> str:
    """生成操作建议（使用动态阈值）"""
    # 闸门触发 → 强制清仓/减仓
    if gate_triggered:
        gate = gate_triggered.get("gate", "")
        reason = gate_triggered.get("reason", "")

        if gate == "gate1":
            return f"⚠️ {reason}，建议减仓至50%以下"
        if gate == "gate2":
            return f"⚠️ {reason}，建议止损清仓"
        if gate == "gate3":
            return f"⚠️ {reason}，建议暂停交易"

    # 震荡市静音
    if oscillation_silence:
        return "📊 震荡市，建议持仓观望，不操作"

    # 趋势 + MACD 组合建议
    if trend_signal == "上升" and macd_signal == "金叉":
        return "📈 趋势向上+MACD金叉，建议加仓"
    elif trend_signal == "上升" and macd_signal == "中性":
        return "📈 趋势向上，可持有观察"
    elif trend_signal == "下降" and macd_signal == "死叉":
        return "📉 趋势向下+MACD死叉，建议减仓"
    elif trend_signal == "下降" and macd_signal == "中性":
        return "📉 趋势向下，建议谨慎持有"
    else:
        return "📊 趋势不明，建议观望"


# ============================================================
# 内部函数：趋势解读文案生成（P0-4 核心）
# ============================================================

def _generate_trend_narrative(
    trend_signal: str,
    macd_signal: str,
    oscillation_silence: bool,
    gate_triggered: Optional[dict],
    nav_history: list,
) -> str:
    """
    生成趋势解读文案（供前端展示）

    返回：例如 "📈 趋势向上，MACD金叉，适合加仓"
    """
    # 闸门触发 → 紧急提示
    if gate_triggered and gate_triggered.get("gate") == "gate1":
        return "⚠️ 市场过热（仓位>=70%），建议减仓至50%以下"
    if gate_triggered and gate_triggered.get("gate") == "gate2":
        return "⚠️ 回撤过大（>=15%），建议止损清仓"
    if gate_triggered and gate_triggered.get("gate") == "gate3":
        return "⚠️ 市场极端恐慌，建议暂停交易"

    # 震荡市静音
    if oscillation_silence:
        return "📊 当前为震荡市，建议持仓观望，避免频繁交易"

    # 趋势向上
    if trend_signal == "上升":
        if macd_signal == "金叉":
            return "📈 趋势向上，MACD金叉，适合加仓"
        elif macd_signal == "死叉":
            return "📈 趋势向上，但MACD死叉，建议谨慎加仓"
        else:
            return "📈 趋势向上，建议持有观察"

    # 趋势向下
    elif trend_signal == "下降":
        if macd_signal == "死叉":
            return "📉 趋势向下，MACD死叉，建议减仓"
        elif macd_signal == "金叉":
            return "📉 趋势向下，但MACD金叉，可能出现反弹"
        else:
            return "📉 趋势向下，建议谨慎持有"

    # 震荡
    else:
        return "📊 趋势不明，建议观望等待方向确认"


# ============================================================
# 辅助函数：默认响应
# ============================================================

def _get_default_response(reason: str) -> Dict:
    """返回默认响应（计算失败时）"""
    return {
        "trend_signal": "震荡",
        "macd_signal": "中性",
        "oscillation_silence": True,
        "gate_triggered": None,
        "operation_suggestion": "数据不足，建议观望",
        "trend_narrative": f"⚠️ {reason}，暂无法判断趋势",
    }


__all__ = ["calculate_position_v5"]
