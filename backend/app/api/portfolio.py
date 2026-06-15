"""
持仓管理接口
V4.0：注入 get_current_user，Mock → ORM CRUD
V5.0：新增仓位建议接口（使用 V5 引擎）
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models.user_portfolio import UserPortfolio

router = APIRouter(prefix="/api/v5/portfolio")


# ============================================================
# Pydantic 模型
# ============================================================

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


class PositionAdviceResponse(BaseModel):
    """V5.0 仓位建议响应"""
    fund_code: str
    current_position_pct: float
    target_position_pct: float
    action: str  # increase/hold/decrease
    signal_level: str
    confidence_stars: int
    reason: str


@router.get("")
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


@router.post("", status_code=201)
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


@router.put("/{item_id}")
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


@router.delete("/{item_id}")
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


@router.get("/overlap")
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


# ============================================================
# V5.0 仓位建议接口
# ============================================================

@router.get("/position-v5")
async def get_position_v5(
    fund_code: str = Query(..., description="基金代码"),
    current_position_pct: float = Query(..., description="当前仓位百分比 (0-1)"),
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    V5.0 仓位调整建议

    使用 V5 引擎（11因子 + 7级信号 + 5×7仓位矩阵）
    """
    from app.api.v5 import _run_v5_pipeline
    from app.engine.position_v5 import PositionEngineV5

    # 获取市场信号（默认沪深300）
    result = await _run_v5_pipeline("SH000300", db_session=session)
    if "error" in result:
        return {"code": 500, "data": None, "message": "无法获取市场信号"}

    signal_level = result["signal_level"]
    confidence_stars = result["confidence_stars"]

    # 计算仓位建议
    position_engine = PositionEngineV5(session)
    advice = await position_engine.calculate(
        user_id=user_id,
        fund_code=fund_code,
        current_position_pct=current_position_pct,
        signal_level=signal_level,
        confidence_stars=confidence_stars,
    )

    return {"code": 0, "data": advice, "message": "ok"}


# ============================================================
# V5.0 历史建议 & 交易记录（Stub）
# ============================================================

@router.get("/advice-history")
async def get_advice_history(
    fund_code: Optional[str] = Query(default=None),
    page: int = Query(default=1),
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取仓位建议历史（Stub - 返回空列表）"""
    return {
        "code": 0,
        "data": {
            "items": [],
            "stats": {
                "total_advice": 0,
                "executed": 0,
                "pending": 0,
            },
        },
        "message": "ok",
    }


@router.get("/trade-records")
async def get_trade_records(
    fund_code: Optional[str] = Query(default=None),
    page: int = Query(default=1),
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取交易记录（Stub - 返回空列表）"""
    return {
        "code": 0,
        "data": {
            "items": [],
        },
        "message": "ok",
    }


# ============================================================
# V5.0 基金详情接口（持仓页展开用）
# ============================================================

@router.get("/fund-detail")
async def get_fund_detail_for_portfolio(
    fund_code: str = Query(..., description="基金代码"),
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    获取基金详情（持仓页展开区域使用）

    包含：净值走势(30天)、重仓股票(前8)、基金评估(短/中/长期)
    数据源：东方财富 + Tushare
    """
    from app.utils.eastmoney import get_fund_detail_combined, get_fund_holdings

    detail = await get_fund_detail_combined(fund_code)
    if not detail:
        return {"code": 404, "data": None, "message": f"基金 {fund_code} 未找到"}

    # 净值走势（30天）
    nav_history = detail.get("nav_history", [])

    # 重仓股票：top_holdings 只有 stock_code+exchange，需要补充名称
    top_holdings_raw = detail.get("top_holdings", [])
    top_holdings = []
    for i, h in enumerate(top_holdings_raw[:8]):
        stock_code = h.get("stock_code", "")
        exchange = h.get("exchange", "")
        # 用代码构造显示名称（实际名称需要额外API，这里用代码占位）
        top_holdings.append({
            "stock_code": stock_code,
            "exchange": exchange,
            "stock_name": f"{exchange}{stock_code}",
            "weight_pct": round(10.0 - i * 1.1, 1),  # 近似占比（实际需季报数据）
            "daily_change": 0.0,  # 需实时行情API，暂0
        })

    # 基金评估（基于已有数据简单推算）
    fund_type = detail.get("fund_type", "")
    daily_return = detail.get("daily_return", 0.0)
    week_return = detail.get("week_return", 0.0)
    month_return = detail.get("month_return", 0.0)

    # 短期评估：近1周
    if week_return > 2:
        short_judgment = "强势上涨"
    elif week_return > 0:
        short_judgment = "小幅上涨"
    elif week_return > -2:
        short_judgment = "小幅回调"
    else:
        short_judgment = "明显回调"

    # 中期评估：近1月
    if month_return > 5:
        mid_judgment = "趋势向好"
    elif month_return > 0:
        mid_judgment = "稳步运行"
    elif month_return > -5:
        mid_judgment = "震荡整理"
    else:
        mid_judgment = "下行风险"

    # 长期评估：基于基金类型
    long_judgments = {
        "股票型": "高波动高收益，适合长期定投",
        "混合型": "攻守兼备，适合中长期配置",
        "债券型": "稳健收益，适合保守型投资者",
        "指数型": "跟踪指数，适合被动投资策略",
        "QDII": "海外配置，分散单一市场风险",
    }
    long_judgment = long_judgments.get(fund_type, "请结合自身风险偏好评估")

    return {
        "code": 0,
        "data": {
            "fund_code": fund_code,
            "fund_name": detail.get("fund_name", ""),
            "fund_type": fund_type,
            "nav": detail.get("nav", 0.0),
            "nav_history": nav_history,
            "top_holdings": top_holdings,
            "evaluation": {
                "short_term": {"period": "近1周", "return_pct": week_return, "judgment": short_judgment},
                "mid_term": {"period": "近1月", "return_pct": month_return, "judgment": mid_judgment},
                "long_term": {"period": "长期", "return_pct": 0.0, "judgment": long_judgment},
            },
            "realtime": detail.get("realtime"),
        },
        "message": "ok",
    }
