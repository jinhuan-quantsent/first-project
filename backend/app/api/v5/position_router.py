"""
V5 Position Router - 仓位管理相关路由
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
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
