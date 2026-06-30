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
from app.core.redis_client import cache_get, cache_set

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
    cache_key = f"fsa:portfolio:{user_id}"
    cached = await cache_get(cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok"}

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

    portfolio_data = {
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
    }
    await cache_set(cache_key, portfolio_data, ttl=60)
    return {"code": 0, "data": portfolio_data, "message": "ok"}


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
    from app.engine.v5 import _run_v5_pipeline
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
    """获取仓位建议历史（从 advice_log 表读取真实数据）"""
    from app.models.advice_log import AdviceLog

    page_size = 20
    offset = (page - 1) * page_size

    # 构建查询
    stmt = select(AdviceLog).where(AdviceLog.user_id == user_id)
    count_stmt = select(func.count(AdviceLog.id)).where(AdviceLog.user_id == user_id)

    if fund_code:
        stmt = stmt.where(AdviceLog.index_code == fund_code)
        count_stmt = count_stmt.where(AdviceLog.index_code == fund_code)

    # 获取总数
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # 获取分页数据
    stmt = stmt.order_by(AdviceLog.trade_date.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "date": row.trade_date.strftime("%Y-%m-%d %H:%M") if row.trade_date else "",
            "signal_level": row.signal_level or row.sentiment_label,
            "confidence_stars": row.confidence_stars,
            "advice_type": row.advice_type,
            "advice_content": row.advice_content,
            "suggested_position": row.suggested_position,
            "is_executed": bool(row.is_executed) or row.is_executed_at is not None,
            "is_verified": bool(row.is_verified),
            "actual_result": row.actual_result,
            "accuracy_score": row.accuracy_score,
        })

    # 计算胜率
    verified = [r for r in rows if r.is_verified]
    correct = [r for r in verified if r.accuracy_score is not None and r.accuracy_score > 0.5]
    win_rate = round(len(correct) / len(verified) * 100, 1) if verified else 0

    return {
        "code": 0,
        "data": {
            "items": items,
            "stats": {
                "total_advice": total,
                "executed": sum(1 for r in rows if r.is_executed or r.is_executed_at),
                "pending": sum(1 for r in rows if not r.is_executed and not r.is_executed_at),
                "win_rate": win_rate,
                "verified_count": len(verified),
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
    """获取交易记录（从 position_execution 表读取真实数据）"""
    from app.models.position_execution import PositionExecution

    page_size = 20
    offset = (page - 1) * page_size

    # 构建查询
    stmt = select(PositionExecution).where(PositionExecution.user_id == user_id)
    count_stmt = select(func.count(PositionExecution.id)).where(PositionExecution.user_id == user_id)

    if fund_code:
        stmt = stmt.where(PositionExecution.fund_code == fund_code)
        count_stmt = count_stmt.where(PositionExecution.fund_code == fund_code)

    # 获取总数
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # 获取分页数据
    stmt = stmt.order_by(PositionExecution.execute_date.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    items = []
    for row in rows:
        # 判断交易类型
        if row.to_position_pct > row.from_position_pct:
            trade_type = "买入"
        elif row.to_position_pct < row.from_position_pct:
            trade_type = "卖出"
        else:
            trade_type = "调仓"

        items.append({
            "id": row.id,
            "date": row.execute_date.strftime("%Y-%m-%d") if row.execute_date else "",
            "fund_code": row.fund_code,
            "type": trade_type,
            "amount": row.amount or 0,
            "from_pct": row.from_position_pct,
            "to_pct": row.to_position_pct,
            "signal_level": row.signal_level,
            "confidence_stars": row.confidence_stars,
            "reason": row.reason or "",
            "nav": 0,  # 净值需要额外查询，暂留0
            "fee": 0,  # 费用暂无数据
        })

    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
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

    # 重仓股票：补充真实名称和实时行情
    top_holdings_raw = detail.get("top_holdings", [])
    top_holdings = []

    # 常见重仓股静态映射（兜底，API查不到时使用）
    STATIC_STOCK_NAMES = {
        "600519": "贵州茅台", "000333": "美的集团", "000858": "五粮液",
        "600809": "山西汾酒", "002594": "比亚迪", "600660": "福耀玻璃",
        "000568": "泸州老窖", "000596": "古井贡酒", "601318": "中国平安",
        "000651": "格力电器", "600036": "招商银行", "601888": "中国中免",
        "600276": "恒瑞医药", "000725": "京东方A", "601012": "隆基绿能",
        "600900": "长江电力", "601398": "工商银行", "600030": "中信证券",
        "002475": "立讯精密", "300750": "宁德时代", "601899": "紫金矿业",
        "600585": "海螺水泥", "000002": "万科A", "601166": "兴业银行",
        "600887": "伊利股份", "000063": "中兴通讯", "002230": "科大讯飞",
        "600406": "国电南瑞", "601628": "中国人寿", "600000": "浦发银行",
    }

    # 尝试从东方财富获取真实股票名称和行情
    stock_info_map = {}
    if top_holdings_raw:
        try:
            from app.utils.eastmoney import get_stock_info_batch
            stock_info_map = await get_stock_info_batch(top_holdings_raw[:8])
        except Exception:
            pass

    for i, h in enumerate(top_holdings_raw[:8]):
        stock_code = h.get("stock_code", "")
        exchange = h.get("exchange", "")
        info = stock_info_map.get(stock_code, {})

        stock_name = (
            info.get("name")
            or STATIC_STOCK_NAMES.get(stock_code)
            or f"{exchange}{stock_code}"
        )
        daily_change = info.get("change_pct") or 0.0

        top_holdings.append({
            "stock_code": stock_code,
            "exchange": exchange,
            "stock_name": stock_name,
            "weight_pct": round(10.0 - i * 1.1, 1),  # 近似占比（实际需季报数据）
            "daily_change": round(daily_change, 2),
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

    # 调用趋势卫士获取完整趋势数据
    trend_guard_data = {}
    try:
        from app.engine.position_v5 import calculate_trend_guard
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, we need to await
            # But this function is not async, so we use run_until_complete
            import concurrent.futures
            pass
    except Exception:
        pass

    try:
        from app.engine.trend_guard import calculate_position_v5
        tg_result = calculate_position_v5(
            fund_code=fund_code,
            cost_basis=0.0,
            current_position=0.5,
        )
        trend_guard_data = {
            "trend_signal": tg_result.get("trend_signal", ""),
            "macd_signal": tg_result.get("macd_signal", ""),
            "oscillation_silence": tg_result.get("oscillation_silence", False),
            "gate_triggered": tg_result.get("gate_triggered"),
            "operation_suggestion": tg_result.get("operation_suggestion", ""),
            "trend_narrative": tg_result.get("trend_narrative", ""),
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"趋势卫士调用失败(fund-detail): {e}")
        trend_guard_data = {}

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
            "trend_guard": trend_guard_data,
        },
        "message": "ok",
    }
