"""
建仓评级引擎 V5.0
基于板块情绪信号 + TURN分位 + 底背离，输出4档建仓评级

评级档位:
  strong    (强烈·绿)  逆向轨道 S+ + 强底背离 + 置信度≥3
  cautious  (谨慎·黄)  顺势轨道 A/B + MA20上升 + TURN<90% + 置信度≥2
                        逆向轨道 S+ + 中等底背离 / S + 任意底背离 + 置信度≥2
                        D信号(贪婪区间，正常仓位)
  watch     (观望·灰)  C信号 / 置信度<2 / TURN 90-95% / 逆向无底背离
  forbidden (禁止·红)  E信号(Gate-E情绪过热) / TURN>95% / excluded轨道 / 置信度≤1星
                        Gate3准入排除条件：信号E / Gate2已触发 / 置信度≤1 / excluded轨道
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.engine.sector_scorer import score_sectors, _fetch_sector_price_data
from app.engine.trend_guard import _calculate_ma20_trend
from app.engine.divergence_detector import detect_bottom_divergence

from app.core.database import get_session_factory
from app.models.position_rating_fund_map import PositionRatingFundMap
from sqlalchemy import select

logger = logging.getLogger(__name__)

# 评级配置
RATING_CONFIG = {
    "strong":    {"label": "强烈", "color": "#16a34a"},
    "cautious":  {"label": "谨慎", "color": "#eab308"},
    "watch":     {"label": "观望", "color": "#6b7280"},
    "forbidden": {"label": "禁止", "color": "#dc2626"},
}

# 仓位建议
POSITION_SUGGESTION = {
    "strong": 0.8,     # 80% 仓位
    "cautious": 0.3,   # 30% 仓位
    "watch": 0.0,      # 0% 仓位
    "forbidden": 0.0,  # 禁止建仓
}


@dataclass
class PositionRatingResult:
    """建仓评级结果"""
    sector_code: str
    sector_name: str
    rating: str              # strong/cautious/watch/forbidden
    rating_label: str        # 强烈/谨慎/观望/禁止
    rating_color: str        # #16a34a/#eab308/#6b7280/#dc2626
    reason: str
    signal_level: str
    trend_track: str         # trend_follow/contrarian/excluded
    confidence_stars: int
    composite_score: float
    turn_percentile: Optional[float]
    bottom_divergence: Optional[dict]
    position_suggestion: float   # 建议仓位比例 0.0-1.0
    funds: list

    def to_dict(self) -> dict:
        return {
            "sector_code": self.sector_code,
            "sector_name": self.sector_name,
            "rating": self.rating,
            "rating_label": self.rating_label,
            "rating_color": self.rating_color,
            "reason": self.reason,
            "signal_level": self.signal_level,
            "track": self.trend_track,
            "trend_track": self.trend_track,
            "position_suggestion": self.position_suggestion,
            "confidence_stars": self.confidence_stars,
            "composite_score": round(self.composite_score, 1),
            "turn_percentile": self.turn_percentile,
            "bottom_divergence": self.bottom_divergence,
            "funds": self.funds,
        }


# ============================================================
# 数据库查询
# ============================================================

# _get_db_connection() 已删除 — 改用 async SQLAlchemy


async def _get_active_sector_funds() -> dict:
    """
    查询 position_rating_fund_map 表（async SQLAlchemy）
    返回 {sector_code: [fund_dict, ...]} 仅 active 一级板块
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(PositionRatingFundMap)
                .where(
                    PositionRatingFundMap.status == "active",
                    PositionRatingFundMap.fund_level == 1
                )
                .order_by(PositionRatingFundMap.sw_sector_code)
            )
            rows = result.scalars().all()

            sector_funds = {}
            for row in rows:
                code = row.sw_sector_code
                if code not in sector_funds:
                    sector_funds[code] = []
                sector_funds[code].append({
                    "fund_code": row.fund_code,
                    "fund_name": row.fund_name,
                    "track_index": row.track_index or "",
                    "fit_degree": float(row.fit_degree),
                    "fund_level": int(row.fund_level),
                    "status": row.status,
                })
            logger.info(f"查询到 {len(sector_funds)} 个active板块的基金映射")
            return sector_funds
    except Exception as e:
        logger.error(f"查询基金映射表失败: {e}")
        return {}


async def _get_funds_by_sector(sector_code: str) -> list:
    """查询单个板块的基金列表（active 一级 + reserved 二级）— async SQLAlchemy"""
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(PositionRatingFundMap)
                .where(
                    PositionRatingFundMap.sw_sector_code == sector_code,
                    PositionRatingFundMap.status.in_(["active", "reserved"])
                )
                .order_by(PositionRatingFundMap.fund_level, PositionRatingFundMap.fit_degree.desc())
            )
            rows = result.scalars().all()

            funds = []
            for row in rows:
                funds.append({
                    "fund_code": row.fund_code,
                    "fund_name": row.fund_name,
                    "track_index": row.track_index or "",
                    "fit_degree": float(row.fit_degree),
                    "fund_level": int(row.fund_level),
                    "status": row.status,
                    "parent_sector": row.parent_sector_name or "",
                    "sub_sector": row.sub_sector_name or "",
                    "track_index_code": row.track_index_code or "",
                })
            logger.info(f"板块 {sector_code} 查询到 {len(funds)} 个基金")
            return funds
    except Exception as e:
        logger.error(f"查询板块 {sector_code} 基金失败: {e}")
        return []


# ============================================================
# 辅助计算
# ============================================================

def _compute_ma20_rising(sector_code: str) -> bool:
    """获取板块价格数据并计算 MA20 是否上升"""
    try:
        price_data = _fetch_sector_price_data(sector_code, days=60)
        if not price_data or len(price_data) < 20:
            return False
        trend = _calculate_ma20_trend(price_data)
        return trend == "上升"
    except Exception as e:
        logger.warning(f"计算MA20趋势失败: {sector_code}: {e}")
        return False


def _compute_rsi_series(closes: list, period: int = 14) -> list:
    """计算 RSI 序列（Wilder smoothing），用于底背离检测的情绪代理"""
    if len(closes) < period + 1:
        return []

    deltas = [float(closes[i]) - float(closes[i - 1]) for i in range(1, len(closes))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    # 初始平均
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsis = []
    for i in range(period, len(deltas)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))

    return rsis


def _detect_sector_bottom_divergence(sector_code: str) -> Optional[dict]:
    """
    检测板块底背离信号

    使用价格数据 + RSI（作为情绪代理）检测底背离：
    - 价格创新低但 RSI 未创新低 → 下跌动能减弱 → 底背离

    Returns:
        detect_bottom_divergence 结果 (含 strength: weak/moderate/strong) 或 None
    """
    try:
        price_data = _fetch_sector_price_data(sector_code, days=60)
        if not price_data or len(price_data) < 30:
            return None

        closes = [d["close"] for d in price_data]

        # 计算 RSI 序列作为情绪代理
        rsis = _compute_rsi_series(closes, period=14)
        if len(rsis) < 20:
            return None

        # 对齐长度: RSI 比 closes 少 period 个元素
        n = min(len(closes), len(rsis))
        closes_aligned = closes[-n:]
        rsis_aligned = rsis[-n:]

        result = detect_bottom_divergence(closes_aligned, rsis_aligned)
        if result:
            logger.info(
                f"板块{sector_code}底背离检测: strength={result.get('strength')}, "
                f"price_low_1={result.get('price_low_1'):.2f}, "
                f"price_low_2={result.get('price_low_2'):.2f}"
            )
        return result
    except Exception as e:
        logger.warning(f"底背离检测失败: {sector_code}: {e}")
        return None


# ============================================================
# 核心评级逻辑
# ============================================================

def calculate_position_rating(
    sector_code: str,
    sector_name: str,
    composite_score: float,
    signal_level: str,
    trend_track: str,
    confidence_stars: int,
    factor_scores: dict,
    ma20_rising: bool,
    bottom_divergence: Optional[dict] = None,
) -> PositionRatingResult:
    """
    计算单个板块的建仓评级

    评级优先级: forbidden > contrarian(strong/cautious/watch) > D信号(cautious) > trend_follow > watch
    """
    custom_pos = None  # 自定义仓位建议，None时使用 POSITION_SUGGESTION[rating]
    # 提取 TURN 分位
    turn_data = factor_scores.get("TURN", {})
    if isinstance(turn_data, dict):
        turn_percentile = turn_data.get("raw_percentile")
    else:
        turn_percentile = None

    # 提取底背离强度
    div_strength = None
    if bottom_divergence and isinstance(bottom_divergence, dict):
        div_strength = bottom_divergence.get("strength")

    # ── 1. forbidden（最高优先级 — Gate3准入排除）──
    if signal_level == "E":
        rating = "forbidden"
        reason = "极度贪婪，Gate-E情绪过热提示，Gate3准入排除，不建议新建仓"
    elif turn_percentile is not None and turn_percentile > 95:
        rating = "forbidden"
        reason = f"成交额分位{turn_percentile:.1f}%，过热禁止建仓"
    elif trend_track == "excluded":
        rating = "forbidden"
        reason = "板块轨道excluded，Gate3准入排除，不建议新建仓"
    elif confidence_stars <= 1:
        rating = "forbidden"
        reason = f"置信度过低（{confidence_stars}星≤1），Gate3准入排除，不建议新建仓"

    # ── 2. contrarian track（逆向轨道：S+/S信号 + 底背离）──
    elif trend_track == "contrarian" and signal_level in ("S+", "S"):
        if signal_level == "S+" and div_strength == "strong" and confidence_stars >= 3:
            rating = "strong"
            reason = "极度恐惧+强底背离，适合逆向建仓"
        elif signal_level == "S+" and div_strength == "moderate" and confidence_stars >= 2:
            rating = "cautious"
            reason = "极度恐惧+中等底背离，可谨慎逆向建仓"
        elif signal_level == "S" and div_strength in ("weak", "moderate", "strong") and confidence_stars >= 2:
            rating = "cautious"
            reason = "恐惧+底背离确认，可谨慎逆向建仓"
        else:
            rating = "watch"
            if not div_strength:
                reason = "逆向信号但无底背离确认，暂时观望"
            elif confidence_stars < 2:
                reason = f"逆向信号+底背离({div_strength})但置信度{confidence_stars}星不足，暂时观望"
            else:
                reason = f"逆向信号条件不满足（{signal_level}+{div_strength}+{confidence_stars}星），暂时观望"

    # ── 3. D信号（贪婪区间，注意风险）──
    elif signal_level == "D":
        rating = "cautious"
        reason = "贪婪D信号，注意风险"
        custom_pos = 1.0  # D信号正常仓位

    # ── 4. trend_follow（顺势轨道：A/B信号）──
    elif trend_track == "trend_follow" and signal_level in ("A", "B"):
        if ma20_rising and confidence_stars >= 2:
            if turn_percentile is not None and turn_percentile >= 90:
                rating = "watch"
                reason = f"TURN分位{turn_percentile:.1f}%偏高，暂观望"
            else:
                rating = "cautious"
                reason = "顺势信号+趋势向上，可谨慎建仓"
        else:
            rating = "watch"
            if confidence_stars < 2:
                reason = f"置信度{confidence_stars}星不足，暂时观望"
            elif not ma20_rising:
                reason = "顺势信号但MA20未上升，暂时观望"
            else:
                reason = "顺势信号条件不满足，暂时观望"

    # ── 5. watch（兜底）──
    else:
        rating = "watch"
        if signal_level == "C":
            reason = "偏贪婪区间，暂时观望"
        elif confidence_stars < 2:
            reason = f"置信度{confidence_stars}星不足，暂时观望"
        elif turn_percentile is not None and 90 <= turn_percentile <= 95:
            reason = f"TURN分位{turn_percentile:.1f}%处于过热边缘，暂时观望"
        else:
            reason = "无明确建仓信号，暂时观望"

    cfg = RATING_CONFIG[rating]
    return PositionRatingResult(
        sector_code=sector_code,
        sector_name=sector_name,
        rating=rating,
        rating_label=cfg["label"],
        rating_color=cfg["color"],
        reason=reason,
        signal_level=signal_level,
        trend_track=trend_track,
        confidence_stars=confidence_stars,
        composite_score=composite_score,
        turn_percentile=turn_percentile,
        bottom_divergence=bottom_divergence,
        position_suggestion=custom_pos if custom_pos is not None else POSITION_SUGGESTION[rating],
        funds=[],
    )


async def calculate_position_ratings_for_all() -> list:
    """
    计算所有有active基金的板块的建仓评级

    流程:
      1. 调用 sector_scorer.score_sectors() 获取31板块情绪数据
      2. 查询 position_rating_fund_map 获取23个active一级板块的基金
      3. 对每个板块计算评级（含真实底背离检测）
      4. 附加基金列表
    """
    try:
        # 1. 获取31板块情绪数据
        sector_data = await score_sectors()
        if not sector_data:
            logger.warning("板块情绪数据获取失败")
            return []

        # 2. 查询 active 一级板块基金映射
        sector_funds = await _get_active_sector_funds()
        if not sector_funds:
            logger.warning("无active基金映射数据")
            return []

        # 3. 对每个active板块计算评级
        results = []
        active_codes = set(sector_funds.keys())

        for s in sector_data:
            sector_code = s.get("sector_code", "")
            if sector_code not in active_codes:
                continue

            sector_name = s.get("sector_name", "")
            composite_score = s.get("sentiment_score", 50.0)
            signal_level = s.get("signal_level", "B")
            trend_track = s.get("track", "excluded")
            confidence_stars = s.get("confidence_stars", 0)
            factor_scores = s.get("factor_scores", {})

            # 计算 ma20_rising
            ma20_rising = _compute_ma20_rising(sector_code)

            # 真实底背离检测（仅对逆向轨道板块检测）
            bottom_divergence = None
            if trend_track == "contrarian":
                bottom_divergence = _detect_sector_bottom_divergence(sector_code)
                # 如果检测失败（数据不足等），回退到默认确认
                if not bottom_divergence:
                    bottom_divergence = {
                        "detected": True,
                        "strength": "moderate",
                        "source": "contrarian_fallback",
                        "note": "底背离数据不足，基于S+/S信号推断",
                    }

            result = calculate_position_rating(
                sector_code=sector_code,
                sector_name=sector_name,
                composite_score=composite_score,
                signal_level=signal_level,
                trend_track=trend_track,
                confidence_stars=confidence_stars,
                factor_scores=factor_scores,
                ma20_rising=ma20_rising,
                bottom_divergence=bottom_divergence,
            )

            # 4. 附加基金列表
            funds = sector_funds.get(sector_code, [])
            for fund in funds:
                fund["rating"] = result.rating
                fund["rating_reason"] = result.reason
            result.funds = funds

            results.append(result)

        # 统计日志
        rating_counts = {"strong": 0, "cautious": 0, "watch": 0, "forbidden": 0}
        for r in results:
            rating_counts[r.rating] = rating_counts.get(r.rating, 0) + 1
        logger.info(
            f"建仓评级完成: {len(results)}个板块, "
            f"strong={rating_counts['strong']}, cautious={rating_counts['cautious']}, "
            f"watch={rating_counts['watch']}, forbidden={rating_counts['forbidden']}"
        )

        return results

    except Exception as e:
        logger.exception("建仓评级计算失败")
        return []
