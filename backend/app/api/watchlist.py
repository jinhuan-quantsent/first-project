"""
自选基金接口
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
from app.models.user_watchlist import UserWatchlist

router = APIRouter(prefix="/api/v5/watchlist")


class WatchlistAdd(BaseModel):
    """添加自选"""
    fund_code: str
    fund_name: str = ""
    notes: str = ""
    alert_threshold: float = 0.0


@router.get("/watchlist")
async def get_watchlist(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取自选列表"""
    stmt = (
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.sort_order.asc(), UserWatchlist.added_at.desc())
    )
    result = await session.execute(stmt)
    items = result.scalars().all()

    return {
        "code": 0,
        "data": {
            "items": [
                {
                    "id": item.id,
                    "fund_code": item.fund_code,
                    "fund_name": item.fund_name,
                    "added_at": item.added_at.isoformat() if item.added_at else "",
                    "notes": item.notes,
                    "alert_threshold": item.alert_threshold,
                    "sort_order": item.sort_order,
                    "current_nav": 1.0,
                    "daily_return": 0.0,
                    "week_return": 0.0,
                    "month_return": 0.0,
                }
                for item in items
            ],
            "total": len(items),
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.post("/watchlist", status_code=201)
async def add_watchlist_item(
    item: WatchlistAdd,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """添加自选"""
    # 计算排序序号
    count_stmt = select(func.count()).where(UserWatchlist.user_id == user_id)
    count_result = await session.execute(count_stmt)
    next_order = (count_result.scalar() or 0) + 1

    new_item = UserWatchlist(
        user_id=user_id,
        fund_code=item.fund_code,
        fund_name=item.fund_name or f"基金{item.fund_code}",
        notes=item.notes,
        alert_threshold=item.alert_threshold,
        sort_order=next_order,
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
            "added_at": new_item.added_at.isoformat() if new_item.added_at else "",
            "notes": new_item.notes,
            "alert_threshold": new_item.alert_threshold,
            "sort_order": new_item.sort_order,
        },
        "message": "添加成功",
    }


@router.delete("/watchlist/{item_id}")
async def delete_watchlist_item(
    item_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除自选"""
    stmt = (
        delete(UserWatchlist)
        .where(UserWatchlist.id == item_id, UserWatchlist.user_id == user_id)
        .returning(UserWatchlist.id)
    )
    result = await session.execute(stmt)
    deleted_id = result.scalar_one_or_none()

    if deleted_id is None:
        return {"code": 404, "data": None, "message": f"自选 {item_id} 不存在"}

    await session.commit()
    return {"code": 0, "data": None, "message": "删除成功"}
