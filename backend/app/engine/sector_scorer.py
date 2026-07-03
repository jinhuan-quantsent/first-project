#!/usr/bin/env python3
"""
板块情绪评分引擎 V5.0 — 三层流水线 + 双轨制板块过滤器

V5.0 架构:
  层1 分位数标准化: factor_history → percentile (0-1)
  层2 Sigmoid映射: percentile → sigmoid_score (0-100)
  层3 分歧度动态加权: weighted_sum × penalty → composite_score

5因子配置 (IC/IR 验证后定稿):
  TURN (0.28, fear)  - 成交额相对强度
  VOL  (0.25, greed) - 20日年化波动率
  NHNL (0.20, greed) - 20日新高新低净占比
  RSI  (0.15, greed) - 14日RSI
  DIV  (0.12, fear)  - 跨板块分歧度 (市场级)

双轨制板块过滤器:
  正常轨道: 信号A/B/C + MA20上升 + 置信度≥2星 + 完整度≥0.90
  逆向轨道: S+(置信度≥3)/S(置信度≥2) + 底背离 + 完整度≥0.90
  排除: 都不满足
"""
import logging
import math
import time
import warnings
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, timedelta

import numpy as np

from app.core.config import settings
from app.engine.confidence import ConfidenceEngine
from app.engine.divergence_detector import DivergenceDetector
from app.engine.trend_guard import _calculate_ma20_trend

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')

# ============================================================
# V5 板块因子配置 (独立于 V5_FACTOR_CONFIG)
# ============================================================

V5_SECTOR_FACTOR_CONFIG = {
    "TURN": {"weight": 0.28, "direction": "fear",  "sigmoid_c": 0.5, "sigmoid_k": 2.0, "reverse": True},
    "VOL":  {"weight": 0.25, "direction": "greed", "sigmoid_c": 0.5, "sigmoid_k": 3.0, "reverse": False},
    "NHNL": {"weight": 0.20, "direction": "greed", "sigmoid_c": 0.6, "sigmoid_k": 2.5, "reverse": False},
    "RSI":  {"weight": 0.15, "direction": "greed", "sigmoid_c": 0.5, "sigmoid_k": 2.5, "reverse": False},
    "DIV":  {"weight": 0.12, "direction": "fear",  "sigmoid_c": 0.5, "sigmoid_k": 2.0, "reverse": True},
}

SECTOR_FACTOR_NAMES = list(V5_SECTOR_FACTOR_CONFIG.keys())
NON_DIV_FACTORS = [f for f in SECTOR_FACTOR_NAMES if f != "DIV"]
DIV_INDEX_CODE = "SW_L1_DIV"
COLD_START_MIN_SAMPLES = 252

# 信号等级
_LEVELS = ["S+", "S", "A", "B", "C", "D", "E"]
_BOUNDARIES = settings.V5_SIGNAL_BOUNDARIES
_LEVEL_MEANINGS = {
    "S+": "极度恐惧", "S": "恐惧", "A": "偏恐惧", "B": "中性",
    "C": "偏贪婪", "D": "贪婪", "E": "极度贪婪",
}


def _map_sector_signal(score: float) -> str:
    """板块专用信号映射，使用 V5_SECTOR_SIGNAL_THRESHOLDS。

    5因子加权平均自然范围[25,72]比14因子[8,85]窄，
    用独立边界[36,40,45,55,58,62]确保S/E极端信号可触发。
    14因子引擎仍用 SignalMapper + V5_SIGNAL_BOUNDARIES [12,25,38,52,65,80]。
    """
    thresholds = settings.V5_SECTOR_SIGNAL_THRESHOLDS
    if score < thresholds[0]:    # < 36 -> S+
        return "S+"
    elif score < thresholds[1]:  # < 40 -> S
        return "S"
    elif score < thresholds[2]:  # < 45 -> A
        return "A"
    elif score < thresholds[3]:  # < 55 -> B
        return "B"
    elif score < thresholds[4]:  # < 58 -> C
        return "C"
    elif score < thresholds[5]:  # < 62 -> D
        return "D"
    else:                         # >= 62 -> E
        return "E"

# 板块名称 → 行业分组映射 (保留原有)
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


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ThreePartReason:
    """三段式理由（观察→分析→行动）"""
    observation: str = ""
    analysis: str = ""
    action: str = ""

    def to_dict(self) -> dict:
        return {
            "observation": self.observation,
            "analysis": self.analysis,
            "action": self.action,
        }

    def to_string(self) -> str:
        parts = []
        if self.observation:
            parts.append(self.observation)
        if self.analysis:
            parts.append(self.analysis)
        if self.action:
            parts.append(self.action)
        return "；".join(parts)


@dataclass
class SectorFactorResult:
    """单个板块因子的计算结果"""
    factor_name: str
    raw_value: float
    percentile: Optional[float]
    sigmoid_score: float
    cold_start: bool = False


# ============================================================
# 辅助函数
# ============================================================

def _map_sector_group(name: str) -> str:
    for kw, grp in _GROUP_MAP.items():
        if kw in name:
            return grp
    return "综合"


def _sentiment_label(score: float) -> str:
    if score < 20:
        return "极度恐惧"
    elif score < 35:
        return "恐惧"
    elif score < 55:
        return "中性"
    elif score < 75:
        return "贪婪"
    else:
        return "极度贪婪"


# ============================================================
# 同步数据库查询 (板块代码直接查, 不经过 to_tushare 转换)
# ============================================================

def _get_db_connection():
    """获取同步 MySQL 连接"""
    import pymysql
    return pymysql.connect(
        host='rm-bp1iqpeh04issog45uo.mysql.rds.aliyuncs.com',
        port=3306,
        user='Jin0220',
        password='Jinhuan0220',
        db='fund_sentiment',
        charset='utf8mb4',
    )


def _calc_percentile_sync(index_code: str, factor_name: str, raw_value: float) -> tuple[Optional[float], int]:
    """
    同步计算分位数: raw_value 在 factor_history 历史序列中的百分位
    返回 (percentile 0.0-1.0, sample_count)
    数据不足时返回 (None, count)
    """
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        # 查询历史序列 (不经过 to_tushare, 直接用板块代码)
        cursor.execute(
            "SELECT raw_value FROM factor_history "
            "WHERE index_code = %s AND factor_name = %s "
            "ORDER BY trade_date ASC",
            (index_code, factor_name)
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None, 0

        series = [float(r[0]) for r in rows]
        count = len(series)

        if count < COLD_START_MIN_SAMPLES:
            return None, count

        # percentileofscore
        from scipy.stats import percentileofscore
        pct = percentileofscore(series, raw_value, kind="rank")
        return round(pct / 100.0, 6), count

    except Exception as e:
        logger.warning(f"_calc_percentile_sync error: {index_code}/{factor_name}: {e}")
        return None, 0


# ============================================================
# 因子原始值计算 (从 AKShare 价格数据)
# ============================================================

def _fetch_sector_price_data(sector_code: str, days: int = 60) -> list[dict]:
    """获取板块近期价格数据 (复用 data_fetcher)"""
    try:
        from app.engine.data_fetcher import fetch_sw_industry_hist
        return fetch_sw_industry_hist(sector_code, days)
    except Exception as e:
        logger.warning(f"fetch_sector_price_data error: {sector_code}: {e}")
        return []


def _compute_sector_factors(price_data: list[dict]) -> dict:
    """
    从价格数据计算 4 个板块因子的最新原始值
    返回 {"VOL": float, "RSI": float, "NHNL": float, "TURN": float}
    """
    if not price_data or len(price_data) < 20:
        return {}

    closes = np.array([d["close"] for d in price_data], dtype=float)
    amounts = np.array([d.get("amount", 0) for d in price_data], dtype=float)

    result = {}

    # VOL: 20日年化波动率
    returns = np.diff(closes) / closes[:-1]
    if len(returns) >= 20:
        vol = float(np.std(returns[-20:]) * np.sqrt(252))
        result["VOL"] = vol

    # RSI: 14日 RSI (Wilder)
    if len(closes) >= 15:
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        # Wilder smoothing
        avg_gain = gains[:14].mean()
        avg_loss = losses[:14].mean()
        for i in range(14, len(deltas)):
            avg_gain = (avg_gain * 13 + gains[i]) / 14
            avg_loss = (avg_loss * 13 + losses[i]) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        else:
            rsi = 100.0
        result["RSI"] = float(rsi)

    # NHNL: 20日新高新低净占比
    if len(closes) >= 20:
        window = closes[-20:]
        rolling_max = np.max(window)
        rolling_min = np.min(window)
        is_new_high = 1.0 if closes[-1] >= rolling_max else 0.0
        is_new_low = 1.0 if closes[-1] <= rolling_min else 0.0
        nhnl = (is_new_high - is_new_low)
        result["NHNL"] = float(nhnl)

    # TURN: 成交额相对强度
    if len(amounts) >= 20 and np.mean(amounts[-20:]) > 0:
        turn = float(amounts[-1] / np.mean(amounts[-20:]))
        result["TURN"] = turn

    return result


# ============================================================
# Sigmoid 映射
# ============================================================

def _apply_sigmoid(x: float, c: float, k: float) -> float:
    """Sigmoid: x ∈ [0,1] → score ∈ [0,100]"""
    if x is None:
        x = 0.5
    x = max(0.0, min(1.0, x))
    score = 100.0 / (1.0 + math.exp(-k * (x - c)))
    return round(score, 4)


def _sigmoid_map_factor(factor_name: str, percentile: Optional[float], raw_value: float, cold_start: bool) -> SectorFactorResult:
    """
    对单个因子做 Sigmoid 映射
    cold_start=True 时用线性映射代替
    """
    cfg = V5_SECTOR_FACTOR_CONFIG[factor_name]
    c = cfg["sigmoid_c"]
    k = cfg["sigmoid_k"]
    reverse = cfg["reverse"]

    if cold_start or percentile is None:
        # 冷启动: 线性映射 raw_value → [0, 100]
        # 简单线性: score = 50 + (raw - median) * scale
        # 用 0.5 分位数作为中位数近似
        sigmoid_score = _apply_sigmoid(0.5, c, k)
        return SectorFactorResult(
            factor_name=factor_name,
            raw_value=raw_value,
            percentile=None,
            sigmoid_score=sigmoid_score,
            cold_start=True,
        )

    sigmoid_score = _apply_sigmoid(percentile, c, k)

    # reverse=True 的因子: score = 100 - score
    if reverse:
        sigmoid_score = 100.0 - sigmoid_score

    return SectorFactorResult(
        factor_name=factor_name,
        raw_value=raw_value,
        percentile=percentile,
        sigmoid_score=round(sigmoid_score, 4),
        cold_start=False,
    )


# ============================================================
# 聚合 (层3: 分歧度动态加权)
# ============================================================

def _aggregate_sector_scores(factor_results: list[SectorFactorResult]) -> tuple[float, dict]:
    """
    聚合因子 Sigmoid 得分 → 综合情绪分
    流程: 加权求和 × 惩罚系数 → final_score
    返回 (composite_score, detail_dict)
    """
    if not factor_results:
        return 50.0, {}

    # 1. 加权求和
    weighted_sum = 0.0
    total_weight = 0.0
    for fr in factor_results:
        w = V5_SECTOR_FACTOR_CONFIG[fr.factor_name]["weight"]
        weighted_sum += fr.sigmoid_score * w
        total_weight += w

    if total_weight <= 0:
        raw_score = 50.0
    else:
        raw_score = weighted_sum / total_weight

    # 2. 分歧度惩罚
    scores = [fr.sigmoid_score for fr in factor_results]
    factor_std = float(np.std(scores)) if len(scores) > 1 else 0.0

    # penalty: std 0 → 1.0, std 15 → 0.5
    penalty_min = settings.V5_DIVERGENCE_PENALTY_MIN
    penalty_max = settings.V5_DIVERGENCE_PENALTY_MAX
    std_threshold = settings.V5_DIVERGENCE_STD_THRESHOLD
    penalty = penalty_max - (factor_std / std_threshold) * (penalty_max - penalty_min)
    penalty = max(penalty_min, min(penalty_max, penalty))

    # 3. 最终得分
    final_score = raw_score * penalty + 50.0 * (1.0 - penalty)
    final_score = max(0.0, min(100.0, final_score))

    detail = {
        "raw_score": round(raw_score, 4),
        "factor_std": round(factor_std, 4),
        "penalty": round(penalty, 4),
        "final_score": round(final_score, 4),
        "factor_scores": {fr.factor_name: fr.sigmoid_score for fr in factor_results},
    }

    return round(final_score, 1), detail


# ============================================================
# 置信度计算 (复用 ConfidenceEngine)
# ============================================================

def _calc_confidence(factor_results: list[SectorFactorResult], signal_level: str,
                     regime: str, price_series: list[float] = None,
                     sentiment_series: list[float] = None) -> tuple[int, dict, list[str]]:
    """
    计算置信度 (适配板块因子)
    返回 (stars, detail, triggered_defenses)
    """
    # 转换为 FactorSigmoidResult 格式
    from app.engine.factor_engine.base import FactorSigmoidResult

    sigmoid_results = []
    for fr in factor_results:
        sigmoid_results.append(FactorSigmoidResult(
            factor_name=fr.factor_name,
            percentile=fr.percentile if fr.percentile is not None else 0.5,
            sigmoid_score=fr.sigmoid_score,
            c_param=V5_SECTOR_FACTOR_CONFIG[fr.factor_name]["sigmoid_c"],
            k_param=V5_SECTOR_FACTOR_CONFIG[fr.factor_name]["sigmoid_k"],
            slope_at_midpoint=0.0,
        ))

    engine = ConfidenceEngine()
    stars, detail, triggered = engine.calculate(
        sigmoid_results=sigmoid_results,
        signal_level=signal_level,
        regime=regime,
        price_series=price_series,
        sentiment_series=sentiment_series,
    )

    return stars, detail, triggered


# ============================================================
# 三段式理由生成
# ============================================================

def _build_reason_v5(name: str, score: float, signal_level: str,
                     factor_results: list[SectorFactorResult],
                     confidence_stars: int, track: str) -> ThreePartReason:
    """生成 V5 三段式推荐理由"""
    # ── 观察段 ──
    meaning = _LEVEL_MEANINGS.get(signal_level, "中性")
    obs = f"{name}板块情绪评分{score:.0f}分（{meaning}），"

    # 因子亮点
    top_factor = max(factor_results, key=lambda x: abs(x.sigmoid_score - 50))
    if top_factor.sigmoid_score > 60:
        obs += f"{top_factor.factor_name}因子偏热（{top_factor.sigmoid_score:.0f}）"
    elif top_factor.sigmoid_score < 40:
        obs += f"{top_factor.factor_name}因子偏冷（{top_factor.sigmoid_score:.0f}）"
    else:
        obs += "各因子相对均衡"

    # ── 分析段 ──
    cold_start = any(fr.cold_start for fr in factor_results)
    track_label = "逆向轨道" if track == "contrarian" else ("正常轨道" if track == "trend_follow" else "未通过过滤")
    analysis_parts = [f"信号等级{signal_level}（{meaning}）"]
    analysis_parts.append(f"置信度{confidence_stars}星")
    analysis_parts.append(f"轨道: {track_label}")
    if cold_start:
        analysis_parts.append("冷启动模式")
    analysis = "，".join(analysis_parts) + "触发评分"

    # ── 行动段 ──
    if track == "contrarian":
        action = "逆向轨道触发，极端情绪+底背离，可关注反转机会，建议小仓位试探"
    elif track == "trend_follow":
        if signal_level in ("A", "B"):
            action = "正常轨道通过，趋势向上，可适度布局"
        elif signal_level == "C":
            action = "正常轨道通过，偏热区间，建议持有观望"
        elif signal_level == "D":
            action = "正常轨道通过（谨慎建仓），贪婪区间，注意风险"
        else:
            action = "正常轨道通过，建议持有"
    else:
        action = "未通过板块过滤器，建议观望"

    return ThreePartReason(observation=obs, analysis=analysis, action=action)


# ============================================================
# 核心: V5 三层流水线评分
# ============================================================

def score_sector_v5(sector_code: str, sector_name: str,
                    div_percentile: Optional[float] = None,
                    div_raw_value: Optional[float] = None,
                    price_data: list[dict] = None) -> dict:
    """
    V5 三层流水线板块评分

    Args:
        sector_code: 板块代码 (如 "801730")
        sector_name: 板块名称
        div_percentile: DIV因子的分位数 (市场级, 需外部计算)
        div_raw_value: DIV因子的原始值
        price_data: 板块价格数据 (可选, 避免重复拉取)

    Returns:
        评分结果字典
    """
    # 1. 获取价格数据
    if price_data is None:
        price_data = _fetch_sector_price_data(sector_code, days=60)

    if not price_data or len(price_data) < 20:
        # 数据不足, 返回中性
        return _get_default_sector_result(sector_code, sector_name, reason="数据不足")

    # 2. 计算因子原始值
    raw_values = _compute_sector_factors(price_data)
    if not raw_values:
        return _get_default_sector_result(sector_code, sector_name, reason="因子计算失败")

    # 3. 层1+层2: 分位数标准化 + Sigmoid映射
    factor_results: list[SectorFactorResult] = []
    cold_start = False

    for factor_name in NON_DIV_FACTORS:
        raw_val = raw_values.get(factor_name)
        if raw_val is None or not np.isfinite(raw_val):
            continue

        # 层1: 分位数
        percentile, sample_count = _calc_percentile_sync(sector_code, factor_name, raw_val)

        if percentile is None and sample_count < COLD_START_MIN_SAMPLES:
            cold_start = True

        # 层2: Sigmoid
        fr = _sigmoid_map_factor(factor_name, percentile, raw_val, cold_start=(percentile is None and sample_count < COLD_START_MIN_SAMPLES))
        factor_results.append(fr)

    # DIV 因子 (市场级, 分位数由外部传入)
    if div_percentile is not None and div_raw_value is not None:
        div_fr = _sigmoid_map_factor("DIV", div_percentile, div_raw_value, cold_start=False)
        factor_results.append(div_fr)
    else:
        # DIV 数据不足, 用中性值
        div_fr = _sigmoid_map_factor("DIV", 0.5, 0.0, cold_start=True)
        factor_results.append(div_fr)

    # 4. 层3: 聚合
    composite_score, agg_detail = _aggregate_sector_scores(factor_results)

    # 5. 信号映射 (板块专用边界)
    signal_level = _map_sector_signal(composite_score)

    # 6. 市场体制
    scores = [fr.sigmoid_score for fr in factor_results]
    mean_score = float(np.mean(scores))
    std_score = float(np.std(scores))
    if std_score > settings.V5_DIVERGENCE_STD_THRESHOLD:
        regime = "extreme_volatility"
    elif mean_score > 60:
        regime = "bull"
    elif mean_score < 40:
        regime = "bear"
    else:
        regime = "sideways"

    # 7. 置信度
    price_series = [d["close"] for d in price_data[-20:]] if len(price_data) >= 20 else []
    confidence_stars, confidence_detail, triggered_defenses = _calc_confidence(
        factor_results, signal_level, regime, price_series=price_series
    )

    # 8. 因子完整度
    expected_factors = len(V5_SECTOR_FACTOR_CONFIG)
    available_factors = len([fr for fr in factor_results if not fr.cold_start])
    factor_completeness = available_factors / expected_factors

    # 9. 双轨制板块过滤器
    track = calculate_sector_filter(
        sector_code=sector_code,
        sentiment_score=composite_score,
        signal_level=signal_level,
        confidence_stars=confidence_stars,
        sector_price_history=price_data,
        factor_completeness=factor_completeness,
    )

    # 10. 三段式理由
    reason = _build_reason_v5(
        sector_name, composite_score, signal_level,
        factor_results, confidence_stars, track
    )

    # 11. 动量 (保留向后兼容)
    closes = [d["close"] for d in price_data]
    momentum_5d = round((closes[-1] / closes[-6] - 1) * 100, 1) if len(closes) >= 6 else 0.0
    momentum_20d = round((closes[-1] / closes[-21] - 1) * 100, 1) if len(closes) >= 21 else 0.0
    chg = round((closes[-1] / closes[-2] - 1) * 100, 1) if len(closes) >= 2 else 0.0

    return {
        "sector_code": sector_code,
        "sector_name": sector_name,
        "sector_group": _map_sector_group(sector_name),
        "sentiment_score": composite_score,
        "sentiment_label": _sentiment_label(composite_score),
        "signal_level": signal_level,
        "confidence_stars": confidence_stars,
        "confidence_detail": confidence_detail,
        "track": track,
        "triggered_defenses": triggered_defenses,
        "momentum_5d": momentum_5d,
        "momentum_20d": momentum_20d,
        "strength_index": max(5, min(100, round(50 + chg * 10, 1))),
        "strength_rank": 0,
        "sector_return": chg,
        "factor_completeness": round(factor_completeness, 2),
        "cold_start": cold_start,
        "factor_scores": {
            fr.factor_name: {
                "score": fr.sigmoid_score,
                "raw_percentile": round(fr.percentile * 100, 1) if fr.percentile is not None else None,
            }
            for fr in factor_results
        },
        "aggregation_detail": agg_detail,
        "reason": reason.to_dict(),
    }


def _get_default_sector_result(sector_code: str, sector_name: str, reason: str = "") -> dict:
    """数据不足时的默认返回"""
    return {
        "sector_code": sector_code,
        "sector_name": sector_name,
        "sector_group": _map_sector_group(sector_name),
        "sentiment_score": 50.0,
        "sentiment_label": "中性",
        "signal_level": "B",
        "confidence_stars": 1,
        "confidence_detail": {},
        "track": "excluded",
        "triggered_defenses": [],
        "momentum_5d": 0.0,
        "momentum_20d": 0.0,
        "strength_index": 50.0,
        "strength_rank": 0,
        "sector_return": 0.0,
        "factor_completeness": 0.0,
        "cold_start": True,
        "factor_scores": {},
        "aggregation_detail": {},
        "factor_details": {},
        "reason": {"observation": f"{sector_name}数据不足", "analysis": reason, "action": "建议观望"},
    }


# ============================================================
# DIV 因子计算 (跨板块)
# ============================================================

def _calc_div_factor(sector_preliminary_scores: dict[str, float]) -> tuple[float, Optional[float]]:
    """
    计算DIV因子: 跨板块情绪分标准差

    Args:
        sector_preliminary_scores: {sector_code: preliminary_score}

    Returns:
        (div_raw_value, div_percentile)
    """
    if len(sector_preliminary_scores) < 5:
        return 0.0, None

    scores = list(sector_preliminary_scores.values())
    div_raw = float(np.std(scores))

    # 从 factor_history 获取 DIV 分位数
    div_pct, _ = _calc_percentile_sync(DIV_INDEX_CODE, "DIV", div_raw)

    return div_raw, div_pct


def _calc_preliminary_score(sector_code: str, raw_values: dict) -> tuple[float, bool]:
    """
    计算板块初步情绪分 (4因子等权平均, 用于DIV)
    返回 (preliminary_score, cold_start)
    """
    factor_results: list[SectorFactorResult] = []
    cold_start = False

    for factor_name in NON_DIV_FACTORS:
        raw_val = raw_values.get(factor_name)
        if raw_val is None or not np.isfinite(raw_val):
            continue

        percentile, sample_count = _calc_percentile_sync(sector_code, factor_name, raw_val)
        if percentile is None and sample_count < COLD_START_MIN_SAMPLES:
            cold_start = True

        fr = _sigmoid_map_factor(factor_name, percentile, raw_val,
                                 cold_start=(percentile is None and sample_count < COLD_START_MIN_SAMPLES))
        factor_results.append(fr)

    if not factor_results:
        return 50.0, True

    # 等权平均 (不是加权, 用于DIV计算)
    avg_score = float(np.mean([fr.sigmoid_score for fr in factor_results]))
    return avg_score, cold_start


# ============================================================
# 双轨制板块过滤器
# ============================================================

def calculate_sector_filter(
    sector_code: str,
    sentiment_score: float,
    signal_level: str,
    confidence_stars: int,
    sector_price_history: list[dict] = None,
    sector_sentiment_history: list[float] = None,
    factor_completeness: float = 1.0,
) -> str:
    """
    双轨制板块过滤器

    返回: "trend_follow" | "contrarian" | "excluded"
    """
    # 因子完整度检查
    if factor_completeness < 0.90:
        return "excluded"

    # 获取 MA20 趋势
    trend_signal = "震荡"
    if sector_price_history and len(sector_price_history) >= 20:
        trend_signal = _calculate_ma20_trend(sector_price_history)

    # ── 正常轨道校验 ──
    trend_follow_pass = (
        signal_level in ["A", "B", "C", "D"] and
        trend_signal == "上升" and
        confidence_stars >= 2 and
        factor_completeness >= 0.90
    )

    # ── 逆向轨道校验 ──
    # S+ (极度恐惧): confidence_stars >= 3 (保留高门槛)
    # S  (恐惧):     confidence_stars >= 2 (降低门槛, 回测显示95%的S信号为2星)
    contrarian_pass = False
    contrarian_qualified = (
        (signal_level == "S+" and confidence_stars >= 3) or
        (signal_level == "S" and confidence_stars >= 2)
    )
    if contrarian_qualified and factor_completeness >= 0.90:
        # 检查底背离 (bullish divergence)
        has_bottom_divergence = False
        if sector_price_history and sector_sentiment_history:
            if len(sector_price_history) >= 5 and len(sector_sentiment_history) >= 5:
                price_series = [d["close"] for d in sector_price_history[-20:]]
                detector = DivergenceDetector()
                div_result = detector.detect(price_series, sector_sentiment_history[-20:])
                if div_result["divergence_type"] == "bullish" and div_result["strength"] > 30:
                    has_bottom_divergence = True
        elif signal_level in ("S+", "S"):
            # S+/S 信号本身已暗示恐惧区域, 无背离数据时也允许通过
            has_bottom_divergence = True

        contrarian_pass = has_bottom_divergence

    # ── 优先级: 逆向轨道 > 正常轨道 > 排除 ──
    if contrarian_pass:
        return "contrarian"
    elif trend_follow_pass:
        return "trend_follow"
    else:
        return "excluded"


# ============================================================
# 批量评分 (入口)
# ============================================================

async def score_sectors(raw_items: list[dict] = None) -> list[dict]:
    """
    批量板块评分 (V5 三层流水线 + DIV跨板块)

    Args:
        raw_items: 板块行情列表 (来自东方财富API)
                   如果为None, 自动获取申万行业列表

    Returns:
        评分后的板块列表
    """
    start_time = time.time()

    # 1. 获取板块列表
    if raw_items is None:
        sectors = _get_sw_sector_list()
    else:
        sectors = []
        for item in raw_items:
            code = str(item.get("code", ""))
            name = item.get("name", "")
            if code and name:
                sectors.append({"code": code, "name": name})

    if not sectors:
        logger.warning("板块数据为空, 无法评分")
        return []

    # 去重
    seen = set()
    unique_sectors = []
    for s in sectors:
        key = (s["code"], s["name"])
        if key not in seen:
            seen.add(key)
            unique_sectors.append(s)

    logger.info(f"V5板块评分开始: {len(unique_sectors)} 个板块")

    # 2. 批量拉取价格数据 + 计算因子原始值
    sector_raw_factors: dict[str, dict] = {}  # {code: {factor: value}}
    sector_price_data: dict[str, list[dict]] = {}  # {code: price_data}

    for s in unique_sectors:
        code = s["code"]
        price_data = _fetch_sector_price_data(code, days=60)
        sector_price_data[code] = price_data

        if price_data and len(price_data) >= 20:
            raw_vals = _compute_sector_factors(price_data)
            sector_raw_factors[code] = raw_vals
        else:
            sector_raw_factors[code] = {}

    # 3. 计算各板块初步情绪分 (用于DIV)
    preliminary_scores: dict[str, float] = {}
    for s in unique_sectors:
        code = s["code"]
        raw_vals = sector_raw_factors.get(code, {})
        if raw_vals:
            score, _ = _calc_preliminary_score(code, raw_vals)
            preliminary_scores[code] = score

    # 4. 计算 DIV 因子
    div_raw, div_pct = _calc_div_factor(preliminary_scores)
    logger.info(f"DIV因子: raw={div_raw:.4f}, percentile={div_pct}")

    # 5. 对每个板块执行 V5 三层流水线评分
    scored = []
    for s in unique_sectors:
        code = s["code"]
        name = s["name"]
        price_data = sector_price_data.get(code, [])

        result = score_sector_v5(
            sector_code=code,
            sector_name=name,
            div_percentile=div_pct,
            div_raw_value=div_raw,
            price_data=price_data,
        )
        scored.append(result)

    # 6. 强度排名
    scored.sort(key=lambda x: x["strength_index"], reverse=True)
    for rank, item in enumerate(scored, 1):
        item["strength_rank"] = rank

    elapsed = time.time() - start_time
    cold_count = sum(1 for s in scored if s.get("cold_start"))
    tf_count = sum(1 for s in scored if s.get("track") == "trend_follow")
    ct_count = sum(1 for s in scored if s.get("track") == "contrarian")
    ex_count = sum(1 for s in scored if s.get("track") == "excluded")

    logger.info(
        f"V5板块评分完成: {len(scored)}个板块, 冷启动{cold_count}个, "
        f"正常轨道{tf_count}个, 逆向轨道{ct_count}个, 排除{ex_count}个, 耗时{elapsed:.1f}s"
    )

    return scored


def _get_sw_sector_list() -> list[dict]:
    """获取申万一级行业列表"""
    try:
        import akshare as ak
        df = ak.sw_index_first_info()
        sectors = []
        for _, row in df.iterrows():
            code = str(row['行业代码']).replace('.SI', '')
            name = row['行业名称']
            sectors.append({"code": code, "name": name})
        return sectors
    except Exception as e:
        logger.error(f"获取申万行业列表失败: {e}")
        return []


# ============================================================
# 向后兼容: 旧版 score_sector (保留接口, 内部调用 V5)
# ============================================================

def score_sector(item: dict) -> dict:
    """
    旧版接口兼容: 将单条板块行情转换为情绪评分
    内部调用 score_sector_v5
    """
    code = str(item.get("code", ""))
    name = item.get("name", "")

    if not code:
        return _get_default_sector_result(code, name, "无板块代码")

    result = score_sector_v5(code, name)
    return result


# ============================================================
# 向后兼容: add_sector_filter (已集成到 score_sectors)
# ============================================================

def add_sector_filter(sectors: list[dict]) -> list[dict]:
    """
    为板块列表添加板块过滤器信号 (向后兼容)
    V5 版本中过滤器已集成到 score_sectors, 此函数为 no-op
    """
    if not sectors:
        return sectors

    if not settings.ENABLE_SECTOR_FILTER:
        logger.info("板块过滤器未启用, 跳过")
        return sectors

    # V5 中 track 字段已在 score_sectors 中计算, 此处确保存在
    for sector in sectors:
        if "track" not in sector:
            sector["track"] = "excluded"
        # 向后兼容: build_signal
        track = sector.get("track", "excluded")
        if track == "trend_follow":
            sector["build_signal"] = "适合建仓"
        elif track == "contrarian":
            sector["build_signal"] = "逆向建仓"
        else:
            sector["build_signal"] = "暂不建仓"

    return sectors
