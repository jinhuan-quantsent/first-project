"""
引擎兼容层 — V5.0

为保留原有 API 接口（market.py）提供 V4.0 格式的输出，
底层使用 V5.0 的 11 因子流水线。

V4.0 格式（7因子）→ V5.0 格式（11因子）映射：
- 波动率 → VOL
- 换手率 → TURN
- 涨跌比 → ADR
- 新高占比 → NHNL
- 融资融券 → FLOW (部分替代)
- 股债比 → ERP
- RSI → 移除（V5 无 RSI）
- 北向资金 → NBF

新增 V5 因子：ETF, POS, PCR, NEWF
"""

from __future__ import annotations

from typing import Optional
from datetime import date

from app.engine.factor_engine import FACTOR_NAMES, FACTOR_CLASSES
from app.engine.factor_engine.base import FactorRawValue, FactorSigmoidResult
from app.engine.quantile import QuantileNorm
from app.engine.sigmoid import SigmoidMapper
from app.engine.aggregator_v5 import AggregatorV5, CompositeScore
from app.core.config import settings


# ============================================================
# 兼容 V4.0 的数据结构
# ============================================================

class FactorScore:
    """V4.0 因子评分（兼容结构）"""
    def __init__(
        self,
        factor_name: str,
        raw_value: float,
        score: float,
        label: str,
        is_extreme: bool,
        extreme_type: Optional[str] = None,
    ) -> None:
        self.factor_name = factor_name
        self.raw_value = raw_value
        self.score = score
        self.label = label
        self.is_extreme = is_extreme
        self.extreme_type = extreme_type


class CompositeResult:
    """V4.0 综合结果（兼容结构）"""
    def __init__(
        self,
        index_code: str,
        index_name: str,
        composite_score: float,
        sentiment_label: str,
        factor_scores: dict[str, FactorScore],
        top3_factors: list[FactorScore],
        trend_direction: str = "stable",
        trend_strength: float = 0.0,
        is_extreme: bool = False,
        abnormal_signals: list[str] | None = None,
        conclusion: str = "",
        operation_advice: str = "",
        divergence_index: float = 0.0,
    ) -> None:
        self.index_code = index_code
        self.index_name = index_name
        self.composite_score = composite_score
        self.sentiment_label = sentiment_label
        self.factor_scores = factor_scores
        self.top3_factors = top3_factors
        self.trend_direction = trend_direction
        self.trend_strength = trend_strength
        self.is_extreme = is_extreme
        self.abnormal_signals = abnormal_signals or []
        self.conclusion = conclusion
        self.operation_advice = operation_advice
        self.divergence_index = divergence_index


# ============================================================
# V4.0 兼容函数
# ============================================================

# V4.0 因子名称 → V5.0 因子代码映射
V4_TO_V5_FACTOR = {
    "波动率": "VOL",
    "换手率": "TURN",
    "涨跌比": "ADR",
    "新高占比": "NHNL",
    "融资融券": "FLOW",
    "股债比": "ERP",
    "RSI": "VOL",  # RSI 移除，用 VOL 替代
    "北向资金": "NBF",
}

# V4.0 因子层级（兼容）
FACTOR_LAYERS = {
    "波动率": {"layer": "price", "direction": "fear"},
    "换手率": {"layer": "liquidity", "direction": "fear"},
    "涨跌比": {"layer": "breadth", "direction": "greed"},
    "新高占比": {"layer": "breadth", "direction": "greed"},
    "融资融券": {"layer": "liquidity", "direction": "greed"},
    "股债比": {"layer": "valuation", "direction": "fear"},
    "RSI": {"layer": "momentum", "direction": "greed"},
    "北向资金": {"layer": "liquidity", "direction": "greed"},
}


def score_factor(factor_name: str, raw_value: float, index_code: str) -> FactorScore:
    """
    V4.0 兼容：计算单因子评分
    底层使用 V5.0 Sigmoid 映射
    """
    from app.engine.factor_engine import FACTOR_CLASSES

    v5_name = V4_TO_V5_FACTOR.get(factor_name, "VOL")
    factor_cls = FACTOR_CLASSES.get(v5_name)
    if not factor_cls:
        # 默认返回中性
        return FactorScore(
            factor_name=factor_name,
            raw_value=raw_value,
            score=50.0,
            label="neutral",
            is_extreme=False,
        )

    factor = factor_cls()
    sigmoid_mapper = SigmoidMapper()

    # 简化的分位数（用固定值）
    x = 0.50
    score = sigmoid_mapper.apply_sigmoid(x, factor.sigmoid_c, factor.sigmoid_k)

    # 判断极端值
    is_extreme = score < 20 or score > 80
    extreme_type = None
    if score < 20:
        extreme_type = "extreme_fear"
    elif score > 80:
        extreme_type = "extreme_greed"

    return FactorScore(
        factor_name=factor_name,
        raw_value=raw_value,
        score=round(score, 2),
        label=_score_to_label(score),
        is_extreme=is_extreme,
        extreme_type=extreme_type,
    )


def calculate_index_sentiment(
    index_code: str,
    index_name: str,
    factor_scores: dict[str, FactorScore],
) -> CompositeResult:
    """
    V4.0 兼容：计算单指数情绪
    底层使用 V5.0 聚合器
    """
    # 转换 V4 格式到 V5 格式
    sigmoid_results = []
    for name, fs in factor_scores.items():
        v5_name = V4_TO_V5_FACTOR.get(name, "VOL")
        sigmoid_results.append(FactorSigmoidResult(
            factor_name=v5_name,
            percentile=0.50,  # 默认中位数
            sigmoid_score=fs.score,
            c_param=0.50,
            k_param=3.0,
            slope_at_midpoint=0.0,
        ))

    # 使用 V5 聚合器
    aggregator = AggregatorV5()
    composite = aggregator.aggregate(sigmoid_results)

    # 映射回 V4 格式
    from app.engine.signal_mapper import SignalMapper
    mapper = SignalMapper()
    signal_level, _ = mapper.map(composite.composite_score)
    sentiment_label = _signal_to_v4_label(signal_level)

    # Top 3 因子
    sorted_factors = sorted(
        factor_scores.values(),
        key=lambda f: abs(f.score - 50),
        reverse=True,
    )
    top3 = sorted_factors[:3]

    return CompositeResult(
        index_code=index_code,
        index_name=index_name,
        composite_score=round(composite.composite_score, 2),
        sentiment_label=sentiment_label,
        factor_scores=factor_scores,
        top3_factors=top3,
        conclusion=mapper.get_conclusion(signal_level),
        divergence_index=round(composite.divergence_penalty * 100, 2),
    )


def calculate_composite_sentiment(
    index_results: dict[str, CompositeResult],
) -> CompositeResult:
    """
    V4.0 兼容：计算综合情绪
    """
    if not index_results:
        return CompositeResult(
            index_code="composite",
            index_name="综合",
            composite_score=50.0,
            sentiment_label="neutral",
            factor_scores={},
            top3_factors=[],
        )

    # 取第一个结果作为基础
    first = next(iter(index_results.values()))
    avg_score = sum(r.composite_score for r in index_results.values()) / len(index_results)

    from app.engine.signal_mapper import SignalMapper
    mapper = SignalMapper()
    signal_level, _ = mapper.map(avg_score)
    sentiment_label = _signal_to_v4_label(signal_level)

    return CompositeResult(
        index_code="composite",
        index_name="综合",
        composite_score=round(avg_score, 2),
        sentiment_label=sentiment_label,
        factor_scores=first.factor_scores,
        top3_factors=first.top3_factors,
        conclusion=mapper.get_conclusion(signal_level),
    )


# ============================================================
# 辅助函数
# ============================================================

def _score_to_label(score: float) -> str:
    """分数 → V4.0 标签"""
    if score < 20:
        return "extreme_fear"
    if score < 40:
        return "fear"
    if score < 60:
        return "neutral"
    if score < 80:
        return "greed"
    return "extreme_greed"


def _signal_to_v4_label(signal_level: str) -> str:
    """V5.0 信号等级 → V4.0 标签"""
    mapping = {
        "S+": "extreme_fear",
        "S": "fear",
        "A": "fear",
        "B": "neutral",
        "C": "neutral",
        "D": "greed",
        "E": "extreme_greed",
    }
    return mapping.get(signal_level, "neutral")
