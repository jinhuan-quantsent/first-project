"""
趋势卫士引擎 V5.0（方案B核心模块）— Gate体系重构版
拆分两套独立体系：建仓准入层 + 持仓风控层

持仓风控层（check_holding_gates）：
  Gate1（极端回撤保命闸）：阶段最大回撤≥20% → 无条件强制清仓
  Gate2（趋势破位离场闸）：跌破MA20 + 回撤≥10% → 强制清仓（contrarian豁免）
  Gate-E（情绪过热提示闸）：信号E级 → 仅提示不减仓

建仓准入层（check_admission_gate）：
  Gate3（准入排除闸）：信号E / Gate2已触发 / 置信度≤1星 / excluded轨道 → 不准入
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
    data = _load_fund_category_map()
    fund_mapping = data.get("fund_mapping", [])
    for item in fund_mapping:
        if item.get("code") == fund_code:
            return item.get("category", "unknown")
    logger.warning(f"基金 {fund_code} 未找到分类，默认使用 sector")
    return "sector"


def _get_clearance_thresholds(fund_code: str) -> dict:
    data = _load_fund_category_map()
    category = _get_fund_category(fund_code)
    categories = data.get("categories", {})
    if category in categories:
        thresholds = categories[category].get("clear_threshold", {})
        return {
            "overheat": thresholds.get("overheat", 20.0) / 100,
            "drawdown": thresholds.get("drawdown", -10.0) / 100,
            "panic": thresholds.get("panic", 20.0),
        }
    return {"overheat": 0.20, "drawdown": -0.10, "panic": 20.0}


# ===========================================================
# 基金 → 板块代码映射
# ===========================================================

_SW_INDUSTRY_NAMES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}

_DIV_INDEX_CODE = "SW_L1_DIV"


def _get_fund_sector_code(fund_code: str) -> Optional[str]:
    """查询基金对应的申万一级行业板块代码"""
    try:
        import pymysql
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        from app.core.config import settings

        database_url = settings.DATABASE_URL
        if not database_url:
            return None

        sync_url = database_url.replace("mysql+aiomysql://", "mysql+pymysql://")
        engine = create_engine(sync_url, poolclass=NullPool)

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT index_code FROM fund_sentiment.fund_mapping "
                    "WHERE fund_code = :code LIMIT 1"
                ),
                {"code": fund_code},
            )
            row = result.first()
            if not row:
                logger.debug(f"基金 {fund_code} 在 fund_mapping 表中未找到")
                return None

            index_code = row[0]
            if not index_code:
                return None

            if index_code.startswith("801"):
                logger.info(f"基金 {fund_code} → 板块代码 {index_code}")
                return index_code

            logger.debug(f"基金 {fund_code} 的 index_code={index_code} 不是 SW 行业代码")
            return None

    except Exception as e:
        logger.warning(f"查询基金板块代码失败: {fund_code}, error={e}")
        return None


def _get_latest_div_factor() -> tuple:
    """从 factor_history 表获取最新的 DIV 因子值和分位数"""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        from app.core.config import settings

        database_url = settings.DATABASE_URL
        if not database_url:
            return None, None

        sync_url = database_url.replace("mysql+aiomysql://", "mysql+pymysql://")
        engine = create_engine(sync_url, poolclass=NullPool)

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT raw_value, quantile_percentile FROM factor_history "
                    "WHERE index_code = :idx AND factor_name = 'DIV' "
                    "ORDER BY trade_date DESC LIMIT 1"
                ),
                {"idx": _DIV_INDEX_CODE},
            )
            row = result.first()
            if row:
                div_raw = float(row[0]) if row[0] is not None else None
                div_pct = float(row[1]) if row[1] is not None else None
                logger.info(f"DIV因子: raw={div_raw}, percentile={div_pct}")
                return div_raw, div_pct

        logger.warning("factor_history 中未找到 DIV 因子数据")
        return None, None

    except Exception as e:
        logger.warning(f"获取 DIV 因子失败: {e}")
        return None, None


def _get_sector_track(fund_code: str) -> Optional[str]:
    """获取基金对应板块的双轨制过滤器结果"""
    try:
        sector_code = _get_fund_sector_code(fund_code)
        if not sector_code:
            return None

        sector_name = _SW_INDUSTRY_NAMES.get(sector_code, sector_code)

        div_raw, div_pct = _get_latest_div_factor()

        from app.engine.sector_scorer import score_sector_v5

        kwargs = {}
        if div_raw is not None and div_pct is not None:
            kwargs["div_percentile"] = div_pct
            kwargs["div_raw_value"] = div_raw

        sector_result = score_sector_v5(
            sector_code=sector_code,
            sector_name=sector_name,
            **kwargs,
        )

        if not sector_result:
            logger.warning(f"板块 {sector_code} V5 评分失败，降级放行")
            return None

        factor_completeness = sector_result.get("factor_completeness", 0.0)
        cold_start = sector_result.get("cold_start", True)
        track = sector_result.get("track")

        logger.info(
            f"板块 {sector_code}({sector_name}): track={track}, "
            f"score={sector_result.get('sentiment_score', 0):.1f}, "
            f"signal={sector_result.get('signal_level', '?')}, "
            f"completeness={factor_completeness}, cold_start={cold_start}"
        )

        if factor_completeness < 0.90 or cold_start:
            logger.info(
                f"板块 {sector_code} 因子不完整 "
                f"(completeness={factor_completeness:.2f}, cold_start={cold_start})，降级放行"
            )
            return None

        return track

    except ImportError:
        logger.warning("sector_scorer 模块未找到，板块过滤降级放行")
        return None
    except Exception as e:
        logger.warning(f"获取板块轨道失败: {fund_code}, error={e}，降级放行")
        return None


# ===========================================================
# 趋势卫士配置
# ===========================================================

MA20_TREND_THRESHOLD = 0.02
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
OSCILLATION_AMPLITUDE_MAX = 0.05
OSCILLATION_CROSSING_MIN = 3
OSCILLATION_SLOPE_MAX = 0.003

# Gate阈值常量
GATE1_DRAWDOWN_THRESHOLD = 0.20  # 极端回撤保命闸：20%
GATE2_DRAWDOWN_THRESHOLD = 0.10  # 趋势破位离场闸：10%
DRAWDOWN_WINDOW = 60             # 回撤计算窗口（交易日）

# Gate-P 恐慌闸阈值
PANIC_CONSECUTIVE_DAYS = 2       # 连续大跌天数
PANIC_DECLINE_THRESHOLD = 0.03   # 单日跌幅阈值（3%）
PANIC_VOLUME_SHRINK_THRESHOLD = 0.30  # 成交量萎缩阈值（30%）


def _get_price(d: dict) -> float:
    return d.get("close", d.get("nav", 0))


def _calculate_drawdown(nav_history: list, window: int = DRAWDOWN_WINDOW) -> float:
    """
    计算阶段最大回撤（max→current / max）
    使用最近 window 个交易日的数据
    """
    prices = [_get_price(d) for d in nav_history]
    if not prices:
        return 0.0

    window_prices = prices[-window:] if len(prices) >= window else prices
    max_nav = max(window_prices)
    current_nav = prices[-1]

    if max_nav > 0:
        return (max_nav - current_nav) / max_nav
    return 0.0


# ===========================================================
# 核心函数
# ===========================================================

def calculate_position_v5(
    fund_code: str,
    cost_basis: float,
    current_position: float,
    signal_level: str = "B",
    fund_type: str = "unknown",
    confidence_stars: int = 3,
    date: str = None,
) -> Dict:
    """
    计算持仓建议（趋势卫士核心函数）

    参数：
        fund_code: 基金代码
        cost_basis: 持仓成本
        current_position: 当前仓位（0-1）
        signal_level: 信号等级（S+/S/A/B/C/D/E）
        fund_type: 基金分类（broad/sector/theme）
        confidence_stars: 置信度星级（1-5），用于准入层
        date: 计算日期

    返回：
        {
            trend_signal, macd_signal, oscillation_silence,
            gate_triggered,          ← 持仓风控层结果
            admission_gate,          ← 建仓准入层结果
            operation_suggestion, trend_narrative,
            sector_track
        }
    """
    logger.info(
        f"趋势卫士计算开始: {fund_code}, signal={signal_level}, "
        f"type={fund_type}, conf={confidence_stars}"
    )

    try:
        from app.engine.data_fetcher import fetch_fund_nav_history, fetch_index_hist

        nav_history = fetch_fund_nav_history(fund_code, days=60)
        if not nav_history or len(nav_history) < 60:
            logger.warning(f"趋势卫士数据不足(需≥60条): {fund_code}, 仅{len(nav_history) if nav_history else 0}条")
            return _get_default_response("数据不足")

        # 正序化
        if len(nav_history) >= 2:
            try:
                d0 = str(nav_history[0].get("date", ""))
                d1 = str(nav_history[-1].get("date", ""))
                if d0 and d1 and d0 > d1:
                    nav_history = list(reversed(nav_history))
            except Exception:
                pass

        trend_signal = _calculate_ma20_trend(nav_history)
        macd_result = _calculate_macd(nav_history)
        macd_signal = macd_result["signal"]   # 兼容：下游仍用 str
        oscillation_silence = _check_oscillation(nav_history)

        # 获取板块双轨制轨道
        sector_track = None
        fund_category = _get_fund_category(fund_code)
        if fund_category in ("sector", "theme"):
            sector_track = _get_sector_track(fund_code)
            logger.info(f"基金 {fund_code} 板块轨道: {sector_track}")
        else:
            logger.debug(f"基金 {fund_code} 类别={fund_category}，跳过板块过滤")

        # ★ Gate体系重构：持仓风控层
        gate_triggered = check_holding_gates(
            signal_level=signal_level,
            sector_track=sector_track,
            nav_history=nav_history,
            ma20_trend=trend_signal,
            current_pct=current_position,
            fund_code=fund_code,
        )

        # Gate2是否触发（从结构化 gate 对象里取）
        gate2_triggered = (
            isinstance(gate_triggered, dict)
            and gate_triggered.get("gate_2", {}).get("triggered", False)
        )

        # ★ Gate体系重构：建仓准入层
        admission_gate = check_admission_gate(
            signal_level=signal_level,
            sector_track=sector_track,
            confidence=confidence_stars,
            gate2_triggered=gate2_triggered,
            fund_code=fund_code,
        )

        operation_suggestion = _generate_operation_suggestion(
            trend_signal, macd_signal, oscillation_silence, gate_triggered,
            sector_track=sector_track,
        )

        trend_narrative = _generate_trend_narrative(
            trend_signal, macd_signal, oscillation_silence, gate_triggered, nav_history,
            sector_track=sector_track,
        )

        logger.info(
            f"趋势卫士计算完成: {fund_code}, signal={trend_signal}, "
            f"gate={gate_triggered}, sector_track={sector_track}"
        )

        # 从结构化 gate 对象里取兼容字段（gate_triggered 已 DEPRECATED）
        gate_triggered_compat = gate_triggered.get("gate_triggered") if isinstance(gate_triggered, dict) else None

        return {
            "trend_signal": trend_signal,
            "macd_signal": macd_signal,            # 兼容：str，6 状态值
            "macd_detail": macd_result,             # 新增：完整 dict 详情
            "oscillation_silence": oscillation_silence,
            "gate_triggered": gate_triggered_compat,   # DEPRECATED 兼容字段
            "gates": gate_triggered,                    # 新结构化 Gate 对象
            "admission_gate": admission_gate,
            "operation_suggestion": operation_suggestion,
            "trend_narrative": trend_narrative,
            "sector_track": sector_track,
        }

    except Exception as e:
        logger.error(f"趋势卫士计算失败: {fund_code}, error={e}")
        return _get_default_response(f"计算失败: {str(e)}")


# ===========================================================
# 内部函数：MA20趋势计算
# ===========================================================

def _calculate_ma20_trend(nav_history: list) -> str:
    if len(nav_history) < 20:
        return "震荡"

    prices = [_get_price(d) for d in nav_history[-20:]]

    ma20 = sum(prices) / len(prices)
    current_price = prices[-1]

    if ma20 > 0:
        price_vs_ma20 = (current_price - ma20) / ma20
    else:
        return "震荡"

    if len(prices) >= 5 and prices[-5] > 0:
        short_trend = (prices[-1] - prices[-5]) / prices[-5]
    else:
        short_trend = 0

    max_price = max(prices)
    min_price = min(prices)
    amplitude = (max_price - min_price) / min_price if max_price > 0 else 0

    crossings = 0
    for i in range(1, len(prices)):
        if (prices[i-1] <= ma20 and prices[i] > ma20) or \
           (prices[i-1] >= ma20 and prices[i] < ma20):
            crossings += 1

    if len(prices) >= 10:
        ma20_slope = (prices[-1] - prices[-10]) / prices[-10] / 10
    else:
        ma20_slope = 0

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


# ===========================================================
# 内部函数：MACD计算
# ===========================================================

def _calculate_macd(nav_history: list) -> dict:
    """
    MACD 6 状态判定 + 4 维度详情

    返回 dict:
        signal:           金叉/多头/多头收敛/死叉/空头/空头收敛/中性
        strength:         强/中等/弱/无
        trend:            扩大/收敛/稳定/无
        days:             当前状态持续天数
        last_cross_type:  gold/death/None
        last_cross_days:  最近交叉距今天数 (int) 或 None
        histogram:        柱状图数值 (DIF - DEA)
        reason:           None 或 "data_short"
    """
    MIN_DATA_LEN = MACD_SLOW + MACD_SIGNAL  # 26 + 9 = 35

    # 兜底：数据不足
    if len(nav_history) < MIN_DATA_LEN:
        return {
            "signal": "中性",
            "strength": "无",
            "trend": "无",
            "days": 0,
            "last_cross_type": None,
            "last_cross_days": None,
            "histogram": 0.0,
            "reason": "data_short",
        }

    prices = [_get_price(d) for d in nav_history]
    ema_fast = _calculate_ema(prices, MACD_FAST)
    ema_slow = _calculate_ema(prices, MACD_SLOW)
    min_len = min(len(ema_fast), len(ema_slow))
    dif = [f - s for f, s in zip(ema_fast[-min_len:], ema_slow[-min_len:])]
    dea = _calculate_ema(dif, MACD_SIGNAL)

    # 兜底：EMA 序列太短
    if len(dif) < 2 or len(dea) < 2:
        return {
            "signal": "中性",
            "strength": "无",
            "trend": "无",
            "days": 0,
            "last_cross_type": None,
            "last_cross_days": None,
            "histogram": 0.0,
            "reason": "data_short",
        }

    # ① 主信号判定
    hist = dif[-1] - dea[-1]       # 当前柱状图值
    hist_prev = dif[-2] - dea[-2]  # 昨日柱状图值

    if dif[-2] <= dea[-2] and dif[-1] > dea[-1]:
        signal = "金叉"
    elif dif[-2] >= dea[-2] and dif[-1] < dea[-1]:
        signal = "死叉"
    elif dif[-1] > dea[-1]:
        # 多头区域：柱状图扩大 → 多头，缩小 → 多头收敛
        signal = "多头收敛" if abs(hist) < abs(hist_prev) else "多头"
    elif dif[-1] < dea[-1]:
        # 空头区域：柱状图扩大 → 空头，缩小 → 空头收敛
        signal = "空头收敛" if abs(hist) < abs(hist_prev) else "空头"
    else:
        # DIF == DEA 极罕见
        signal = "多头"  # 零线附近偏多处理

    # ② 动能强度（柱状图绝对值分级）
    abs_hist = abs(hist)
    if abs_hist > 0.03:
        strength = "强"
    elif abs_hist > 0.01:
        strength = "中等"
    else:
        strength = "弱"

    # ③ 动能趋势（柱状图绝对值变化方向）
    abs_prev = abs(hist_prev)
    if abs_hist > abs_prev * 1.05:     # 扩大超过5%
        trend = "扩大"
    elif abs_hist < abs_prev * 0.95:   # 收敛超过5%
        trend = "收敛"
    else:
        trend = "稳定"

    # ④ 状态持续天数
    days = _count_macd_state_days(dif, dea)

    # ⑤ 最近交叉
    last_cross_type, last_cross_days = _find_last_cross(dif, dea)

    return {
        "signal": signal,
        "strength": strength,
        "trend": trend,
        "days": days,
        "last_cross_type": last_cross_type,
        "last_cross_days": last_cross_days,
        "histogram": round(hist, 6),
        "reason": None,   # 正常状态无 reason
    }


def _calculate_ema(prices: list, period: int) -> list:
    if len(prices) < period:
        return prices
    ema = []
    multiplier = 2 / (period + 1)
    ema.append(sum(prices[:period]) / period)
    for i in range(period, len(prices)):
        ema.append((prices[i] - ema[-1]) * multiplier + ema[-1])
    return ema


def _count_macd_state_days(dif: list, dea: list) -> int:
    """
    计算当前 MACD 状态（DIF 在 DEA 上方或下方）持续天数。
    从最新数据往回数，直到状态翻转为止。
    注意: dif 和 dea 长度可能不同（EMA缩减），使用尾部对齐索引。
    """
    if len(dif) < 2 or len(dea) < 2:
        return 0

    # 尾部对齐: dif 和 dea 从末尾往前比较
    # dea 比 dif 短（EMA(signal) 再缩减了 MACD_SIGNAL 个元素）
    effective_len = min(len(dif), len(dea))
    dif_offset = len(dif) - effective_len
    dea_offset = len(dea) - effective_len

    current_above = dif[-1] > dea[-1]
    days = 1

    for j in range(effective_len - 2, -1, -1):
        above_j = dif[dif_offset + j] > dea[dea_offset + j]
        if above_j == current_above:
            days += 1
        else:
            break

    return days


def _find_last_cross(dif: list, dea: list) -> tuple:
    """
    从最新数据往回查找最近的金叉/死叉事件。
    注意: dif 和 dea 长度可能不同（EMA缩减），使用尾部对齐索引。

    返回:
        (last_cross_type, last_cross_days)
        last_cross_type: "gold" / "death" / None
        last_cross_days: int 或 None（距今天数）
    """
    if len(dif) < 2 or len(dea) < 2:
        return (None, None)

    # 尾部对齐: dif 和 dea 从末尾往前比较
    effective_len = min(len(dif), len(dea))
    dif_offset = len(dif) - effective_len
    dea_offset = len(dea) - effective_len

    for j in range(effective_len - 2, -1, -1):
        di = dif_offset + j      # dif 索引
        di1 = dif_offset + j + 1  # dif 下一个索引
        dk = dea_offset + j      # dea 素引
        dk1 = dea_offset + j + 1  # dea 下一个索引

        if dif[di] <= dea[dk] and dif[di1] > dea[dk1]:
            return ("gold", effective_len - 1 - j)
        elif dif[di] >= dea[dk] and dif[di1] < dea[dk1]:
            return ("death", effective_len - 1 - j)

    return (None, None)


# ===========================================================
# 内部函数：震荡市判断
# ===========================================================

def _check_oscillation(nav_history: list) -> bool:
    trend = _calculate_ma20_trend(nav_history)
    return trend == "震荡"


# ===========================================================
# 持仓风控层 — Gate-P/Gate1/Gate2/Gate-E（优先级从高到低）
# ===========================================================

def check_panic_gate(fund_code: str = "") -> dict:
    """
    Gate-P 恐慌闸 — 全市场恐慌检测

    定义: 连续2天全市场跌幅>3% + 成交量萎缩>30%
    触发时: 所有推荐降级为"观望"，不再建议任何操作

    返回: {triggered, action, reason, consecutive_days, max_decline_pct, volume_shrink_pct}
    """
    try:
        from app.engine.data_fetcher import fetch_index_hist

        # 用沪深300代表全市场
        hist = fetch_index_hist("000300.SH", days=10)
        if not hist or len(hist) < 3:
            return {
                "triggered": False, "action": "hold",
                "label": "全市场恐慌（保命闸）",
                "reason": "", "consecutive_days": 0,
                "max_decline_pct": 0.0, "volume_shrink_pct": 0.0,
            }

        # 正序化
        if len(hist) >= 2:
            try:
                d0 = str(hist[0].get("date", ""))
                d1 = str(hist[-1].get("date", ""))
                if d0 and d1 and d0 > d1:
                    hist = list(reversed(hist))
            except Exception:
                pass

        closes = [float(d.get("close", 0)) for d in hist]
        volumes = [float(d.get("volume", d.get("vol", 0))) for d in hist]

        # 检查连续大跌
        consecutive_decline_days = 0
        max_decline_pct = 0.0
        for i in range(max(0, len(closes) - 5), len(closes) - 1):
            if closes[i] > 0 and closes[i + 1] > 0:
                decline = (closes[i + 1] - closes[i]) / closes[i]
                if decline <= -PANIC_DECLINE_THRESHOLD:
                    consecutive_decline_days += 1
                    max_decline_pct = min(max_decline_pct, decline)
                elif consecutive_decline_days > 0:
                    break  # 不连续了

        # 检查成交量萎缩
        volume_shrink_pct = 0.0
        if len(volumes) >= 3 and volumes[-3] > 0:
            recent_avg = sum(volumes[-2:]) / 2 if volumes[-2] > 0 else 0
            prior_avg = volumes[-3]
            if prior_avg > 0 and recent_avg > 0:
                volume_shrink_pct = 1.0 - recent_avg / prior_avg

        panic_triggered = (
            consecutive_decline_days >= PANIC_CONSECUTIVE_DAYS
            and volume_shrink_pct >= PANIC_VOLUME_SHRINK_THRESHOLD
        )

        if panic_triggered:
            logger.warning(
                f"Gate-P恐慌闸触发: {fund_code}, "
                f"连续大跌{consecutive_decline_days}天, "
                f"最大跌幅={max_decline_pct*100:.1f}%, "
                f"成交量萎缩={volume_shrink_pct*100:.1f}%"
            )

        return {
            "triggered": panic_triggered,
            "action": "hold" if panic_triggered else "hold",
            "label": "全市场恐慌（保命闸）",
            "reason": (
                f"全市场恐慌：连续{consecutive_decline_days}天大跌>={PANIC_DECLINE_THRESHOLD*100:.0f}%，"
                f"成交量萎缩{volume_shrink_pct*100:.1f}%，所有操作降级为观望"
                if panic_triggered else ""
            ),
            "consecutive_days": consecutive_decline_days,
            "max_decline_pct": round(max_decline_pct * 100, 2),
            "volume_shrink_pct": round(volume_shrink_pct * 100, 2),
        }

    except Exception as e:
        logger.warning(f"Gate-P恐慌检测失败: {e}")
        return {
            "triggered": False, "action": "hold",
            "label": "全市场恐慌（保命闸）",
            "reason": "", "consecutive_days": 0,
            "max_decline_pct": 0.0, "volume_shrink_pct": 0.0,
        }


def check_holding_gates(
    signal_level: str,
    sector_track: Optional[str],
    nav_history: list,
    ma20_trend: str,
    current_pct: float,
    fund_code: str = "",
) -> dict:
    """
    持仓风控层 — 结构化 Gate 输出（V2）

    优先级：Gate-P（恐慌闸）> Gate1（极端回撤20%清仓）> Gate2（趋势破位清仓）> Gate-E（E级提示）

    contrarian轨道豁免Gate2但不豁免Gate-P/Gate1/Gate-E：
    S+/S信号逆向买入时趋势必然在下降，Gate2会立刻清仓导致逆向逻辑作废

    返回结构化 dict，包含：
    {
        gate_p: {triggered, action, reason, consecutive_days, max_decline_pct, volume_shrink_pct},
        gate_1: {triggered, action, trigger_price, current_distance_pct, drawdown, reason},
        gate_2: {triggered, action, trigger_price, current_distance_pct, drawdown, reason, exempted, exempt_reason},
        gate_e: {triggered, action, reason},
        overall_status: "panic" | "stop_loss" | "warning" | "normal",
        sector_track: str | None,
        # DEPRECATED: gate_triggered 保留兼容值，请改用 gate_p/gate_1/gate_2/gate_e
        gate_triggered: dict | None,
    }
    """
    if not nav_history:
        return _build_gate_structure(sector_track=sector_track)

    # ── Gate-P 恐慌闸检测（最高优先级）──
    gate_p = check_panic_gate(fund_code=fund_code)
    gate_p_triggered = gate_p.get("triggered", False)

    # 计算回撤（60日窗口，max→current）
    drawdown = _calculate_drawdown(nav_history, DRAWDOWN_WINDOW)

    # 计算当前净值与MA20价位
    prices = [_get_price(d) for d in nav_history]
    current_price = prices[-1] if prices else 0.0
    window_prices = prices[-DRAWDOWN_WINDOW:] if len(prices) >= DRAWDOWN_WINDOW else prices
    peak_price = max(window_prices) if window_prices else current_price

    ma20_prices = prices[-20:] if len(prices) >= 20 else prices
    ma20_price = sum(ma20_prices) / len(ma20_prices) if ma20_prices else 0.0

    # ── Gate1 计算 ──
    gate1_trigger_price = peak_price * (1 - GATE1_DRAWDOWN_THRESHOLD) if peak_price > 0 else None
    gate1_distance_pct = None
    if gate1_trigger_price and current_price > 0:
        # 负=距触发还有空间（安全），正=已超过触发阈值（触发）
        gate1_distance_pct = round((GATE1_DRAWDOWN_THRESHOLD - drawdown) * 100, 2) * -1
    gate1_triggered = drawdown >= GATE1_DRAWDOWN_THRESHOLD

    if gate1_triggered:
        logger.warning(
            f"Gate1触发: {fund_code}, 回撤={drawdown:.2%} >= {GATE1_DRAWDOWN_THRESHOLD:.0%}，无条件强制清仓"
        )

    # ── Gate2 计算 ──
    gate2_exempted = (sector_track == "contrarian")
    gate2_exempt_reason = "逆向策略逆趋势布局，MA20下降为正常特征" if gate2_exempted else None
    gate2_trigger_price = ma20_price if ma20_price > 0 else None
    gate2_distance_pct = None
    if gate2_trigger_price and current_price > 0:
        gate2_distance_pct = round((current_price - gate2_trigger_price) / gate2_trigger_price * 100, 2)

    gate2_triggered = False
    if not gate2_exempted:
        if ma20_trend == "下降" and drawdown >= GATE2_DRAWDOWN_THRESHOLD:
            gate2_triggered = True
            logger.warning(
                f"Gate2触发: {fund_code}, MA20趋势下降+回撤={drawdown:.2%} >= "
                f"{GATE2_DRAWDOWN_THRESHOLD:.0%}，趋势破位清仓"
            )
    else:
        logger.info(f"Gate2跳过: {fund_code}, contrarian轨道豁免（逆向买入信号不应被下降趋势阻断）")

    # ── Gate-E 计算 ──
    gate_e_triggered = (signal_level == "E")
    if gate_e_triggered:
        logger.info(f"Gate-E触发: {fund_code}, 极度贪婪信号(E)，仅提示不减仓")

    # ── overall_status 优先级硬编码 ──
    # panic > stop_loss > warning > normal
    if gate_p_triggered:
        overall_status = "panic"
    elif gate1_triggered or gate2_triggered:
        overall_status = "stop_loss"
    elif gate_e_triggered:
        overall_status = "warning"
    elif gate2_distance_pct is not None and gate2_distance_pct <= 3.0:
        # 距MA20 3%以内 → warning（豁免时标注豁免，非豁免时正常预警）
        overall_status = "warning"
    else:
        overall_status = "normal"

    # ── 构建结构化 gate 对象 ──
    gate1_obj = {
        "triggered": gate1_triggered,
        "action": "clear" if gate1_triggered else "hold",
        "label": "极端回撤（保命线）",
        "trigger_price": round(gate1_trigger_price, 4) if gate1_trigger_price else None,
        "current_distance_pct": gate1_distance_pct,
        "drawdown": round(drawdown, 4),
        "description": f"阶段回撤 >= {GATE1_DRAWDOWN_THRESHOLD*100:.0f}%",
        "reason": (
            f"极端回撤{drawdown*100:.1f}%>={GATE1_DRAWDOWN_THRESHOLD*100:.0f}%，无条件清仓"
            if gate1_triggered else ""
        ),
    }

    gate2_obj = {
        "triggered": gate2_triggered,
        "action": "clear" if gate2_triggered else "hold",
        "label": "趋势破位（离场线）",
        "trigger_price": round(gate2_trigger_price, 4) if gate2_trigger_price else None,
        "current_distance_pct": gate2_distance_pct,
        "drawdown": round(drawdown, 4),
        "description": f"跌破MA20 + 回撤 >= {GATE2_DRAWDOWN_THRESHOLD*100:.0f}%",
        "exempted": gate2_exempted,
        "exempt_reason": gate2_exempt_reason,
        "reason": (
            f"跌破MA20且回撤{drawdown*100:.1f}%>={GATE2_DRAWDOWN_THRESHOLD*100:.0f}%，趋势破位清仓"
            if gate2_triggered else (
                "逆向轨道豁免趋势破位检测" if gate2_exempted else ""
            )
        ),
    }

    gate_e_obj = {
        "triggered": gate_e_triggered,
        "action": "hold",  # Gate-E 永远是提示闸，不强制清仓
        "label": "情绪过热（过热预警）",
        "trigger_price": None,  # 无固定价位
        "description": "信号等级达到 E（极度贪婪）",
        "reason": "进入极度贪婪区间，紧盯趋势破位信号" if gate_e_triggered else "",
    }

    # ── DEPRECATED: gate_triggered 兼容字段 ──
    # 新代码请改用 gate_1 / gate_2 / gate_e
    gate_triggered_compat = None
    if gate1_triggered:
        gate_triggered_compat = {
            "gate": "gate-1", "action": "clear", "adjusted_pct": 0.0,
            "reason": gate1_obj["reason"], "drawdown": drawdown,
        }
    elif gate2_triggered:
        gate_triggered_compat = {
            "gate": "gate-2", "action": "clear", "adjusted_pct": 0.0,
            "reason": gate2_obj["reason"], "drawdown": drawdown,
        }
    elif gate_e_triggered:
        gate_triggered_compat = {
            "gate": "gate-e", "action": "hold", "adjusted_pct": current_pct,
            "reason": gate_e_obj["reason"],
        }

    return {
        "gate_p": gate_p,
        "gate_1": gate1_obj,
        "gate_2": gate2_obj,
        "gate_e": gate_e_obj,
        "overall_status": overall_status,
        "sector_track": sector_track,
        # DEPRECATED: 保留兼容值，请改用 gate_1/gate_2/gate_e
        "gate_triggered": gate_triggered_compat,
    }


def _build_gate_structure(sector_track = None) -> dict:
    """构建空数据时的默认结构化 Gate 对象"""
    empty_gate_p = {
        "triggered": False, "action": "hold", "label": "全市场恐慌（保命闸）",
        "reason": "", "consecutive_days": 0, "max_decline_pct": 0.0, "volume_shrink_pct": 0.0,
    }
    empty_gate1 = {
        "triggered": False, "action": "hold", "label": "极端回撤（保命线）",
        "trigger_price": None, "current_distance_pct": None, "drawdown": 0.0,
        "description": f"阶段回撤 >= {GATE1_DRAWDOWN_THRESHOLD*100:.0f}%", "reason": "",
    }
    empty_gate2 = {
        "triggered": False, "action": "hold", "label": "趋势破位（离场线）",
        "trigger_price": None, "current_distance_pct": None, "drawdown": 0.0,
        "description": f"跌破MA20 + 回撤 >= {GATE2_DRAWDOWN_THRESHOLD*100:.0f}%",
        "exempted": (sector_track == "contrarian"),
        "exempt_reason": "逆向策略逆趋势布局，MA20下降为正常特征" if sector_track == "contrarian" else None,
        "reason": "",
    }
    empty_gate_e = {
        "triggered": False, "action": "hold", "label": "情绪过热（过热预警）",
        "trigger_price": None, "description": "信号等级达到 E（极度贪婪）", "reason": "",
    }
    return {
        "gate_p": empty_gate_p,
        "gate_1": empty_gate1,
        "gate_2": empty_gate2,
        "gate_e": empty_gate_e,
        "overall_status": "normal",
        "sector_track": sector_track,
        "gate_triggered": None,
    }


# ===========================================================
# 建仓准入层 — Gate3
# ===========================================================

def check_admission_gate(
    signal_level: str,
    sector_track: Optional[str],
    confidence: int,
    gate2_triggered: bool,
    fund_code: str = "",
) -> dict:
    """
    建仓准入层 — 只管能不能新买，不影响已有持仓

    Gate3（准入排除闸）：以下任一条件满足 → 不准入
    - 信号E级（极度贪婪区间不适合建仓）
    - Gate2已触发（趋势破位，不宜新建仓）
    - 置信度≤1星（信号不可靠）
    - sector_track=excluded（板块被排除）

    返回 {"admitted": bool, "reason": str}
    """
    if signal_level == "E":
        logger.info(f"Gate3准入拒绝: {fund_code}, 信号E级（极度贪婪），不准入")
        return {"admitted": False, "reason": "信号E级（极度贪婪），不准入"}

    if gate2_triggered:
        logger.info(f"Gate3准入拒绝: {fund_code}, Gate2趋势破位已触发，不准入")
        return {"admitted": False, "reason": "Gate2趋势破位已触发，不准入"}

    if confidence <= 1:
        logger.info(f"Gate3准入拒绝: {fund_code}, 置信度过低（{confidence}星），不准入")
        return {"admitted": False, "reason": f"置信度过低（{confidence}星≤1），不准入"}

    if sector_track == "excluded":
        logger.info(f"Gate3准入拒绝: {fund_code}, 板块轨道excluded，不准入")
        return {"admitted": False, "reason": "板块轨道excluded，不准入"}

    return {"admitted": True, "reason": ""}


# ===========================================================
# 内部函数：操作建议生成
# ===========================================================

def _generate_operation_suggestion(
    trend_signal: str,
    macd_signal: str,
    oscillation_silence: bool,
    gate_triggered: Optional[dict],
    sector_track: Optional[str] = None,
) -> str:
    """生成操作建议"""
    # 支持新结构化 gate 对象 和旧兼容格式
    if gate_triggered:
        if isinstance(gate_triggered, dict) and "gate_1" in gate_triggered:
            # 新结构化格式
            overall = gate_triggered.get("overall_status", "normal")
            if overall == "panic":
                return "🚨 全市场恐慌：所有操作降级为观望，不建议任何买入或减仓操作"
            elif overall == "stop_loss":
                if gate_triggered.get("gate_1", {}).get("triggered"):
                    reason = gate_triggered["gate_1"]["reason"]
                else:
                    reason = gate_triggered.get("gate_2", {}).get("reason", "止损触发")
                return f"⚠️ {reason}"
            elif overall == "warning":
                if gate_triggered.get("gate_e", {}).get("triggered"):
                    return f"⚠️ {gate_triggered['gate_e']['reason']}"
                elif gate_triggered.get("gate_2", {}).get("exempted"):
                    return "⚠️ 逆向轨道接近MA20，请关注后续走势"
                return "⚠️ 预警状态，请谨慎操作"
        else:
            # 旧兼容格式（DEPRECATED）
            gate = gate_triggered.get("gate", "")
            reason = gate_triggered.get("reason", "")
            if gate in ("gate-1", "gate-2", "gate-e"):
                return f"⚠️ {reason}"

    # contrarian 轨道提示
    if sector_track == "contrarian":
        if trend_signal == "下降":
            return "📉 逆向轨道：板块处于恐慌底部，趋势下降但属逆向买入机会，可适度布局"

    if oscillation_silence:
        return "📊 震荡市，建议持仓观望，不操作"

    # 上升 + MACD 组合
    if trend_signal == "上升" and macd_signal == "金叉":
        return "📈 趋势向上+MACD金叉，加仓窗口"
    elif trend_signal == "上升" and macd_signal == "多头":
        return "📈 趋势向上+MACD多头运行，建议持有或适度加仓"
    elif trend_signal == "上升" and macd_signal == "多头收敛":
        return "📈 趋势向上但动能减弱，建议持有观察，暂不加仓"
    elif trend_signal == "上升" and macd_signal in ("死叉", "空头", "空头收敛"):
        return "📈 趋势向上但MACD转空，建议谨慎持有，关注后续走势"

    # 下降 + MACD 组合
    elif trend_signal == "下降" and macd_signal == "死叉":
        return "📉 趋势向下+MACD死叉，减仓信号"
    elif trend_signal == "下降" and macd_signal == "空头":
        return "📉 趋势向下+MACD空头运行，建议减仓防守"
    elif trend_signal == "下降" and macd_signal == "空头收敛":
        return "📉 趋势向下但动能减弱，可能接近底部，持有观察反弹信号"
    elif trend_signal == "下降" and macd_signal in ("金叉", "多头", "多头收敛"):
        return "📉 趋势向下但MACD转多，关注反弹机会，暂不急于加仓"

    # 震荡 + MACD 组合
    elif trend_signal == "震荡" and macd_signal in ("金叉", "多头", "多头收敛"):
        return "📊 震荡行情+MACD偏多，可适度持有，不急于加仓"
    elif trend_signal == "震荡" and macd_signal in ("死叉", "空头", "空头收敛"):
        return "📊 震荡行情+MACD偏空，建议谨慎，观望为主"
    elif trend_signal == "震荡":
        return "📊 震荡行情，MACD多空反复，观望为主，不急于加仓减仓"

    # 兜底
    else:
        return "📊 数据不足，建议观望"


# ===========================================================
# 内部函数：趋势解读文案生成
# ===========================================================

def _generate_trend_narrative(
    trend_signal: str,
    macd_signal: str,
    oscillation_silence: bool,
    gate_triggered: Optional[dict],
    nav_history: list,
    sector_track: Optional[str] = None,
) -> str:
    # 支持新结构化 gate 对象 和旧兼容格式
    if gate_triggered:
        if isinstance(gate_triggered, dict) and "gate_1" in gate_triggered:
            # 新结构化格式
            overall = gate_triggered.get("overall_status", "normal")
            if overall == "panic":
                return "🚨 全市场恐慌信号：连续大幅下跌+成交量萎缩，市场系统性风险极高，所有操作降级为观望"
            elif overall == "stop_loss":
                if gate_triggered.get("gate_1", {}).get("triggered"):
                    reason = gate_triggered["gate_1"]["reason"]
                else:
                    reason = gate_triggered.get("gate_2", {}).get("reason", "止损触发")
                return f"⚠️ {reason}"
            elif overall == "warning":
                if gate_triggered.get("gate_e", {}).get("triggered"):
                    return f"⚠️ {gate_triggered['gate_e']['reason']}"
                elif gate_triggered.get("gate_2", {}).get("exempted"):
                    return "⚠️ 逆向轨道接近MA20，价格接近趋势线，请关注走势变化"
                return "⚠️ 预警状态，请谨慎操作"
        else:
            # 旧兼容格式（DEPRECATED）
            gate = gate_triggered.get("gate", "")
            reason = gate_triggered.get("reason", "")
            if gate in ("gate-1", "gate-2", "gate-e"):
                return f"⚠️ {reason}"

    # contrarian 轨道叙事
    if sector_track == "contrarian":
        if trend_signal == "下降":
            return "📉 逆向轨道信号：板块处于恐慌底部区域，MA20下降属预期行为，逆向布局机会"
        elif trend_signal == "震荡":
            return "📊 逆向轨道信号：板块底部震荡，等待底部确认后可适度布局"

    if oscillation_silence:
        return "📊 当前为震荡市，建议持仓观望，避免频繁交易"

    # 上升 + MACD 组合
    if trend_signal == "上升":
        if macd_signal == "金叉":
            return "📈 趋势向上，MACD金叉确认，适合加仓"
        elif macd_signal == "多头":
            return "📈 趋势向上，MACD多头运行，趋势健康可持有"
        elif macd_signal == "多头收敛":
            return "📈 趋势向上但MACD动能收敛，多头趋势可能减弱，需关注"
        elif macd_signal in ("死叉", "空头", "空头收敛"):
            return "📈 趋势向上但MACD转向空头，上涨动力不足，建议谨慎"

    # 下降 + MACD 组合
    elif trend_signal == "下降":
        if macd_signal == "死叉":
            return "📉 趋势向下，MACD死叉确认，建议减仓"
        elif macd_signal == "空头":
            return "📉 趋势向下，MACD空头运行，下跌动能仍强"
        elif macd_signal == "空头收敛":
            return "📉 趋势向下但MACD动能收敛，下跌可能接近尾声"
        elif macd_signal in ("金叉", "多头", "多头收敛"):
            return "📉 趋势向下但MACD出现多头信号，可能迎来反弹"

    # 震荡 + MACD 组合
    elif trend_signal == "震荡":
        if macd_signal in ("金叉", "多头", "多头收敛"):
            return "📊 震荡整理，MACD偏多信号，等待方向突破再操作"
        elif macd_signal in ("死叉", "空头", "空头收敛"):
            return "📊 震荡整理，MACD偏空信号，观望为主"
        else:
            return "📊 震荡行情，MACD多空反复，观望等待方向确认"

    # 兜底
    else:
        return "📊 数据不足，暂无法判断趋势"


# ===========================================================
# 辅助函数：默认响应
# ===========================================================

def _get_default_response(reason: str) -> Dict:
    return {
        "trend_signal": "震荡",
        "macd_signal": "中性",
        "macd_detail": {
            "signal": "中性",
            "strength": "无",
            "trend": "无",
            "days": 0,
            "last_cross_type": None,
            "last_cross_days": None,
            "histogram": 0.0,
            "reason": "data_short",
        },
        "oscillation_silence": True,
        "gate_triggered": None,   # DEPRECATED 兼容字段
        "gates": _build_gate_structure(sector_track=None),
        "admission_gate": {"admitted": True, "reason": ""},
        "operation_suggestion": "数据不足，建议观望",
        "trend_narrative": f"⚠️ {reason}，暂无法判断趋势",
        "sector_track": None,
    }


__all__ = ["calculate_position_v5", "check_holding_gates", "check_admission_gate"]
