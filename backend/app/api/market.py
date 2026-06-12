"""
大盘情绪相关接口
包含多指数情绪、板块情绪、机会推荐、异常检测等
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.engine.scoring import (
    FactorScore,
    score_volatility,
    score_turnover,
    score_adv_decline,
    score_new_high,
    score_margin,
    score_bond_equity,
    score_rsi,
)
from app.engine.aggregator import (
    calculate_index_sentiment,
    calculate_composite_sentiment,
    CompositeResult,
)
from app.engine.recommendations import generate_recommendations, RecommendationResult
from app.engine.position import calculate_position

router = APIRouter()


# ============================================================
# Mock 数据生成
# ============================================================
MOCK_INDEXES: dict[str, dict] = {
    "SH000001": {
        "name": "上证综指",
        "close": 3250.68,
        "change_pct": 0.35,
        "volatility": 18.5,
        "turnover_ratio": 2.8,
        "adv_decline_ratio": 1.15,
        "new_high_ratio": 6.5,
        "margin_data": {"margin_balance": 14800, "short_balance": 950, "net_margin_flow": 35},
        "bond_yield": 2.85,
        "equity_yield": 4.2,
        "rsi_value": 52.0,
    },
    "SH000300": {
        "name": "沪深300",
        "close": 3850.42,
        "change_pct": 0.52,
        "volatility": 16.2,
        "turnover_ratio": 1.8,
        "adv_decline_ratio": 1.35,
        "new_high_ratio": 8.2,
        "margin_data": {"margin_balance": 12500, "short_balance": 720, "net_margin_flow": 55},
        "bond_yield": 2.85,
        "equity_yield": 3.8,
        "rsi_value": 56.0,
    },
    "SZ399001": {
        "name": "深证成指",
        "close": 11280.35,
        "change_pct": -0.28,
        "volatility": 22.0,
        "turnover_ratio": 3.5,
        "adv_decline_ratio": 0.92,
        "new_high_ratio": 5.8,
        "margin_data": {"margin_balance": 10200, "short_balance": 680, "net_margin_flow": -15},
        "bond_yield": 2.85,
        "equity_yield": 3.5,
        "rsi_value": 44.0,
    },
    "SZ399006": {
        "name": "创业板指",
        "close": 2350.18,
        "change_pct": -0.85,
        "volatility": 28.5,
        "turnover_ratio": 5.2,
        "adv_decline_ratio": 0.72,
        "new_high_ratio": 4.5,
        "margin_data": {"margin_balance": 5800, "short_balance": 520, "net_margin_flow": -45},
        "bond_yield": 2.85,
        "equity_yield": 2.8,
        "rsi_value": 38.0,
    },
}


def _compute_index_result(index_code: str, data: dict) -> CompositeResult:
    """计算单个指数的情绪结果"""
    factor_scores: dict[str, FactorScore] = {
        "波动率": score_volatility(data["volatility"]),
        "换手率": score_turnover(data["turnover_ratio"]),
        "涨跌比": score_adv_decline(data["adv_decline_ratio"]),
        "新高占比": score_new_high(data["new_high_ratio"]),
        "融资融券": score_margin(data["margin_data"]),
        "股债比": score_bond_equity(data["bond_yield"], data["equity_yield"]),
        "RSI": score_rsi(data["rsi_value"]),
    }
    return calculate_index_sentiment(index_code, data["name"], factor_scores)


# ============================================================
# Mock 板块数据
# ============================================================
MOCK_SECTORS: list[dict] = [
    {"sector_code": "BK001", "sector_name": "半导体", "sector_group": "科技", "sentiment_score": 72, "sentiment_label": "greed", "momentum_5d": 3.5, "momentum_20d": 8.2, "strength_index": 75, "sector_return": 1.8, "turnover_ratio": 4.5, "fund_flow": 25.0},
    {"sector_code": "BK002", "sector_name": "人工智能", "sector_group": "科技", "sentiment_score": 78, "sentiment_label": "greed", "momentum_5d": 5.2, "momentum_20d": 12.5, "strength_index": 82, "sector_return": 2.5, "turnover_ratio": 6.0, "fund_flow": 45.0},
    {"sector_code": "BK003", "sector_name": "新能源汽车", "sector_group": "制造", "sentiment_score": 55, "sentiment_label": "neutral", "momentum_5d": 0.8, "momentum_20d": -2.5, "strength_index": 52, "sector_return": 0.3, "turnover_ratio": 2.8, "fund_flow": 5.0},
    {"sector_code": "BK004", "sector_name": "医药生物", "sector_group": "医药", "sentiment_score": 28, "sentiment_label": "fear", "momentum_5d": -2.8, "momentum_20d": -6.5, "strength_index": 32, "sector_return": -1.5, "turnover_ratio": 1.2, "fund_flow": -15.0},
    {"sector_code": "BK005", "sector_name": "白酒", "sector_group": "消费", "sentiment_score": 45, "sentiment_label": "neutral", "momentum_5d": -1.2, "momentum_20d": -3.8, "strength_index": 42, "sector_return": -0.8, "turnover_ratio": 1.5, "fund_flow": -8.0},
    {"sector_code": "BK006", "sector_name": "银行", "sector_group": "金融", "sentiment_score": 52, "sentiment_label": "neutral", "momentum_5d": 0.5, "momentum_20d": 1.2, "strength_index": 55, "sector_return": 0.2, "turnover_ratio": 0.8, "fund_flow": 12.0},
    {"sector_code": "BK007", "sector_name": "券商", "sector_group": "金融", "sentiment_score": 62, "sentiment_label": "greed", "momentum_5d": 2.5, "momentum_20d": 5.8, "strength_index": 68, "sector_return": 1.2, "turnover_ratio": 3.5, "fund_flow": 28.0},
    {"sector_code": "BK008", "sector_name": "光伏", "sector_group": "能源", "sentiment_score": 32, "sentiment_label": "fear", "momentum_5d": -3.5, "momentum_20d": -8.0, "strength_index": 30, "sector_return": -2.0, "turnover_ratio": 2.0, "fund_flow": -22.0},
    {"sector_code": "BK009", "sector_name": "军工", "sector_group": "制造", "sentiment_score": 58, "sentiment_label": "neutral", "momentum_5d": 1.5, "momentum_20d": 3.2, "strength_index": 60, "sector_return": 0.8, "turnover_ratio": 2.5, "fund_flow": 8.0},
    {"sector_code": "BK010", "sector_name": "房地产", "sector_group": "地产", "sentiment_score": 22, "sentiment_label": "extreme_fear", "momentum_5d": -5.2, "momentum_20d": -10.5, "strength_index": 20, "sector_return": -3.2, "turnover_ratio": 1.0, "fund_flow": -35.0},
    {"sector_code": "BK011", "sector_name": "通信设备", "sector_group": "科技", "sentiment_score": 65, "sentiment_label": "greed", "momentum_5d": 3.0, "momentum_20d": 7.5, "strength_index": 70, "sector_return": 1.5, "turnover_ratio": 3.8, "fund_flow": 20.0},
    {"sector_code": "BK012", "sector_name": "食品饮料", "sector_group": "消费", "sentiment_score": 42, "sentiment_label": "neutral", "momentum_5d": -0.5, "momentum_20d": 1.0, "strength_index": 48, "sector_return": -0.3, "turnover_ratio": 1.8, "fund_flow": -3.0},
]


# ============================================================
# API 接口
# ============================================================

@router.get("/market/multi-index")
async def get_multi_index(
    codes: Optional[str] = Query(default="SH000001,SH000300,SZ399001,SZ399006", description="指数代码，逗号分隔"),
) -> dict:
    """
    获取多指数情绪数据

    返回四个主要指数的情绪评分、标签、涨跌幅等
    """
    code_list = [c.strip() for c in codes.split(",")]

    index_results: dict[str, CompositeResult] = {}
    items: list[dict] = []

    for code in code_list:
        if code in MOCK_INDEXES:
            data = MOCK_INDEXES[code]
            result = _compute_index_result(code, data)
            index_results[code] = result
            items.append({
                "index_code": code,
                "index_name": data["name"],
                "close": data["close"],
                "change_pct": data["change_pct"],
                "composite_score": result.composite_score,
                "sentiment_label": result.sentiment_label,
                "top3_factors": [
                    {
                        "factor_name": f.factor_name,
                        "score": f.score,
                        "label": f.label,
                        "is_extreme": f.is_extreme,
                    }
                    for f in result.top3_factors
                ],
                "trend_direction": result.trend_direction,
                "trend_strength": result.trend_strength,
                "is_extreme": result.is_extreme,
                "conclusion": result.conclusion,
            })

    # 计算综合情绪
    composite = calculate_composite_sentiment(index_results)

    return {
        "code": 0,
        "data": {
            "indexes": items,
            "composite": {
                "composite_score": composite.composite_score,
                "sentiment_label": composite.sentiment_label,
                "divergence_index": composite.divergence_index,
                "conclusion": composite.conclusion,
                "operation_advice": composite.operation_advice,
            },
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.get("/market/index/{code}")
async def get_index_detail(code: str) -> dict:
    """
    获取单个指数详细情绪数据

    包含7因子完整评分、历史趋势等
    """
    if code not in MOCK_INDEXES:
        return {"code": 404, "data": None, "message": f"指数 {code} 不存在"}

    data = MOCK_INDEXES[code]
    result = _compute_index_result(code, data)

    # 模拟5日历史
    today = date.today()
    history = []
    base_score = result.composite_score
    for i in range(5, 0, -1):
        d = today - timedelta(days=i)
        offset = (i - 3) * 2.5  # 制造趋势
        history.append({
            "date": d.isoformat(),
            "composite_score": round(base_score - offset, 1),
            "sentiment_label": result.sentiment_label,
        })

    # 当前日
    history.append({
        "date": today.isoformat(),
        "composite_score": result.composite_score,
        "sentiment_label": result.sentiment_label,
    })

    # 仓位建议
    position_advice = calculate_position(result.composite_score, result.sentiment_label)

    return {
        "code": 0,
        "data": {
            "index_code": code,
            "index_name": data["name"],
            "close": data["close"],
            "change_pct": data["change_pct"],
            "composite_score": result.composite_score,
            "sentiment_label": result.sentiment_label,
            "factor_scores": {
                name: {
                    "raw_value": fs.raw_value,
                    "score": fs.score,
                    "label": fs.label,
                    "is_extreme": fs.is_extreme,
                    "extreme_type": fs.extreme_type,
                }
                for name, fs in result.factor_scores.items()
            },
            "top3_factors": [
                {
                    "factor_name": f.factor_name,
                    "raw_value": f.raw_value,
                    "score": f.score,
                    "label": f.label,
                    "is_extreme": f.is_extreme,
                    "extreme_type": f.extreme_type,
                }
                for f in result.top3_factors
            ],
            "conclusion": result.conclusion,
            "operation_advice": result.operation_advice,
            "trend_direction": result.trend_direction,
            "trend_strength": result.trend_strength,
            "is_extreme": result.is_extreme,
            "abnormal_signals": result.abnormal_signals,
            "position_advice": {
                "suggested_position": position_advice.suggested_position,
                "cash_reserve": position_advice.cash_reserve,
                "action": position_advice.action,
                "reason": position_advice.reason,
                "risk_level": position_advice.risk_level,
            },
            "history": history,
        },
        "message": "ok",
    }


@router.get("/market/snapshot")
async def get_market_snapshot() -> dict:
    """
    市场快照（顶部状态条数据）

    返回关键指数摘要 + 全局情绪标签
    """
    items = []
    index_results: dict[str, CompositeResult] = {}

    for code, data in MOCK_INDEXES.items():
        result = _compute_index_result(code, data)
        index_results[code] = result
        items.append({
            "index_code": code,
            "index_name": data["name"],
            "close": data["close"],
            "change_pct": data["change_pct"],
            "composite_score": result.composite_score,
            "sentiment_label": result.sentiment_label,
        })

    composite = calculate_composite_sentiment(index_results)

    return {
        "code": 0,
        "data": {
            "indexes": items,
            "global_sentiment": composite.sentiment_label,
            "global_score": composite.composite_score,
            "divergence_index": composite.divergence_index,
            "conclusion": composite.conclusion,
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.get("/market/sector/{name}")
async def get_sector_detail(name: str) -> dict:
    """
    获取板块情绪详情

    Args:
        name: 板块名称（支持模糊匹配）
    """
    sector = None
    for s in MOCK_SECTORS:
        if name in s["sector_name"]:
            sector = s
            break

    if not sector:
        return {"code": 404, "data": None, "message": f"板块 {name} 不存在"}

    return {
        "code": 0,
        "data": sector,
        "message": "ok",
    }


@router.get("/market/recommendations")
async def get_recommendations() -> dict:
    """
    机会雷达推荐

    返回强势板块、超跌机会、稳健配置
    """
    result: RecommendationResult = generate_recommendations(MOCK_SECTORS, top_n=5)

    def _item_to_dict(item) -> dict:
        return {
            "sector_code": item.sector_code,
            "sector_name": item.sector_name,
            "sector_group": item.sector_group,
            "sentiment_score": item.sentiment_score,
            "sentiment_label": item.sentiment_label,
            "momentum_5d": item.momentum_5d,
            "momentum_20d": item.momentum_20d,
            "strength_index": item.strength_index,
            "opportunity_type": item.opportunity_type,
            "opportunity_reason": item.opportunity_reason,
            "recommended_funds": item.recommended_funds,
        }

    return {
        "code": 0,
        "data": {
            "strong_sectors": [_item_to_dict(i) for i in result.strong_sectors],
            "rebound_opportunities": [_item_to_dict(i) for i in result.rebound_opportunities],
            "steady_choices": [_item_to_dict(i) for i in result.steady_choices],
            "top_picks": [_item_to_dict(i) for i in result.top_picks],
            "summary": result.summary,
        },
        "message": "ok",
    }


@router.get("/market/sector-heatmap")
async def get_sector_heatmap() -> dict:
    """
    板块情绪热力图数据

    返回所有板块的情绪评分用于热力图展示
    """
    heatmap_data = []
    for s in MOCK_SECTORS:
        heatmap_data.append({
            "sector_code": s["sector_code"],
            "sector_name": s["sector_name"],
            "sector_group": s["sector_group"],
            "sentiment_score": s["sentiment_score"],
            "sentiment_label": s["sentiment_label"],
            "sector_return": s["sector_return"],
            "momentum_5d": s["momentum_5d"],
            "strength_index": s["strength_index"],
        })

    # 按分组聚合
    groups: dict[str, list[float]] = {}
    for h in heatmap_data:
        g = h["sector_group"]
        if g not in groups:
            groups[g] = []
        groups[g].append(h["sentiment_score"])

    group_summary = [
        {
            "group_name": g,
            "avg_score": round(sum(scores) / len(scores), 1),
            "sector_count": len(scores),
        }
        for g, scores in groups.items()
    ]

    return {
        "code": 0,
        "data": {
            "sectors": heatmap_data,
            "group_summary": group_summary,
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.get("/market/abnormal-check")
async def get_abnormal_check() -> dict:
    """
    异常检测

    检查所有指数是否存在极端信号
    """
    abnormal_items = []
    for code, data in MOCK_INDEXES.items():
        factor_scores = {
            "波动率": score_volatility(data["volatility"]),
            "换手率": score_turnover(data["turnover_ratio"]),
            "涨跌比": score_adv_decline(data["adv_decline_ratio"]),
            "新高占比": score_new_high(data["new_high_ratio"]),
            "融资融券": score_margin(data["margin_data"]),
            "股债比": score_bond_equity(data["bond_yield"], data["equity_yield"]),
            "RSI": score_rsi(data["rsi_value"]),
        }
        extremes = [
            {
                "factor_name": fs.factor_name,
                "score": fs.score,
                "extreme_type": fs.extreme_type,
            }
            for fs in factor_scores.values()
            if fs.is_extreme
        ]
        if extremes:
            abnormal_items.append({
                "index_code": code,
                "index_name": data["name"],
                "extremes": extremes,
            })

    return {
        "code": 0,
        "data": {
            "has_abnormal": len(abnormal_items) > 0,
            "abnormal_count": len(abnormal_items),
            "items": abnormal_items,
        },
        "message": "ok",
    }


@router.get("/market/trend-summary")
async def get_trend_summary() -> dict:
    """
    趋势摘要（5日微趋势数据）

    用于前端 MicroTrendBar 组件
    """
    today = date.today()
    trend_data: dict[str, list[dict]] = {}

    for code, data in MOCK_INDEXES.items():
        result = _compute_index_result(code, data)
        base = result.composite_score
        trend_data[code] = []
        for i in range(5, 0, -1):
            d = today - timedelta(days=i)
            offset = (3 - i) * 1.5
            s = round(base + offset, 1)
            trend_data[code].append({
                "date": d.isoformat(),
                "score": s,
                "label": "extreme_fear" if s < 20 else ("fear" if s < 40 else ("neutral" if s < 60 else ("greed" if s < 80 else "extreme_greed"))),
            })

    return {
        "code": 0,
        "data": {
            "trends": trend_data,
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }
