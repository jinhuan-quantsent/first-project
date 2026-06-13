"""
V5.0 评分引擎 — 分位数映射 + 因子分层 + 动态权重
核心改进：
1. 因子分层：估值层(股债比+新高占比) / 动量层(涨跌比+换手率+RSI) / 资金层(波动率+融资融券+北向资金)
2. 分位数映射替代固定阈值
3. 情绪变化速度
"""
from dataclasses import dataclass, field
from typing import Optional

from app.engine.factor_history import factor_history, REVERSE_FACTORS, INVERTED_U_FACTORS

@dataclass
class FactorScore:
    factor_name: str
    raw_value: float
    score: float
    label: str
    layer: str = "momentum"
    is_extreme: bool = False
    extreme_type: str = ""
    confidence: str = "low"

# ── 分位数参考表（基于A股近3年统计特征，运行时可由实际历史数据覆盖）──
# 格式: {因子名: {"p10": val, "p25": val, "p50": val, "p75": val, "p90": val}}
PERCENTILE_REFS = {
    "波动率":    {"p10": 8,   "p25": 12,  "p50": 18,  "p75": 25,  "p90": 35},
    "换手率":    {"p10": 0.4, "p25": 0.7, "p50": 1.2, "p75": 2.0, "p90": 3.5},
    "涨跌比":    {"p10": 0.3, "p25": 0.6, "p50": 1.0, "p75": 1.5, "p90": 2.5},
    "新高占比":  {"p10": 1.5, "p25": 3.0, "p50": 5.5, "p75": 9.0, "p90": 14.0},
    "融资融券":  {"p10": 5,   "p25": 15,  "p50": 30,  "p75": 50,  "p90": 70},
    "股债比":    {"p10": -1.0,"p25": 0.0, "p50": 1.2, "p75": 2.5, "p90": 4.0},
    "RSI":       {"p10": 25,  "p25": 35,  "p50": 50,  "p75": 65,  "p90": 75},
    "北向资金":  {"p10": -80, "p25": -30, "p50": 10,  "p75": 50,  "p90": 100},
}

# ── 因子分层 ──
FACTOR_LAYERS = {
    "valuation": ["股债比", "新高占比"],
    "momentum":  ["涨跌比", "换手率", "RSI"],
    "capital":   ["波动率", "融资融券", "北向资金"],
}

# 基础层权重
BASE_LAYER_WEIGHTS = {"valuation": 0.35, "momentum": 0.35, "capital": 0.30}

# 层内因子均等权重
def _layer_factor_weights(layer):
    return {f: 1.0/len(FACTOR_LAYERS[layer]) for f in FACTOR_LAYERS[layer]}


def _percentile_score(raw_value, factor_name):
    """将原始值映射到0-100分（基于分位数线性插值）"""
    ref = PERCENTILE_REFS.get(factor_name)
    if not ref:
        return 50.0
    if raw_value <= ref["p10"]:
        return max(5, raw_value / ref["p10"] * 10)
    if raw_value <= ref["p25"]:
        pct = (raw_value - ref["p10"]) / (ref["p25"] - ref["p10"])
        return 10 + pct * 15
    if raw_value <= ref["p50"]:
        pct = (raw_value - ref["p25"]) / (ref["p50"] - ref["p25"])
        return 25 + pct * 25
    if raw_value <= ref["p75"]:
        pct = (raw_value - ref["p50"]) / (ref["p75"] - ref["p50"])
        return 50 + pct * 25
    if raw_value <= ref["p90"]:
        pct = (raw_value - ref["p75"]) / (ref["p90"] - ref["p75"])
        return 75 + pct * 15
    return min(95, 90 + (raw_value - ref["p90"]) / ref["p90"] * 5)


def _get_label(score):
    if score < 20: return "extreme_fear"
    if score < 40: return "fear"
    if score < 60: return "neutral"
    if score < 80: return "greed"
    return "extreme_greed"


def _get_factor_layer(factor_name: str) -> str:
    """根据因子名查找所属层"""
    for layer, factors in FACTOR_LAYERS.items():
        if factor_name in factors:
            return layer
    return "momentum"


def score_factor_percentile(factor_name: str, raw_value: float, index_code: str = None) -> Optional[float]:
    """
    V4.0 动态分位数评分
    正向因子: score = percentile (值越大越好 → 分位数越高越好)
    反向因子: score = 100 - percentile (值越大越恐慌 → 分位数越高越恐慌)
    返回 None 表示历史数据不足，需降级
    """
    if index_code is None:
        return None

    pct = factor_history.get_percentile(index_code, factor_name, raw_value)
    if pct is None:
        return None  # 数据不足，降级

    if factor_name in REVERSE_FACTORS:
        return round(100 - pct, 1)
    return round(pct, 1)


def score_inverted_u(factor_name: str, raw_value: float, index_code: str = None) -> Optional[float]:
    """
    V4.0 倒U型因子评分
    换手率、融资融券：适中最好，偏离中位数越远得分越低
    返回 None 表示历史数据不足，需降级
    """
    if index_code is None:
        return None

    series = factor_history.get_series(index_code, factor_name)
    if len(series) < 60:
        return None

    import numpy as np
    median = np.median(series)
    p90 = np.percentile(series, 90)
    p10 = np.percentile(series, 10)
    iqr_like = p90 - p10 + 1e-8  # 防止除零

    deviation = abs(raw_value - median) / iqr_like
    # deviation 0 -> 100分, deviation > 2 -> 0分
    score = max(0, 100 - deviation * 50)
    return round(min(100, score), 1)


def score_factor(factor_name: str, raw_value: float, index_code: str = None) -> FactorScore:
    """
    V4.0 动态分位数评分（降级兼容）

    优先使用750天历史动态分位数
    降级：数据不足时回退到 PERCENTILE_REFS 硬编码
    """
    score = None
    confidence = "medium"

    # 尝试动态分位数
    if index_code and factor_name in {"换手率", "融资融券"}:
        score = score_inverted_u(factor_name, raw_value, index_code)
    elif index_code:
        score = score_factor_percentile(factor_name, raw_value, index_code)

    if score is not None:
        # 动态分位数成功
        days = factor_history.get_series_count(index_code, factor_name)
        if days >= 250:
            confidence = "high"
        elif days >= 60:
            confidence = "medium"
        else:
            confidence = "low"
    else:
        # 降级：使用旧版 PERCENTILE_REFS
        score = _percentile_score(raw_value, factor_name)
        confidence = "low"

    # 极端值检测
    is_extreme = bool(score <= 15 or score >= 85)
    extreme_type = None
    if score <= 5:
        extreme_type = "极度恐慌信号"
    elif score <= 15:
        extreme_type = "恐慌信号"
    elif score >= 95:
        extreme_type = "极度贪婪信号"
    elif score >= 85:
        extreme_type = "贪婪信号"

    label = _get_label(score)

    return FactorScore(
        factor_name=factor_name,
        raw_value=raw_value,
        score=score,
        label=label,
        is_extreme=is_extreme,
        extreme_type=extreme_type,
        layer=_get_factor_layer(factor_name),
        confidence=confidence,
    )


# ── V5.0 动态权重 ──
def calculate_dynamic_weights(factor_scores, north_flow_5d=None):
    """根据市场状态动态调整层权重"""
    weights = {l: BASE_LAYER_WEIGHTS[l] for l in BASE_LAYER_WEIGHTS}
    factor_weights = {}
    for layer, factors in FACTOR_LAYERS.items():
        for f in factors:
            factor_weights[f] = _layer_factor_weights(layer)[f]

    # 规则1: 极端波动 → 降资金层
    vol_score = None
    for fs in factor_scores.values():
        if fs.factor_name == "波动率":
            vol_score = fs.score
            break
    if vol_score is not None and vol_score < 25:  # 波动率处于高分位=极端波动
        weights["capital"] *= 0.7
        weights["momentum"] += BASE_LAYER_WEIGHTS["capital"] * 0.15
        weights["valuation"] += BASE_LAYER_WEIGHTS["capital"] * 0.15

    # 规则2: 融资融券与涨跌比背离
    margin_s = None
    adv_s = None
    for fs in factor_scores.values():
        if fs.factor_name == "融资融券": margin_s = fs.score
        if fs.factor_name == "涨跌比": adv_s = fs.score
    if margin_s is not None and adv_s is not None and abs(margin_s - adv_s) > 25:
        factor_weights["融资融券"] *= 0.5
        factor_weights["涨跌比"] += _layer_factor_weights("momentum")["涨跌比"] * 0.25

    # 规则3: 北向资金持续流出 → 提升权重
    if north_flow_5d is not None and north_flow_5d < -50:
        factor_weights["北向资金"] *= 1.3

    # 归一化层权重
    total_layer = sum(weights.values())
    for l in weights:
        weights[l] /= total_layer

    # 归一化因子权重（保持层内比例）
    for layer, factors in FACTOR_LAYERS.items():
        layer_total = sum(factor_weights[f] for f in factors)
        if layer_total > 0:
            for f in factors:
                factor_weights[f] = factor_weights[f] / layer_total * weights[layer] * len(factors)

    return weights, factor_weights


# ── 情绪变化速度 ──
def calculate_sentiment_velocity(current_score, previous_scores_5d):
    """计算情绪变化速度（标准化）"""
    if not previous_scores_5d or len(previous_scores_5d) < 3:
        return 0.0, "stable"
    mean_5d = sum(previous_scores_5d) / len(previous_scores_5d)
    diffs = [(s - mean_5d)**2 for s in previous_scores_5d]
    std_5d = (sum(diffs) / len(diffs))**0.5
    if std_5d < 0.5:
        return 0.0, "stable"
    velocity = round((current_score - mean_5d) / std_5d, 2)
    if velocity > 1.5: direction = "surging"
    elif velocity > 0.5: direction = "warming"
    elif velocity < -1.5: direction = "plunging"
    elif velocity < -0.5: direction = "cooling"
    else: direction = "stable"
    return velocity, direction
