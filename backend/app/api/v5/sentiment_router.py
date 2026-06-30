"""
V5 Sentiment Router - 情绪分析相关路由
"""
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.services.sentiment_service import SentimentService
from app.api.v5.schemas import PositionAdviceRequest, PositionExecuteRequest

router = APIRouter(tags=["v5-sentiment"])


@router.get("/market/sentiment/{index_code}")
async def get_v5_sentiment(
    index_code: str,
    trade_date: Optional[str] = Query(default=None, description="交易日期 YYYY-MM-DD"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 指数情绪（14 因子 + 7 级信号 + 4 星置信度）

    返回完整流水线结果，用于前端信号详情页
    """
    service = SentimentService(db_session=session)
    result = await service.run_pipeline(index_code, trade_date)

    if "error" in result:
        return {"code": 404, "data": None, "message": result["error"]}

    return {"code": 0, "data": result, "message": "ok"}


@router.get("/market/multi-index")
async def get_v5_multi_index(
    codes: Optional[str] = Query(
        default="SH000001,SH000300,SZ399001,SZ399006",
        description="指数代码，逗号分隔",
    ),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取多指数 V5.0 情绪摘要

    返回简化结果（不含因子明细），用于首页仪表盘。
    优化：并行调用 pipeline + Redis 缓存 + 降级策略
    """
    service = SentimentService(db_session=session)
    code_list = [c.strip() for c in codes.split(",")]
    return await service.run_multi_index(code_list)


@router.get("/market/signal-lights/{index_code}")
async def get_v5_signal_lights(
    index_code: str,
    days: int = Query(default=3, description="查看最近N天信号"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 信号灯数据（三周期）

    返回最近N天的信号等级，用于 SignalLights 组件
    """
    service = SentimentService(db_session=session)
    return await service.get_signal_lights(index_code, days)


@router.get("/market/snapshot")
async def get_v5_market_snapshot(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    市场快照（顶部状态条数据）

    返回关键指数摘要 + 全局情绪标签（基于 V5 pipeline）。
    优化：并行调用 + Redis 缓存 + 降级策略
    """
    service = SentimentService(db_session=session)
    return await service.get_market_snapshot()


@router.get("/market/divergence")
async def get_divergence_alert(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    全指数背离检测（Dashboard 顶部预警横幅数据源）

    对4个默认指数运行价格-情绪背离检测，返回有背离信号的指数列表。
    缓存5分钟。
    """
    service = SentimentService(db_session=session)
    return await service.get_divergence_alert()


@router.get("/market/factor-radar")
async def get_factor_radar(
    index_code: str = Query(default="SH000300"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    因子雷达图数据（Dashboard 因子可视化）

    返回14因子的当前分位数值（百分位数），供 ECharts 雷达图使用。
    """
    service = SentimentService(db_session=session)
    return await service.get_factor_radar(index_code)
