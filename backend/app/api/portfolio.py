"""
持仓管理接口
CRUD + 持仓重叠分析
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class PortfolioItem(BaseModel):
    """持仓项"""
    fund_code: str
    fund_name: str = ""
    fund_type: str = ""
    holding_shares: float = 0.0
    cost_nav: float = 0.0
    current_nav: float = 0.0
    market_value: float = 0.0
    total_return: float = 0.0
    return_rate: float = 0.0
    daily_return: float = 0.0
    buy_date: Optional[str] = None
    portfolio_tag: str = "core"
    weight_pct: float = 0.0


# Mock 持仓数据
MOCK_PORTFOLIO: list[dict] = [
    {
        "id": 1,
        "user_id": "demo_user",
        "fund_code": "000001",
        "fund_name": "华夏成长混合",
        "fund_type": "混合型",
        "holding_shares": 10000.0,
        "cost_nav": 1.3520,
        "current_nav": 1.5240,
        "market_value": 15240.0,
        "total_return": 1720.0,
        "return_rate": 12.72,
        "daily_return": 79.25,
        "buy_date": "2024-01-15",
        "portfolio_tag": "core",
        "weight_pct": 35.0,
    },
    {
        "id": 2,
        "user_id": "demo_user",
        "fund_code": "320007",
        "fund_name": "诺安成长混合",
        "fund_type": "混合型",
        "holding_shares": 8000.0,
        "cost_nav": 0.9850,
        "current_nav": 1.1250,
        "market_value": 9000.0,
        "total_return": 1120.0,
        "return_rate": 14.21,
        "daily_return": 256.5,
        "buy_date": "2024-03-20",
        "portfolio_tag": "satellite",
        "weight_pct": 20.7,
    },
    {
        "id": 3,
        "user_id": "demo_user",
        "fund_code": "005827",
        "fund_name": "易方达蓝筹精选混合",
        "fund_type": "混合型",
        "holding_shares": 5000.0,
        "cost_nav": 2.0520,
        "current_nav": 2.1580,
        "market_value": 10790.0,
        "total_return": 530.0,
        "return_rate": 5.17,
        "daily_return": 16.19,
        "buy_date": "2024-06-10",
        "portfolio_tag": "core",
        "weight_pct": 24.8,
    },
    {
        "id": 4,
        "user_id": "demo_user",
        "fund_code": "110022",
        "fund_name": "易方达消费行业股票",
        "fund_type": "股票型",
        "holding_shares": 2000.0,
        "cost_nav": 4.1250,
        "current_nav": 3.8520,
        "market_value": 7704.0,
        "total_return": -546.0,
        "return_rate": -6.62,
        "daily_return": -65.48,
        "buy_date": "2024-08-05",
        "portfolio_tag": "satellite",
        "weight_pct": 17.7,
    },
]


@router.get("/portfolio")
async def get_portfolio(
    user_id: str = Query(default="demo_user", description="用户ID"),
) -> dict:
    """获取用户持仓列表"""
    items = [
        {k: v for k, v in item.items() if k != "user_id"}
        for item in MOCK_PORTFOLIO
    ]

    total_value = sum(item["market_value"] for item in items)
    total_return = sum(item["total_return"] for item in items)
    total_cost = sum(item["cost_nav"] * item["holding_shares"] for item in items)
    total_return_rate = round((total_value / total_cost - 1) * 100, 2) if total_cost > 0 else 0.0

    # 按标签分组
    core_items = [it for it in items if it["portfolio_tag"] == "core"]
    satellite_items = [it for it in items if it["portfolio_tag"] == "satellite"]
    core_value = sum(it["market_value"] for it in core_items)
    satellite_value = sum(it["market_value"] for it in satellite_items)

    return {
        "code": 0,
        "data": {
            "items": items,
            "summary": {
                "total_value": round(total_value, 2),
                "total_return": round(total_return, 2),
                "total_return_rate": total_return_rate,
                "daily_return": round(sum(item["daily_return"] for item in items), 2),
                "fund_count": len(items),
                "core_ratio": round(core_value / total_value * 100, 1) if total_value > 0 else 0,
                "satellite_ratio": round(satellite_value / total_value * 100, 1) if total_value > 0 else 0,
            },
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.post("/portfolio")
async def add_portfolio_item(item: PortfolioItem) -> dict:
    """添加持仓"""
    new_item = item.model_dump()
    new_item["id"] = len(MOCK_PORTFOLIO) + 1
    new_item["user_id"] = "demo_user"
    new_item["market_value"] = round(item.holding_shares * item.current_nav, 2)
    new_item["total_return"] = round((item.current_nav - item.cost_nav) * item.holding_shares, 2)
    new_item["return_rate"] = round((item.current_nav / item.cost_nav - 1) * 100, 2) if item.cost_nav > 0 else 0
    new_item["daily_return"] = round(new_item["market_value"] * 0.005, 2)

    MOCK_PORTFOLIO.append(new_item)
    return {
        "code": 0,
        "data": new_item,
        "message": "添加成功",
    }


@router.put("/portfolio/{item_id}")
async def update_portfolio_item(item_id: int, item: PortfolioItem) -> dict:
    """更新持仓"""
    for i, existing in enumerate(MOCK_PORTFOLIO):
        if existing["id"] == item_id:
            updated = item.model_dump()
            updated["id"] = item_id
            updated["user_id"] = "demo_user"
            updated["market_value"] = round(item.holding_shares * item.current_nav, 2)
            updated["total_return"] = round((item.current_nav - item.cost_nav) * item.holding_shares, 2)
            updated["return_rate"] = round((item.current_nav / item.cost_nav - 1) * 100, 2) if item.cost_nav > 0 else 0
            MOCK_PORTFOLIO[i] = updated
            return {"code": 0, "data": updated, "message": "更新成功"}
    return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}


@router.delete("/portfolio/{item_id}")
async def delete_portfolio_item(item_id: int) -> dict:
    """删除持仓"""
    for i, existing in enumerate(MOCK_PORTFOLIO):
        if existing["id"] == item_id:
            MOCK_PORTFOLIO.pop(i)
            return {"code": 0, "data": None, "message": "删除成功"}
    return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}


@router.get("/portfolio/overlap")
async def get_portfolio_overlap(
    user_id: str = Query(default="demo_user", description="用户ID"),
) -> dict:
    """
    持仓重叠分析

    分析用户持仓基金之间的持仓重叠度（基于跟踪指数和板块）
    """
    # Mock 重叠分析
    overlap_data = [
        {
            "pair": ["易方达蓝筹精选混合", "华夏成长混合"],
            "overlap_score": 45.2,
            "overlap_sectors": ["白酒", "金融", "消费"],
            "suggestion": "两只基金在消费和金融板块有较高重叠，建议关注分散度",
        },
        {
            "pair": ["诺安成长混合", "华夏成长混合"],
            "overlap_score": 18.5,
            "overlap_sectors": ["科技"],
            "suggestion": "重叠度较低，配置较为分散",
        },
    ]

    return {
        "code": 0,
        "data": {
            "overall_overlap_score": 32.8,
            "overlap_level": "medium",  # low/medium/high
            "details": overlap_data,
            "suggestion": "整体持仓重叠度中等，建议增加不同风格的基金以分散风险",
        },
        "message": "ok",
    }
