"""
V5 Sector Router — 板块情绪 + 机会雷达路由

端点:
  GET /api/v5/sector/sentiment  — 板块情绪评分 (31个申万一级行业)
  GET /api/v5/sector/radar       — 机会雷达 (双轨制推荐引擎)
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, Query

from app.core.redis_client import cache_get, cache_set
from app.engine.sector_scorer import (
    score_sectors,
    score_sector_v5,
    V5_SECTOR_FACTOR_CONFIG,
)
from app.engine.recommendations import get_sector_recommendations

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["v5-sector"])


# ============================================================
# 工具函数
# ============================================================

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


def _enrich_factor_scores(factor_scores: dict) -> dict:
    """
    将 factor_scores 扩展为 {factor_name: {sigmoid_score, raw_percentile, weight, direction, reverse}}

    支持两种输入格式:
    - 旧格式: {factor_name: sigmoid_score} (float)
    - 新格式: {factor_name: {"score": float, "raw_percentile": float}} (dict)
    """
    enriched = {}
    for fname, val in factor_scores.items():
        cfg = V5_SECTOR_FACTOR_CONFIG.get(fname, {})
        # Handle both old (float) and new (dict) formats
        if isinstance(val, dict):
            score = val.get("score")
            raw_percentile = val.get("raw_percentile")
        else:
            score = val
            raw_percentile = None
        enriched[fname] = {
            "sigmoid_score": round(float(score), 1) if score is not None else None,
            "raw_percentile": raw_percentile,
            "weight": cfg.get("weight", 0),
            "direction": cfg.get("direction", ""),
            "reverse": cfg.get("reverse", False),
        }
    return enriched


def _format_sector_item(s: dict) -> dict:
    """格式化单个板块评分结果为 API 响应"""
    return _sanitize({
        "sector_code": s.get("sector_code", ""),
        "sector_name": s.get("sector_name", ""),
        "sector_group": s.get("sector_group", ""),
        "sentiment_score": round(s.get("sentiment_score", 50.0), 1),
        "sentiment_label": s.get("sentiment_label", ""),
        "signal_level": s.get("signal_level", "B"),
        "confidence_stars": s.get("confidence_stars", 0),
        "confidence_detail": s.get("confidence_detail", {}),
        "track": s.get("track", "excluded"),
        "triggered_defenses": s.get("triggered_defenses", []),
        "momentum_5d": s.get("momentum_5d", 0.0),
        "momentum_20d": s.get("momentum_20d", 0.0),
        "strength_index": s.get("strength_index", 50.0),
        "strength_rank": s.get("strength_rank", 0),
        "sector_return": s.get("sector_return", 0.0),
        "factor_completeness": s.get("factor_completeness", 0.0),
        "cold_start": s.get("cold_start", True),
        "factor_scores": _enrich_factor_scores(s.get("factor_scores", {})),
        "aggregation_detail": s.get("aggregation_detail", {}),
        "reason": s.get("reason", {}),
    })


def _format_opportunity_item(item) -> dict:
    """将 OpportunityItem dataclass 序列化为 dict"""
    return _sanitize({
        "sector_code": item.sector_code,
        "sector_name": item.sector_name,
        "sector_group": item.sector_group,
        "sentiment_score": round(item.sentiment_score, 1),
        "sentiment_label": item.sentiment_label,
        "signal_level": item.signal_level,
        "confidence_stars": item.confidence_stars,
        "track": item.track,
        "momentum_5d": item.momentum_5d,
        "momentum_20d": item.momentum_20d,
        "strength_index": item.strength_index,
        "strength_rank": item.strength_rank,
        "opportunity_type": item.opportunity_type,
        "opportunity_reason": item.opportunity_reason,
        "rank": item.rank,
        "reason": item.reason,
        "factor_scores": _enrich_factor_scores(item.factor_scores),
        "factor_completeness": item.factor_completeness,
        "cold_start": item.cold_start,
        "recommended_funds": item.recommended_funds,
    })


# ============================================================
# 端点
# ============================================================

@router.get("/sector/sentiment")
async def get_sector_sentiment(
    sector_code: Optional[str] = Query(
        default=None,
        description="申万一级行业代码 (如 801730)。不传则返回全部31个板块",
    ),
) -> dict:
    """
    板块情绪评分 (V5 三层流水线)

    返回31个申万一级行业的情绪评分、信号等级、置信度、因子明细等。
    如果指定 sector_code，只返回该板块的数据。

    - Layer 1: 分位数归一化 (factor_history → percentile 0-1)
    - Layer 2: Sigmoid 映射 (percentile → score 0-100)
    - Layer 3: 离散度动态加权 (weighted_sum × penalty)
    """
    start = time.time()
    try:
        # --- Cache layer ---
        cache_key = _SECTOR_SENTIMENT_CACHE_KEY
        if not sector_code:  # only cache full list request
            cached = await cache_get(cache_key)
            if cached:
                cached["data"]["cached"] = True
                cached["data"]["elapsed_seconds"] = round(time.time() - start, 3)
                return cached

        sector_data = await score_sectors()

        if not sector_data:
            return {"code": 404, "data": None, "message": "板块数据获取失败"}

        # 按 sector_code 过滤
        if sector_code:
            sector_data = [s for s in sector_data if s.get("sector_code") == sector_code]
            if not sector_data:
                return {"code": 404, "data": None,
                        "message": f"未找到板块代码: {sector_code}"}

        # 格式化输出
        sectors = [_format_sector_item(s) for s in sector_data]

        # ── 注入建仓评级到sectors列表 ──
        if settings.ENABLE_BUILD_RATING:
            try:
                ratings = await calculate_position_ratings_for_all()
                rating_map = {r.sector_code: r for r in ratings}
                for s in sectors:
                    r = rating_map.get(s.get("sector_code", ""))
                    if r:
                        s["build_rating"] = r.rating
                        s["build_reason"] = r.reason
                        s["build_color"] = RATING_CONFIG.get(r.rating, {}).get("color", "#6b7280")
                    else:
                        s["build_rating"] = "watch"
                        s["build_reason"] = "暂无评级数据"
                        s["build_color"] = "#6b7280"
            except Exception as e:
                logger.warning(f"建仓评级注入失败: {e}")

        # 统计
        total = len(sectors)
        track_counts = {"trend_follow": 0, "contrarian": 0, "excluded": 0}
        avg_score = 0.0
        for s in sectors:
            track_counts[s["track"]] = track_counts.get(s["track"], 0) + 1
            avg_score += s["sentiment_score"]
        avg_score = round(avg_score / total, 1) if total > 0 else 0

        elapsed = round(time.time() - start, 2)

        result = {
            "code": 0,
            "data": {
                "sectors": sectors,
                "summary": {
                    "total": total,
                    "avg_sentiment_score": avg_score,
                    "track_distribution": track_counts,
                    "factor_config": {
                        fname: {
                            "weight": cfg["weight"],
                            "direction": cfg["direction"],
                            "reverse": cfg["reverse"],
                        }
                        for fname, cfg in V5_SECTOR_FACTOR_CONFIG.items()
                    },
                },
                "elapsed_seconds": elapsed,
                "cached": False,
            },
            "message": "ok",
        }

        # Write cache (full list only)
        if not sector_code:
            await cache_set(cache_key, result, ttl=_SECTOR_SENTIMENT_CACHE_TTL)

        return result

    except Exception as e:
        logger.exception("板块情绪评分失败")
        return {"code": 500, "data": None, "message": f"服务器错误: {str(e)}"}




def _inject_build_rating_into_result(result_data: dict, ratings_data: list) -> dict:
    """注入建仓评级到radar响应的所有分组列表"""
    if not settings.ENABLE_BUILD_RATING:
        return result_data
    
    # Build lookup by sector_code
    rating_map = {}
    for r in ratings_data:
        rating_map[r.sector_code] = r
    
    # Inject into all sector-containing lists
    sector_list_keys = [
        "contrarian_opportunities", "trend_follow_opportunities",
        "all_recommendations", "strong_sectors",
        "rebound_opportunities", "steady_choices", "top_picks",
    ]
    
    for key in sector_list_keys:
        items = result_data.get(key, [])
        for item in items:
            if isinstance(item, dict) and "sector_code" in item:
                code = item.get("sector_code", "")
                r = rating_map.get(code)
                if r:
                    item["build_rating"] = r.rating
                    item["build_reason"] = r.reason
                    item["build_color"] = RATING_CONFIG.get(r.rating, {}).get("color", "#6b7280")
                else:
                    item["build_rating"] = "watch"
                    item["build_reason"] = "暂无评级数据"
                    item["build_color"] = "#6b7280"
    
    return result_data

@router.get("/sector/radar")
async def get_sector_radar(
    max_contrarian: int = Query(
        default=3, ge=1, le=10, description="逆向轨道最大推荐数"
    ),
    max_trend_follow: int = Query(
        default=5, ge=1, le=10, description="趋势轨道最大推荐数"
    ),
) -> dict:
    """
    机会雷达 (V5 双轨制推荐引擎)

    调用 sector_scorer.score_sectors() 获取板块评分，
    然后通过 generate_recommendations_v5() 生成双轨制推荐:

    - 逆向轨道: signal S+/S, 底部背离, 按分数升序 (越恐惧越有机会)
    - 趋势轨道: signal A/B/C, MA20上升, 按分数降序 (越贪婪趋势越强)
    - 排除区:   不符合上述任一条件
    """
    start = time.time()
    try:
        # --- Cache layer ---
        cache_key = _SECTOR_RADAR_CACHE_KEY
        cached = await cache_get(cache_key)
        if cached:
            cached["data"]["cached"] = True
            cached["data"]["elapsed_seconds"] = round(time.time() - start, 3)
            return cached

        # 调用一站式推荐引擎
        result = await get_sector_recommendations()

        if not result.all_recommendations and not result.contrarian_opportunities:
            # 可能是 score_sectors 失败
            return {
                "code": 404,
                "data": None,
                "message": result.summary or "板块数据获取失败",
            }

        # 序列化
        contrarian = [_format_opportunity_item(item) for item in result.contrarian_opportunities]
        trend_follow = [_format_opportunity_item(item) for item in result.trend_follow_opportunities]
        all_recs = [_format_opportunity_item(item) for item in result.all_recommendations]

        elapsed = round(time.time() - start, 2)

        response = {
            "code": 0,
            "data": {
                "contrarian_opportunities": contrarian,
                "trend_follow_opportunities": trend_follow,
                "all_recommendations": all_recs,
                # 向后兼容字段
                "strong_sectors": [_format_opportunity_item(item) for item in result.strong_sectors],
                "rebound_opportunities": [_format_opportunity_item(item) for item in result.rebound_opportunities],
                "steady_choices": [_format_opportunity_item(item) for item in result.steady_choices],
                "top_picks": [_format_opportunity_item(item) for item in result.top_picks],
                "summary": result.summary,
                # 统计
                "total_count": result.total_count,
                "contrarian_count": result.contrarian_count,
                "trend_follow_count": result.trend_follow_count,
                "excluded_count": result.excluded_count,
                # 因子配置
                "factor_config": {
                    fname: {
                        "weight": cfg["weight"],
                        "direction": cfg["direction"],
                        "reverse": cfg["reverse"],
                    }
                    for fname, cfg in V5_SECTOR_FACTOR_CONFIG.items()
                },
                "elapsed_seconds": elapsed,
                "cached": False,
            },
            "message": "ok",
        }

        # ── 注入建仓评级到radar分组列表 ──
        if settings.ENABLE_BUILD_RATING:
            try:
                ratings = await calculate_position_ratings_for_all()
                response["data"] = _inject_build_rating_into_result(response["data"], ratings)
            except Exception as e:
                logger.warning(f"建仓评级注入radar失败: {e}")

        # Write cache
        await cache_set(cache_key, response, ttl=_SECTOR_RADAR_CACHE_TTL)

        return response

    except Exception as e:
        logger.exception("机会雷达生成失败")
        return {"code": 500, "data": None, "message": f"服务器错误: {str(e)}"}


# ============================================================
# 建仓评级端点 (T4)
# ============================================================

from app.engine.position_rating import (
    calculate_position_rating,
    calculate_position_ratings_for_all,
    PositionRatingResult,
    RATING_CONFIG,
    _get_funds_by_sector as _get_sector_funds_from_db,
    _compute_ma20_rising as _calc_ma20_rising,
)
from app.engine.sector_scorer import score_sector_v5
from app.engine.trend_guard import _get_latest_div_factor
from app.core.redis_client import cache_get, cache_set


# ============================================================
# 建仓评级缓存配置
# ============================================================
_POS_RATING_CACHE_KEY_ALL = "v5:pos_rating:all"
_POS_RATING_CACHE_TTL = 86400  # 24小时（日频数据，无需频繁过期）
_POS_RATING_FUNDS_CACHE_TTL = 86400  # 24小时
_SECTOR_SENTIMENT_CACHE_KEY = "v5:sector:sentiment"
_SECTOR_SENTIMENT_CACHE_TTL = 86400  # 24小时（日频数据，一天变一次）
_SECTOR_RADAR_CACHE_KEY = "v5:sector:radar"
_SECTOR_RADAR_CACHE_TTL = 86400  # 24小时


def _format_position_rating_item(r: PositionRatingResult) -> dict:
    """格式化建仓评级结果为 API 响应"""
    return _sanitize({
        "sector_code": r.sector_code,
        "sector_name": r.sector_name,
        "rating": r.rating,
        "rating_label": r.rating_label,
        "rating_color": r.rating_color,
        "reason": r.reason,
        "signal_level": r.signal_level,
        "trend_track": r.trend_track,
        "track": r.trend_track,
        "position_suggestion": r.position_suggestion,
        "confidence_stars": r.confidence_stars,
        "composite_score": round(r.composite_score, 1),
        "turn_percentile": r.turn_percentile,
        "bottom_divergence": r.bottom_divergence,
        "funds": r.funds,
    })


@router.get("/sector/position-rating")
async def get_all_position_ratings() -> dict:
    """
    获取所有板块的建仓评级摘要

    返回23个active一级板块的4档建仓评级:
    - strong(强烈·绿): 逆向轨道 S+ + 强底背离 + 置信度≥3
    - cautious(谨慎·黄): 顺势轨道 A/B + MA20上升 + TURN<90% + 置信度≥2
    - watch(观望·灰): C信号 / 置信度<2 / TURN 90-95%
    - forbidden(禁止·红): E信号 / D信号 / TURN>95%
    """
    start = time.time()
    try:
        # 先查缓存
        cached = await cache_get(_POS_RATING_CACHE_KEY_ALL)
        if cached:
            elapsed = round(time.time() - start, 3)
            return {
                "code": 0,
                "data": {
                    "sectors": cached["sectors"],
                    "summary": cached["summary"],
                    "elapsed_seconds": elapsed,
                    "cached": True,
                },
                "message": "ok",
            }

        # 缓存未命中，计算
        results = await calculate_position_ratings_for_all()

        if not results:
            return {"code": 404, "data": None, "message": "建仓评级数据获取失败"}

        sectors = [_format_position_rating_item(r) for r in results]

        # 统计
        rating_counts = {"strong": 0, "cautious": 0, "watch": 0, "forbidden": 0}
        for s in sectors:
            rating_counts[s["rating"]] = rating_counts.get(s["rating"], 0) + 1

        summary = {
            "total": len(sectors),
            "rating_distribution": rating_counts,
        }

        elapsed = round(time.time() - start, 2)

        # 写入缓存
        await cache_set(_POS_RATING_CACHE_KEY_ALL, {"sectors": sectors, "summary": summary}, ttl=_POS_RATING_CACHE_TTL)

        return {
            "code": 0,
            "data": {
                "sectors": sectors,
                "summary": summary,
                "elapsed_seconds": elapsed,
                "cached": False,
            },
            "message": "ok",
        }

    except Exception as e:
        logger.exception("建仓评级摘要获取失败")
        return {"code": 500, "data": None, "message": f"服务器错误: {str(e)}"}


@router.get("/sector/position-rating/{sector_code}")
async def get_position_rating(sector_code: str) -> dict:
    """
    获取单个板块的建仓评级详情（含基金列表）

    返回该板块的4档评级 + 关联基金列表（含一级active + 二级reserved）
    """
    start = time.time()
    try:
        # 先查单板块缓存
        cache_key = f"v5:pos_rating:{sector_code}"
        cached = await cache_get(cache_key)
        if cached:
            elapsed = round(time.time() - start, 3)
            return {
                "code": 0,
                "data": cached,
                "elapsed_seconds": elapsed,
                "cached": True,
                "message": "ok",
            }

        # 单板块缓存未命中，查全板块缓存
        all_cached = await cache_get(_POS_RATING_CACHE_KEY_ALL)
        if all_cached:
            for item in all_cached["sectors"]:
                if item["sector_code"] == sector_code:
                    # 补充基金列表
                    all_funds = await _get_sector_funds_from_db(sector_code)
                    for fund in all_funds:
                        fund["rating"] = item["rating"]
                        fund["rating_reason"] = item["reason"]
                    item["funds"] = all_funds
                    await cache_set(cache_key, item, ttl=_POS_RATING_CACHE_TTL)
                    elapsed = round(time.time() - start, 3)
                    return {
                        "code": 0,
                        "data": item,
                        "elapsed_seconds": elapsed,
                        "cached": True,
                        "message": "ok",
                    }

        # 都没命中，计算全部
        results = await calculate_position_ratings_for_all()

        target = None
        for r in results:
            if r.sector_code == sector_code:
                target = r
                break

        if target is None:
            # 可能是 unavailable 板块或不存在
            funds = await _get_sector_funds_from_db(sector_code)
            if not funds:
                return {"code": 404, "data": None,
                        "message": f"未找到板块代码: {sector_code}"}
            # unavailable 板块返回特殊评级
            return {
                "code": 0,
                "data": {
                    "sector_code": sector_code,
                    "rating": "forbidden",
                    "rating_label": "禁止",
                    "rating_color": "#dc2626",
                    "reason": "该板块无可用基金，禁止建仓",
                    "funds": funds,
                    "note": "该板块基金状态为unavailable或reserved",
                },
                "message": "ok",
            }

        # 补充二级 reserved 基金
        all_funds = await _get_sector_funds_from_db(sector_code)
        # 标注评级
        for fund in all_funds:
            fund["rating"] = target.rating
            fund["rating_reason"] = target.reason
        target.funds = all_funds

        item = _format_position_rating_item(target)
        # 二级赛道
        l2 = [f for f in all_funds if f.get("fund_level") == 2]
        item["level2_sectors"] = [{"fund_code": f.get("fund_code",""), "fund_name": f.get("fund_name",""), "track_index": f.get("track_index",""), "track_index_code": f.get("track_index_code",""), "sub_sector": f.get("sub_sector",""), "build_rating": f.get("rating","watch")} for f in l2]
        item["level2_hint"] = "二级赛道已激活" if l2 else "暂无二级赛道数据"
        elapsed = round(time.time() - start, 2)

        # 写入缓存
        await cache_set(cache_key, item, ttl=_POS_RATING_CACHE_TTL)

        return {
            "code": 0,
            "data": item,
            "elapsed_seconds": elapsed,
            "cached": False,
            "message": "ok",
        }

    except Exception as e:
        logger.exception("建仓评级详情获取失败")
        return {"code": 500, "data": None, "message": f"服务器错误: {str(e)}"}


@router.get("/sector/position-rating/{sector_code}/funds")
async def get_sector_funds(sector_code: str) -> dict:
    """
    获取板块关联的基金列表

    返回 position_rating_fund_map 中该板块的所有基金
    (含 active 一级 + reserved 二级 + unavailable)
    """
    try:
        # 查缓存
        funds_cache_key = f"v5:pos_rating_funds:{sector_code}"
        cached = await cache_get(funds_cache_key)
        if cached:
            return {"code": 0, "data": cached, "cached": True, "message": "ok"}

        funds = await _get_sector_funds_from_db(sector_code)
        if not funds:
            return {"code": 404, "data": None,
                    "message": f"未找到板块 {sector_code} 的基金映射"}

        result = {
            "sector_code": sector_code,
            "funds": funds,
            "total": len(funds),
        }

        await cache_set(funds_cache_key, result, ttl=_POS_RATING_FUNDS_CACHE_TTL)

        return {"code": 0, "data": result, "cached": False, "message": "ok"}

    except Exception as e:
        logger.exception("板块基金列表获取失败")
        return {"code": 500, "data": None, "message": f"服务器错误: {str(e)}"}


@router.get("/sector/{sector_code}/detail")
async def get_sector_detail(sector_code: str) -> dict:
    """
    板块详情接口 — 情绪数据+建仓评级+基金列表

    返回:
      - sector 情绪数据 (score_sectors)
      - build_rating 建仓评级
      - funds 一级基金列表 (active)
      - factor_scores 因子详情
    """
    # 路由层缓存检查（先于 score_sectors 计算）
    cache_key = f"v5:sector_detail:{sector_code}"
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    try:
        from app.engine.sector_scorer import score_sectors
        
        # 1. 获取板块情绪数据
        sector_data = await score_sectors()
        target = None
        for s in sector_data:
            if s.get("sector_code") == sector_code:
                target = s
                break
        
        if not target:
            return {"code": 404, "data": None, "message": f"未找到板块: {sector_code}"}
        
        # 2. 获取建仓评级
        build_rating_info = {}
        if settings.ENABLE_BUILD_RATING:
            try:
                ratings = await calculate_position_ratings_for_all()
                for r in ratings:
                    if r.sector_code == sector_code:
                        build_rating_info = {
                            "rating": r.rating,
                            "reason": r.reason,
                            "color": RATING_CONFIG.get(r.rating, {}).get("color", "#6b7280"),
                            "label": RATING_CONFIG.get(r.rating, {}).get("label", "观望"),
                            "position_suggestion": r.position_suggestion,
                            "confidence_stars": r.confidence_stars,
                        }
                        break
            except Exception as e:
                logger.warning(f"建仓评级计算失败: {e}")
        
        # 3. 获取基金列表
        funds = []
        try:
            funds = await _get_sector_funds_from_db(sector_code)
            # 标注评级
            for fund in funds:
                fund["build_rating"] = build_rating_info.get("rating", "watch")
                fund["build_reason"] = build_rating_info.get("reason", "")
        except Exception as e:
            logger.warning(f"基金列表获取失败: {e}")
        
        # 二级赛道（已激活，从基金列表中提取level=2）
        level2_funds = [f for f in funds if f.get("fund_level") == 2]
        level2_sectors = []
        for f in level2_funds:
            level2_sectors.append({
                "fund_code": f.get("fund_code", ""),
                "fund_name": f.get("fund_name", ""),
                "track_index": f.get("track_index", ""),
                "track_index_code": f.get("track_index_code", ""),
                "sub_sector": f.get("sub_sector", ""),
                "fit_degree": f.get("fit_degree", 0),
                "build_rating": f.get("build_rating", "watch"),
            })
        
        result = {
            **target,
            "build_rating_info": build_rating_info,
            "funds": funds,
            # 二级赛道（二期置灰）
            "level2_sectors": level2_sectors,
            "level2_hint": "二级赛道已激活" if level2_sectors else "暂无二级赛道数据",
        }
        
        # 写入路由层缓存（30 分钟）
        try:
            await cache_set(cache_key, result, ttl=1800)
        except Exception:
            pass
        
        return {"code": 0, "data": result, "message": "ok", "cached": False}
    
    except Exception as e:
        logger.exception(f"板块详情获取失败: {sector_code}")
        return {"code": 500, "data": None, "message": f"服务器错误: {str(e)}"}
