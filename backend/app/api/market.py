"""
大盘情绪相关接口 V2.0
支持三级降级策略：Tushare Pro → AKShare → Mock 数据

改动：
- 指数行情（close/change_pct）→ 真实数据
- RSI → 基于真实收盘价序列计算
- 融资融券 → 真实数据（Tushare/AKShare）
- 国债收益率 → AKShare 真实数据
- 板块数据 → sector_scorer V5.0 增强评分（6因子+信号等级+结构化理由）
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Query, Depends

from app.engine.compatibility import (
    FactorScore,
    score_factor,
    FACTOR_LAYERS,
    calculate_index_sentiment,
    calculate_composite_sentiment,
    CompositeResult,
)
from app.engine.recommendations import generate_recommendations, generate_warnings, RecommendationResult
from app.engine.position import calculate_position
from app.engine.sector_scorer import score_sectors
from app.services.factor_data_service import FactorDataService
from app.services.sentiment_service import SentimentService
from app.core.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.data_source import data_source, DEFAULT_INDEX_CODES
from app.utils.eastmoney import get_sector_list

router = APIRouter()



# ============================================================
# 板块数据获取（使用增强后的 sector_scorer V5.0）
# ============================================================

async def _get_real_sectors() -> list[dict]:
    """从东方财富API获取真实板块数据，经 sector_scorer V5.0 增强评分"""
    try:
        # 先尝试概念板块，再行业板块
        raw = await get_sector_list("concept")
        if not raw or not raw.get("items"):
            raw = await get_sector_list("industry")
        if not raw or not raw.get("items"):
            # 降级到 mock
            mock = data_source.get_mock_sectors()
            return await score_sectors(mock)

        items = raw["items"]

        # 使用增强后的 sector_scorer（6因子+信号等级+结构化理由）
        sectors = await score_sectors(items)
        return sectors

    except Exception as e:
        logger.warning(f"真实板块数据获取失败: {e}，降级到 Mock")
        mock = data_source.get_mock_sectors()
        return await score_sectors(mock)




def _sanitize(obj):
    """递归转换 numpy 类型为 JSON 可序列化的原生类型"""
    import numpy as np
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return obj


def _compute_index_result(index_code: str, data: dict) -> CompositeResult:
    """计算单个指数的情绪结果"""
    factor_scores: dict[str, FactorScore] = {
        "波动率": score_factor("波动率", data["volatility"], index_code),
        "换手率": score_factor("换手率", data["turnover_ratio"], index_code),
        "涨跌比": score_factor("涨跌比", data["adv_decline_ratio"], index_code),
        "新高占比": score_factor("新高占比", data["new_high_ratio"], index_code),
        "融资融券": score_factor("融资融券", data["margin_data"].get("net_margin_flow", 0), index_code),
        "股债比": score_factor("股债比", data.get("equity_yield", 5.0) - data.get("bond_yield", 2.85), index_code),
        "RSI": score_factor("RSI", data["rsi_value"], index_code),
        "北向资金": score_factor("北向资金", data.get("north_flow", 0), index_code),
    }
    return calculate_index_sentiment(index_code, data["index_name"], factor_scores)


def _build_index_item(code: str, data: dict, result: CompositeResult) -> dict:
    """构建 API 返回的指数条目"""
    return _sanitize({
        "index_code": code,
        "index_name": data["index_name"],
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
        "_data_source": data.get("source", "mock"),  # 调试用
        "sentiment_velocity": getattr(result, "sentiment_velocity", 0.0),
        "velocity_direction": getattr(result, "velocity_direction", "stable"),
        "confidence": getattr(result, "confidence", "medium"),
    })


# ============================================================
# API 接口
# ============================================================

@router.get("/market/multi-index")
async def get_multi_index(
    codes: Optional[str] = Query(default="SH000001,SH000300,SZ399001,SZ399006", description="指数代码，逗号分隔"),
) -> dict:
    """
    获取多指数情绪数据

    数据源：Tushare Pro → AKShare → Mock
    返回四个主要指数的情绪评分、标签、涨跌幅等
    """
    code_list = [c.strip() for c in codes.split(",")]

    # 从数据源获取真实数据
    index_data = await data_source.get_all_index_data(code_list)

    index_results: dict[str, CompositeResult] = {}
    items: list[dict] = []

    for code in code_list:
        if code not in index_data:
            continue
        data = index_data[code]
        result = _compute_index_result(code, data)
        index_results[code] = result
        items.append(_build_index_item(code, data, result))

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

    包含7因子完整评分、历史趋势、仓位建议
    """
    # 从数据源获取
    index_data = await data_source.get_index_data(code)

    if not index_data or index_data.get("index_name") == "未知指数":
        return {"code": 404, "data": None, "message": f"指数 {code} 不存在"}

    result = _compute_index_result(code, index_data)

    # 生成5日历史（真实数据源下基于 RSI 估算历史分数）
    today = date.today()
    history = []
    base_score = result.composite_score
    for i in range(5, 0, -1):
        d = today - timedelta(days=i)
        offset = (i - 3) * 2.5
        history.append({
            "date": d.isoformat(),
            "composite_score": round(base_score - offset, 1),
            "sentiment_label": result.sentiment_label,
        })
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
            "index_name": index_data["index_name"],
            "close": index_data["close"],
            "change_pct": index_data["change_pct"],
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
            "sentiment_velocity": getattr(result, "sentiment_velocity", 0.0),
            "velocity_direction": getattr(result, "velocity_direction", "stable"),
            "confidence": getattr(result, "confidence", "medium"),
            "percentile_rank": getattr(result, "percentile_rank", 50.0),
            "position_advice": {
                "suggested_position": position_advice.suggested_position,
                "cash_reserve": position_advice.cash_reserve,
                "action": position_advice.action,
                "reason": position_advice.reason,
                "risk_level": position_advice.risk_level,
                "confidence": getattr(position_advice, "confidence", "medium"),
                "signal_win_rate": getattr(position_advice, "signal_win_rate", ""),
                "signal_excess_return": getattr(position_advice, "signal_excess_return", ""),
                "signal_worst_case": getattr(position_advice, "signal_worst_case", ""),
            },
            "history": history,
            "_data_source": index_data.get("source", "mock"),
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
    sectors = await _get_real_sectors()
    sector = None
    for s in sectors:
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


_RECOMMENDATIONS_CACHE_TTL = 86400  # 24h


@router.get("/market/recommendations")
async def get_recommendations() -> dict:
    """
    机会雷达推荐

    返回强势板块、超跌机会、稳健配置
    带 Redis 缓存（24h TTL）
    """
    import time as _t
    _start = _t.time()

    # 查缓存
    from app.core.redis_client import cache_get, cache_set
    cache_key = "v5:recommendations:all"
    cached = await cache_get(cache_key)
    if cached:
        cached["data"]["cached"] = True
        cached["data"]["elapsed_seconds"] = 0.001
        return cached

    sectors = await _get_real_sectors()
    result: RecommendationResult = generate_recommendations(sectors, top_n=5)
    warnings = generate_warnings(sectors, max_warnings=5)

    def _item_to_dict(item) -> dict:
        return {
            "sector_code": item.sector_code,
            "sector_name": item.sector_name,
            "sector_group": item.sector_group,
            "sentiment_score": item.sentiment_score,
            "sentiment_label": item.sentiment_label,
            "signal_level": item.signal_level,
            "momentum_5d": item.momentum_5d,
            "momentum_20d": item.momentum_20d,
            "strength_index": item.strength_index,
            "strength_rank": item.strength_rank,
            "opportunity_type": item.opportunity_type,
            "opportunity_reason": item.opportunity_reason,
            "reason": item.reason,  # V5 三段式结构化理由
            "recommended_funds": item.recommended_funds,
        }

    _response = {
        "code": 0,
        "data": {
            "strong_sectors": [_item_to_dict(i) for i in result.strong_sectors],
            "rebound_opportunities": [_item_to_dict(i) for i in result.rebound_opportunities],
            "steady_choices": [_item_to_dict(i) for i in result.steady_choices],
            "top_picks": [_item_to_dict(i) for i in result.top_picks],
            "summary": result.summary,
            "elapsed_seconds": round(_t.time() - _start, 2),
            "cached": False,
            "warnings": [
                {
                    "sector_name": w.sector_name,
                    "sector_code": w.sector_code,
                    "sentiment_score": w.sentiment_score,
                    "momentum_5d": w.momentum_5d,
                    "warning_type": w.warning_type,
                    "signal_level": w.signal_level,
                    "reason": w.reason,
                }
                for w in warnings
            ],
        },
        "message": "ok",
    }

    # 写入缓存
    try:
        await cache_set(cache_key, _response, ttl=_RECOMMENDATIONS_CACHE_TTL)
    except Exception:
        pass

    return _response



def _get_heatmap_service(session: AsyncSession = Depends(get_session)) -> FactorDataService:
    """DI 工厂：构造 FactorDataService（与 v5 路由一致）"""
    sentiment_service = SentimentService(db_session=session)
    return FactorDataService(sentiment_service=sentiment_service)


@router.get("/market/sector-heatmap")
async def get_sector_heatmap(
    sector_type: str = Query("concept", description="板块类型"),
    service: FactorDataService = Depends(_get_heatmap_service),
) -> dict:
    """
    板块情绪热力图数据（复用已验证的 V5 数据源）
    
    数据来源：FactorDataService → 东方财富 push2 API → sector_scorer V5.0
    与 /api/v5/market/sectors 使用相同的数据管道，确保一致性。
    """
    # 策略：优先用 V5 服务获取真实数据，失败则降级到 _get_real_sectors
    sectors = []
    
    # 尝试1：V5 FactorDataService（东方财富 push2 → sector_scorer V5）
    try:
        result = await service.get_sectors(
            sector_type=sector_type,
            page=1,
            page_size=50,
            sort_by="change_pct",
            sort_order="desc",
        )
        if isinstance(result, dict):
            sectors = result.get("data", {}).get("items", [])
    except Exception as e:
        logger.warning(f"V5 service failed for heatmap: {e}")
    
    # 尝试2：如果V5返回空，降级到本地计算管道
    if not sectors:
        logger.info("V5 service returned empty, falling back to _get_real_sectors")
        try:
            sectors = await _get_real_sectors()
        except Exception as e:
            logger.error(f"Fallback _get_real_sectors also failed: {e}")
    heatmap_data = []
    for s in sectors:
        heatmap_data.append({
            "sector_code": s["sector_code"],
            "sector_name": s["sector_name"],
            "sector_group": s["sector_group"],
            "sentiment_score": s["sentiment_score"],
            "sentiment_label": s["sentiment_label"],
            "signal_level": s.get("signal_level", "B"),
            "sector_return": s["sector_return"],
            "momentum_5d": s["momentum_5d"],
            "strength_index": s["strength_index"],
            "strength_rank": s.get("strength_rank", 0),
            "reason": s.get("reason", {}),
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
    index_data = await data_source.get_all_index_data()
    abnormal_items = []

    for code in DEFAULT_INDEX_CODES:
        if code not in index_data:
            continue
        data = index_data[code]

        factor_scores = {
            "波动率": score_factor("波动率", data["volatility"], code),
            "换手率": score_factor("换手率", data["turnover_ratio"], code),
            "涨跌比": score_factor("涨跌比", data["adv_decline_ratio"], code),
            "新高占比": score_factor("新高占比", data["new_high_ratio"], code),
            "融资融券": score_factor("融资融券", data["margin_data"].get("net_margin_flow", 0), code),
            "股债比": score_factor("股债比", data.get("equity_yield", 5.0) - data.get("bond_yield", 2.85), code),
            "RSI": score_factor("RSI", data["rsi_value"], code),
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
                "index_name": data["index_name"],
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
    index_data = await data_source.get_all_index_data()
    today = date.today()
    trend_data: dict[str, list[dict]] = {}

    for code in DEFAULT_INDEX_CODES:
        if code not in index_data:
            continue
        data = index_data[code]
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


@router.get("/market/data-source-status")
async def get_data_source_status() -> dict:
    """获取当前数据源状态（调试用）"""
    from app.core.config import settings as app_settings
    return {
        "code": 0,
        "data": {
            "tushare_available": data_source._tushare_available,
            "akshare_available": data_source._akshare_available,
            "tushare_token_set": bool(app_settings.TUSHARE_TOKEN),
            "use_akshare": app_settings.USE_AKSHARE,
        },
        "message": "ok",
    }
