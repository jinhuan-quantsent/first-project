"""
自选基金接口
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class WatchlistAdd(BaseModel):
    """添加自选"""
    fund_code: str
    fund_name: str = ""
    notes: str = ""
    alert_threshold: float = 0.0


# Mock 自选数据
MOCK_WATCHLIST: list[dict] = [
    {
        "id": 1,
        "user_id": "demo_user",
        "fund_code": "320007",
        "fund_name": "诺安成长混合",
        "added_at": "2024-06-15T10:30:00",
        "notes": "半导体板块，关注AI芯片机会",
        "alert_threshold": 5.0,
        "sort_order": 1,
        "current_nav": 1.1250,
        "daily_return": 2.85,
        "week_return": 5.52,
        "month_return": 8.25,
    },
    {
        "id": 2,
        "user_id": "demo_user",
        "fund_code": "005827",
        "fund_name": "易方达蓝筹精选混合",
        "added_at": "2024-07-20T14:15:00",
        "notes": "核心资产配置",
        "alert_threshold": -3.0,
        "sort_order": 2,
        "current_nav": 2.1580,
        "daily_return": 0.15,
        "week_return": 0.85,
        "month_return": -1.52,
    },
    {
        "id": 3,
        "user_id": "demo_user",
        "fund_code": "012345",
        "fund_name": "招商中证白酒指数(LOF)A",
        "added_at": "2024-09-01T09:00:00",
        "notes": "等待白酒板块反弹",
        "alert_threshold": 0.0,
        "sort_order": 3,
        "current_nav": 0.9850,
        "daily_return": -1.25,
        "week_return": -3.52,
        "month_return": -7.85,
    },
]


@router.get("/watchlist")
async def get_watchlist(
    user_id: str = Query(default="demo_user", description="用户ID"),
) -> dict:
    """获取自选列表"""
    items = [
        {k: v for k, v in item.items() if k != "user_id"}
        for item in MOCK_WATCHLIST
    ]
    return {
        "code": 0,
        "data": {
            "items": items,
            "total": len(items),
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.post("/watchlist")
async def add_watchlist_item(item: WatchlistAdd) -> dict:
    """添加自选"""
    new_item = {
        "id": len(MOCK_WATCHLIST) + 1,
        "user_id": "demo_user",
        "fund_code": item.fund_code,
        "fund_name": item.fund_name or f"基金{item.fund_code}",
        "added_at": datetime.now().isoformat(),
        "notes": item.notes,
        "alert_threshold": item.alert_threshold,
        "sort_order": len(MOCK_WATCHLIST) + 1,
        "current_nav": 1.0,
        "daily_return": 0.0,
        "week_return": 0.0,
        "month_return": 0.0,
    }
    MOCK_WATCHLIST.append(new_item)
    return {
        "code": 0,
        "data": {k: v for k, v in new_item.items() if k != "user_id"},
        "message": "添加成功",
    }


@router.delete("/watchlist/{item_id}")
async def delete_watchlist_item(item_id: int) -> dict:
    """删除自选"""
    for i, existing in enumerate(MOCK_WATCHLIST):
        if existing["id"] == item_id:
            MOCK_WATCHLIST.pop(i)
            return {"code": 0, "data": None, "message": "删除成功"}
    return {"code": 404, "data": None, "message": f"自选 {item_id} 不存在"}
