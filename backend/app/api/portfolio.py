"""
持仓管理接口
V4.0：注入 get_current_user，Mock → ORM CRUD
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models.user_portfolio import UserPortfolio

router = APIRouter()


class PortfolioItem(BaseModel):
    """持仓项"""
    fund_code: str
    fund_name: str = ""
    fund_type: str = ""
    holding_shares: float = 0.0
    cost_nav: float = 0.0
    current_nav: float = 0.0
    buy_date: Optional[str] = None
    portfolio_tag: str = "core"
    weight_pct: float = 0.0


@router.get("/portfolio")
async def get_portfolio(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取用户持仓列表"""
    stmt = select(UserPortfolio).where(UserPortfolio.user_id == user_id)
    result = await session.execute(stmt)
    items = result.scalars().all()

    item_list = [
        {
            "id": item.id,
            "fund_code": item.fund_code,
            "fund_name": item.fund_name,
            "fund_type": item.fund_type,
            "holding_shares": item.holding_shares,
            "cost_nav": item.cost_nav,
            "current_nav": item.current_nav,
            "market_value": item.market_value,
            "total_return": item.total_return,
            "return_rate": item.return_rate,
            "daily_return": item.daily_return,
            "buy_date": item.buy_date.isoformat() if item.buy_date else "",
            "portfolio_tag": item.portfolio_tag,
            "weight_pct": item.weight_pct,
        }
        for item in items
    ]

    total_value = sum(it["market_value"] for it in item_list)
    total_return = sum(it["total_return"] for it in item_list)
    total_cost = sum(it["cost_nav"] * it["holding_shares"] for it in item_list)
    total_return_rate = round((total_value / total_cost - 1) * 100, 2) if total_cost > 0 else 0.0

    core_items = [it for it in item_list if it["portfolio_tag"] == "core"]
    satellite_items = [it for it in item_list if it["portfolio_tag"] == "satellite"]
    core_value = sum(it["market_value"] for it in core_items)
    satellite_value = sum(it["market_value"] for it in satellite_items)

    return {
        "code": 0,
        "data": {
            "items": item_list,
            "summary": {
                "total_value": round(total_value, 2),
                "total_return": round(total_return, 2),
                "total_return_rate": total_return_rate,
                "daily_return": round(sum(it["daily_return"] for it in item_list), 2),
                "fund_count": len(item_list),
                "core_ratio": round(core_value / total_value * 100, 1) if total_value > 0 else 0,
                "satellite_ratio": round(satellite_value / total_value * 100, 1) if total_value > 0 else 0,
            },
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.post("/portfolio", status_code=201)
async def add_portfolio_item(
    item: PortfolioItem,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """添加持仓"""
    market_value = round(item.holding_shares * item.current_nav, 2)
    total_return = round((item.current_nav - item.cost_nav) * item.holding_shares, 2)
    return_rate = round((item.current_nav / item.cost_nav - 1) * 100, 2) if item.cost_nav > 0 else 0

    new_item = UserPortfolio(
        user_id=user_id,
        fund_code=item.fund_code,
        fund_name=item.fund_name or f"基金{item.fund_code}",
        fund_type=item.fund_type,
        holding_shares=item.holding_shares,
        cost_nav=item.cost_nav,
        current_nav=item.current_nav,
        market_value=market_value,
        total_return=total_return,
        return_rate=return_rate,
        daily_return=round(market_value * 0.005, 2),
        buy_date=item.buy_date,
        portfolio_tag=item.portfolio_tag,
        weight_pct=item.weight_pct,
    )
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)

    return {
        "code": 0,
        "data": {
            "id": new_item.id,
            "fund_code": new_item.fund_code,
            "fund_name": new_item.fund_name,
            "market_value": new_item.market_value,
            "total_return": new_item.total_return,
            "return_rate": new_item.return_rate,
        },
        "message": "添加成功",
    }


@router.put("/portfolio/{item_id}")
async def update_portfolio_item(
    item_id: int,
    item: PortfolioItem,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """更新持仓"""
    stmt = select(UserPortfolio).where(
        UserPortfolio.id == item_id, UserPortfolio.user_id == user_id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if not existing:
        return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}

    market_value = round(item.holding_shares * item.current_nav, 2)
    total_return = round((item.current_nav - item.cost_nav) * item.holding_shares, 2)
    return_rate = round((item.current_nav / item.cost_nav - 1) * 100, 2) if item.cost_nav > 0 else 0

    existing.fund_code = item.fund_code
    existing.fund_name = item.fund_name
    existing.fund_type = item.fund_type
    existing.holding_shares = item.holding_shares
    existing.cost_nav = item.cost_nav
    existing.current_nav = item.current_nav
    existing.market_value = market_value
    existing.total_return = total_return
    existing.return_rate = return_rate
    existing.daily_return = round(market_value * 0.005, 2)
    existing.portfolio_tag = item.portfolio_tag
    existing.weight_pct = item.weight_pct

    await session.commit()

    return {"code": 0, "data": {"id": existing.id}, "message": "更新成功"}


@router.delete("/portfolio/{item_id}")
async def delete_portfolio_item(
    item_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除持仓"""
    stmt = (
        delete(UserPortfolio)
        .where(UserPortfolio.id == item_id, UserPortfolio.user_id == user_id)
        .returning(UserPortfolio.id)
    )
    result = await session.execute(stmt)
    deleted_id = result.scalar_one_or_none()

    if deleted_id is None:
        return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}

    await session.commit()
    return {"code": 0, "data": None, "message": "删除成功"}


@router.get("/portfolio/overlap")
async def get_portfolio_overlap(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """持仓重叠分析"""
    # 基于用户实际持仓进行 Mock 重叠分析
    stmt = select(UserPortfolio).where(UserPortfolio.user_id == user_id)
    result = await session.execute(stmt)
    items = result.scalars().all()

    fund_names = [it.fund_name for it in items if it.fund_name]

    overlap_data: list[dict] = []
    for i in range(len(fund_names)):
        for j in range(i + 1, len(fund_names)):
            overlap_data.append({
                "pair": [fund_names[i], fund_names[j]],
                "overlap_score": round(20 + (i + j) * 3 % 40, 1),
                "overlap_sectors": ["消费", "金融"],
                "suggestion": "建议关注持仓分散度",
            })

    return {
        "code": 0,
        "data": {
            "overall_overlap_score": 32.8 if not overlap_data else round(sum(d["overlap_score"] for d in overlap_data) / len(overlap_data), 1),
            "overlap_level": "medium",
            "details": overlap_data or [],
            "suggestion": "整体持仓重叠度中等，建议增加不同风格的基金以分散风险",
        },
        "message": "ok",
    }
