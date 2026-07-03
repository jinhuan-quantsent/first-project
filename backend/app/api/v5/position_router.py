"""
V5 Position Router - 仓位管理相关路由
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.core.config import settings
from app.services.position_service import PositionService
from app.api.v5.schemas import PositionAdviceRequest, PositionExecuteRequest

router = APIRouter(tags=["v5-position"])


@router.post("/portfolio/position-advice")
async def get_v5_position_advice(
    req: PositionAdviceRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 仓位调整建议

    输入：fund_code + current_position_pct
    输出：PositionAdvice（5×7 矩阵 + 置信度修正 + 成本校验）
    """
    service = PositionService(db_session=session)
    return await service.get_position_advice(
        user_id=user_id,
        fund_code=req.fund_code,
        current_position_pct=req.current_position_pct,
    )


@router.post("/portfolio/position-execute")
async def execute_v5_position(
    req: PositionExecuteRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    执行 V5.0 仓位调整

    记录执行日志，更新用户持仓
    """
    service = PositionService(db_session=session)
    return await service.execute_position(
        user_id=user_id,
        fund_code=req.fund_code,
        target_position_pct=req.target_position_pct,
        signal_level=req.signal_level,
        confidence_stars=req.confidence_stars,
    )


@router.patch("/portfolio/{item_id}/market-value")
async def update_portfolio_market_value(
    item_id: int,
    payload: dict,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    更新持仓市值（行内编辑用）

    仅更新 market_value 字段，自动重算 total_return / return_rate
    """
    service = PositionService(db_session=session)
    new_market_value = payload.get("market_value")
    return await service.update_market_value(
        item_id=item_id,
        user_id=user_id,
        new_market_value=new_market_value,
    )


@router.get("/advice/dca/{index_code}")
async def get_v5_dca_advice(
    index_code: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 定投调整建议

    基于信号等级生成定投倍数和操作建议。
    """
    service = PositionService(db_session=session)
    return await service.get_dca_advice(index_code)



# ============================================================
# 盘中预演API路由 — GET /intraday-preview/{fund_code}
# ============================================================
from datetime import date as _date, datetime as _datetime, time as _time
from app.core.redis_client import cache_get


@router.get("/intraday-preview/{fund_code}")
async def get_intraday_preview(
    fund_code: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    获取盘中预演结果

    直接从 Redis 缓存读取 scheduler 预计算结果。
    不做实时计算（避免API延迟）。

    Returns: 预演结果 dict（含 is_preview=True 标记）
    """
    # 1. 检查全局开关
    global_switch = await cache_get("intraday_preview:global_switch")
    if global_switch == "off" or not settings.ENABLE_INTRADAY_PREVIEW:
        return {"code": 200, "data": None, "message": "盘中预演功能已关闭"}

    # 2. 检查交易时段
    now = _datetime.now()
    if now.time() < _time(9, 30) or now.time() > _time(15, 0):
        return {"code": 200, "data": None, "message": "非交易时段，预演不可用"}

    # 3. 从Redis读取缓存
    today_str = _date.today().isoformat()
    cache_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:{fund_code}:{user_id}"
    cached = await cache_get(cache_key)

    if cached and isinstance(cached, dict) and cached.get("is_preview"):
        return {"code": 0, "data": cached, "message": "ok"}

    # 4. 缓存不存在 -- 返回"数据未就绪"
    return {
        "code": 200,
        "data": {
            "is_preview": True,
            "fund_code": fund_code,
            "status": "pending",
            "message": "预演数据未就绪，请稍后刷新",
        },
        "message": "数据未就绪",
    }
