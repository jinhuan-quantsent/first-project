"""
V5 Sentiment Router - 情绪分析相关路由
"""
from typing import Optional
from datetime import datetime, date

from fastapi import APIRouter, Query

from app.core.redis_client import cache_get, cache_set
from app.core.database import get_session_factory
from app.services.sentiment_service import SentimentService
from app.api.v5.schemas import PositionAdviceRequest, PositionExecuteRequest
from app.utils.code_format import to_tushare, to_display, is_index_code


def _normalize_index_code(index_code: str) -> str | None:
    """归一化指数代码，返回 Display 格式或 None"""
    if not is_index_code(index_code):
        return None
    return to_display(to_tushare(index_code))


router = APIRouter(tags=["v5-sentiment"])


@router.get("/market/sentiment/{index_code}")
async def get_v5_sentiment(
    index_code: str,
    trade_date: Optional[str] = Query(default=None, description="交易日期 YYYY-MM-DD"),
) -> dict:
    """
    获取 V5.0 指数情绪（14 因子 + 7 级信号 + 4 星置信度）

    返回完整流水线结果，用于前端信号详情页。
    路由层 Redis 缓存 5 分钟，命中则无需 DB session。
    """
    if trade_date is None:
        trade_date = date.today().isoformat()

    # 归一化指数代码（000300→SH000300）
    normalized = _normalize_index_code(index_code)
    if normalized is None:
        return {"code": 404, "data": None, "message": f"无效的指数代码: {index_code}"}
    index_code = normalized

    # 路由层缓存检查（先于 session 分配，避免连接池耗尽时阻塞）
    cache_key = f"v5:sentiment:{index_code}:{trade_date}"
    if trade_date == date.today().isoformat():
        cached = await cache_get(cache_key)
        if cached:
            return {"code": 0, "data": cached, "message": "ok", "cached": True}

    async with get_session_factory()() as session:
        service = SentimentService(db_session=session)
        result = await service.run_pipeline(index_code, trade_date)

    if "error" in result:
        return {"code": 404, "data": None, "message": result["error"]}

    # 写入路由层缓存（service 层也有缓存，双重保障）
    if trade_date == date.today().isoformat():
        try:
            await cache_set(cache_key, result, ttl=300)
        except Exception:
            pass

    return {"code": 0, "data": result, "message": "ok"}


@router.get("/market/multi-index")
async def get_v5_multi_index(
    codes: Optional[str] = Query(
        default="SH000001,SH000300,SZ399001,SZ399006",
        description="指数代码，逗号分隔",
    ),
) -> dict:
    """
    获取多指数 V5.0 情绪摘要

    返回简化结果（不含因子明细），用于首页仪表盘。
    优化：并行调用 + Redis 缓存 + 降级策略
    """
    from app.core.redis_client import cache_get, cache_set

    cache_key = "v5:multi_index:" + codes
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    async with get_session_factory()() as session:
        service = SentimentService(db_session=session)
        code_list = [c.strip() for c in codes.split(",")]
        result = await service.run_multi_index(code_list)

    # 提取 data（兼容 service 返回裸数据或 {code:0, data:...} 两种格式）
    if isinstance(result, dict) and "data" in result:
        data = result["data"]
    else:
        data = result

    try:
        await cache_set(cache_key, data, ttl=300)
    except Exception:
        pass

    return {"code": 0, "data": data, "message": "ok"}


@router.get("/market/signal-lights/{index_code}")
async def get_v5_signal_lights(
    index_code: str,
    days: int = Query(default=3, description="查看最近N天信号"),
) -> dict:
    """
    获取 V5.0 信号灯数据（三周期）

    返回最近N天的信号等级，用于 SignalLights 组件。
    路由层 Redis 缓存 5 分钟。
    """
    # 归一化指数代码
    normalized = _normalize_index_code(index_code)
    if normalized is None:
        return {"code": 404, "data": None, "message": f"无效的指数代码: {index_code}"}
    index_code = normalized

    cache_key = f"v5:signal_lights:{index_code}:{days}"
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    async with get_session_factory()() as session:
        service = SentimentService(db_session=session)
        result = await service.get_signal_lights(index_code, days)

    # 提取 data（兼容 service 返回裸数据或 {code:0, data:...} 两种格式）
    if isinstance(result, dict) and "data" in result:
        data = result["data"]
    else:
        data = result

    try:
        await cache_set(cache_key, data, ttl=300)
    except Exception:
        pass

    return {"code": 0, "data": data, "message": "ok"}


@router.get("/market/snapshot")
async def get_v5_market_snapshot() -> dict:
    """
    市场快照（顶部状态条数据）

    返回关键指数摘要 + 全局情绪标签（基于 V5 pipeline）。
    优化：并行调用 + Redis 缓存 + 降级策略。
    路由层额外缓存 5 分钟。
    """
    cache_key = "v5:market_snapshot"
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    async with get_session_factory()() as session:
        service = SentimentService(db_session=session)
        result = await service.get_market_snapshot()

    # 提取 data（兼容 service 返回裸数据或 {code:0, data:...} 两种格式）
    if isinstance(result, dict) and "data" in result:
        data = result["data"]
    else:
        data = result

    try:
        await cache_set(cache_key, data, ttl=300)
    except Exception:
        pass

    return {"code": 0, "data": data, "message": "ok"}


@router.get("/market/divergence")
async def get_divergence_alert() -> dict:
    """
    全指数背离检测（Dashboard 顶部预警横幅数据源）

    对4个默认指数运行价格-情绪背离检测，返回有背离信号的指数列表。
    路由层 Redis 缓存 5 分钟（service 层也有缓存，双重保障）。
    """
    cache_key = "v5:divergence_alert"
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    async with get_session_factory()() as session:
        service = SentimentService(db_session=session)
        result = await service.get_divergence_alert()

    # 提取 data（兼容 service 返回裸数据或 {code:0, data:...} 两种格式）
    if isinstance(result, dict) and "data" in result:
        data = result["data"]
    else:
        data = result

    try:
        await cache_set(cache_key, data, ttl=300)
    except Exception:
        pass

    return {"code": 0, "data": data, "message": "ok"}


@router.get("/market/factor-radar")
async def get_factor_radar(
    index_code: str = Query(default="SH000300"),
) -> dict:
    """
    因子雷达图数据（Dashboard 因子可视化）

    返回14因子的当前分位数值（百分位数），供 ECharts 雷达图使用。
    路由层 Redis 缓存 30 分钟。
    """
    # 归一化指数代码
    normalized = _normalize_index_code(index_code)
    if normalized is None:
        return {"code": 404, "data": None, "message": f"无效的指数代码: {index_code}"}
    index_code = normalized

    cache_key = f"v5:factor_radar:{index_code}"
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    async with get_session_factory()() as session:
        service = SentimentService(db_session=session)
        result = await service.get_factor_radar(index_code)

    # 提取 data（兼容 service 返回裸数据或 {code:0, data:...} 两种格式）
    if isinstance(result, dict) and "data" in result:
        data = result["data"]
    else:
        data = result

    try:
        await cache_set(cache_key, data, ttl=1800)
    except Exception:
        pass

    return {"code": 0, "data": data, "message": "ok"}
