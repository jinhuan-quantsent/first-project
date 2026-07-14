"""
持仓管理接口
V4.0：注入 get_current_user，Mock → ORM CRUD
V5.0：新增仓位建议接口（使用 V5 引擎）
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models.user_portfolio import UserPortfolio
from app.models.user_cash import UserCash
from app.models.fund_nav import FundNav
from app.models.position_execution import PositionExecution
from app.models.advice_log import AdviceLog
from app.core.redis_client import cache_get, cache_set, cache_delete

router = APIRouter(prefix="/api/v5/portfolio")


# ============================================================
# Helper: compute position percentage from market values
# ============================================================


# ── daily_return 动态计算辅助函数 ─────────────────────────────────────

async def _calc_daily_return_from_nav(session, fund_code: str, market_value: float) -> float:
    """
    根据 fund_nav 表最近两条净值计算当日收益金额。
    返回：当日收益（正=赚，负=亏），数据不足返回 0.0
    """
    from sqlalchemy import text
    result = await session.execute(
        text(
            "SELECT nav FROM fund_nav "
            "WHERE fund_code = :code "
            "ORDER BY nav_date DESC "
            "LIMIT 2"
        ),
        {"code": fund_code},
    )
    rows = result.all()
    if len(rows) < 2:
        return 0.0
    today_nav = float(rows[0][0])
    yesterday_nav = float(rows[1][0])
    if yesterday_nav <= 0:
        return 0.0
    daily_pct = (today_nav - yesterday_nav) / yesterday_nav
    return round(market_value * daily_pct, 2)


async def _fetch_realtime_estimate(fund_code: str):
    """获取盘中实时估值（东方财富 API），返回 dict 或 None"""
    import urllib.request, json, re
    try:
        url = "https://fundgz.1234567.com.cn/js/" + fund_code + ".js"
        req = urllib.request.Request(url, headers={"Referer": "https://fund.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
        m = re.search(r"jsonpgz\((.*)\)", raw)
        if not m:
            return None
        d = json.loads(m.group(1))
        return {
            "gsz": float(d.get("gsz", 0)),
            "gszzl": float(d.get("gszzl", 0)),
        }
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────
async def _compute_position_pct(session: AsyncSession, user_id: str, item_market_value: float) -> float:
    """计算基金仓位占比 = item_market_value / total_assets * 100
    
    分母 = Sigma(各基金持仓市值) + 现金余额 = 总资产
    V5.1语义修正: 矩阵百分比表示"占总资产的配置比例", 而非"占持仓市值比例"
    可通过 .env V5_POSITION_DENOMINATOR 切换分母类型
    """
    from app.core.config import settings
    
    # 持仓总市值
    total_stmt = select(func.sum(UserPortfolio.market_value)).where(UserPortfolio.user_id == user_id)
    total_result = await session.execute(total_stmt)
    total_market_value = total_result.scalar() or 0.0
    
    # 现金余额
    cash_stmt = select(UserCash).where(UserCash.user_id == user_id)
    cash_result = await session.execute(cash_stmt)
    cash_row = cash_result.scalar_one_or_none()
    cash_amount = float(cash_row.cash_amount) if cash_row else 0.0
    
    # 根据配置选择分母
    if settings.V5_POSITION_DENOMINATOR == 'total_assets':
        denominator = total_market_value + cash_amount
    else:
        denominator = total_market_value
    
    if denominator > 0:
        return round(item_market_value / denominator * 100, 2)
    return 0.0




async def _fetch_latest_nav_from_api(fund_code: str) -> Optional[float]:
    """当 fund_nav 表无数据时，从 Tushare API 获取最新净值作为兜底"""
    try:
        import tushare as ts
        from app.core.config import settings
        from app.utils.eastmoney import code_to_tushare
        from datetime import date, timedelta

        if not settings.TUSHARE_TOKEN:
            return None

        pro = ts.pro_api(settings.TUSHARE_TOKEN)
        ts_code = code_to_tushare(fund_code)
        base_code = ts_code.split('.')[0]
        primary_suffix = ts_code.split('.')[-1] if '.' in ts_code else 'OF'
        suffixes = [primary_suffix]
        if primary_suffix == 'OF':
            suffixes.extend(['SH', 'SZ'])
        elif primary_suffix in ('SH', 'SZ'):
            suffixes.extend(['OF'])

        end_date = date.today().strftime('%Y%m%d')
        start_date = (date.today() - timedelta(days=30)).strftime('%Y%m%d')

        for suf in suffixes:
            try_code = f'{base_code}.{suf}'
            df = pro.fund_nav(ts_code=try_code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                df = df.sort_values('nav_date', ascending=False)
                unit_nav = float(df.iloc[0]['unit_nav'])
                if unit_nav > 0:
                    return round(unit_nav, 4)
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'Failed to fetch latest NAV from Tushare for {fund_code}: {e}')
        return None



async def _fetch_historical_nav_from_api(fund_code: str, target_date) -> Optional[float]:
    """当 fund_nav 表无数据时，从 Tushare API 获取指定日期的历史净值"""
    try:
        import tushare as ts
        from app.core.config import settings
        from app.utils.eastmoney import code_to_tushare
        from datetime import date, timedelta

        if not settings.TUSHARE_TOKEN:
            return None

        pro = ts.pro_api(settings.TUSHARE_TOKEN)
        ts_code = code_to_tushare(fund_code)
        base_code = ts_code.split('.')[0]
        primary_suffix = ts_code.split('.')[-1] if '.' in ts_code else 'OF'
        suffixes = [primary_suffix]
        if primary_suffix == 'OF':
            suffixes.extend(['SH', 'SZ'])
        elif primary_suffix in ('SH', 'SZ'):
            suffixes.extend(['OF'])

        if isinstance(target_date, date):
            target_str = target_date.strftime('%Y%m%d')
            start = target_date - timedelta(days=10)
        else:
            target_str = str(target_date).replace('-', '')
            parsed = date.fromisoformat(target_str[:4] + '-' + target_str[4:6] + '-' + target_str[6:8])
            start = parsed - timedelta(days=10)
        start_str = start.strftime('%Y%m%d')

        for suf in suffixes:
            try_code = f'{base_code}.{suf}'
            df = pro.fund_nav(ts_code=try_code, start_date=start_str, end_date=target_str)
            if df is not None and not df.empty:
                df = df.sort_values('nav_date', ascending=False)
                unit_nav = float(df.iloc[0]['unit_nav'])
                if unit_nav > 0:
                    return round(unit_nav, 4)
        return None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'Failed to fetch historical NAV from Tushare for {fund_code} on {target_date}: {e}')
        return None

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
    market_value: Optional[float] = None  # Optional: explicit market value (overrides holding_shares * current_nav)
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


class CashUpdate(BaseModel):
    """现金更新"""
    cash_amount: float


class PositionAdjust(BaseModel):
    """手动加仓/减仓请求"""
    amount: float
    date: Optional[str] = None  # ISO 日期，默认今天


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

    item_list = []
    for item in items:
        dr = await _calc_daily_return_from_nav(session, item.fund_code, item.market_value)
        item_list.append({
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
            "daily_return": dr,
            "buy_date": item.buy_date.isoformat() if item.buy_date else "",
            "portfolio_tag": item.portfolio_tag,
            "weight_pct": item.weight_pct,
        })

    total_value = sum(it["market_value"] for it in item_list)
    # 动态计算每只基金的 weight_pct（从市值计算，而非 DB 中可能为0的 weight_pct 字段）
    for it in item_list:
        it["weight_pct"] = round(it["market_value"] / total_value, 4) if total_value > 0 else 0.0
    total_return = sum(it["total_return"] for it in item_list)
    total_cost = sum(it["cost_nav"] * it["holding_shares"] for it in item_list)
    total_return_rate = round((total_value / total_cost - 1) * 100, 2) if total_cost > 0 else 0.0

    core_items = [it for it in item_list if it["portfolio_tag"] == "core"]
    satellite_items = [it for it in item_list if it["portfolio_tag"] == "satellite"]
    core_value = sum(it["market_value"] for it in core_items)
    satellite_value = sum(it["market_value"] for it in satellite_items)

    # 获取用户现金余额
    cash_stmt = select(UserCash).where(UserCash.user_id == user_id)
    cash_result = await session.execute(cash_stmt)
    cash_row = cash_result.scalar_one_or_none()
    cash_amount = float(cash_row.cash_amount) if cash_row else 0.0

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
            "cash_amount": round(cash_amount, 2),
            "total_assets": round(total_value + cash_amount, 2),
        },
        "updated_at": datetime.now().isoformat(),
    }
    await cache_set(cache_key, portfolio_data, ttl=60)
    return {"code": 0, "data": portfolio_data, "message": "ok"}



# ============================================================
# 建仓时后台回填基金净值历史
# ============================================================

async def _backfill_fund_nav_background(fund_code: str) -> None:
    """
    建仓时后台回填基金净值历史（最近365天）。
    作为 asyncio.create_task() 的后台任务调用，不阻塞建仓接口返回。
    """
    import logging
    logger = logging.getLogger(__name__)

    from app.core.config import settings
    if not settings.TUSHARE_TOKEN:
        logger.warning("[NAV回填] TUSHARE_TOKEN 未配置，跳过")
        return

    import tushare as ts
    try:
        pro = ts.pro_api(settings.TUSHARE_TOKEN)
    except Exception as e:
        logger.error("[NAV回填] Tushare 初始化失败: %s", e)
        return

    from datetime import date as date_type, timedelta
    today = date_type.today()
    start_date = (today - timedelta(days=365)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    from app.utils.code_format import to_tushare
    ts_code = to_tushare(fund_code)
    base_code = ts_code.split(".")[0]
    primary_suffix = ts_code.split(".")[-1]
    suffixes = [primary_suffix]
    if primary_suffix == "OF":
        suffixes.extend(["SH", "SZ"])

    df = None
    for suf in suffixes:
        try_code = f"{base_code}.{suf}"
        try:
            df = pro.fund_nav(ts_code=try_code, start_date=start_date, end_date=end_date)
            if df is not None and not df.empty:
                logger.info("[NAV回填] %s 从 %s 获取到 %d 条数据", fund_code, try_code, len(df))
                break
        except Exception:
            continue

    if df is None or df.empty:
        logger.warning("[NAV回填] %s 无法获取净值历史数据", fund_code)
        return

    # 使用新的 async session 写入 fund_nav 表
    from sqlalchemy import select as select_
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.models.fund_nav import FundNav

    engine = get_async_engine()
    async with AsyncSessionType(engine) as sess:
        inserted = 0
        for _, row in df.iterrows():
            nav_date = str(row["nav_date"])
            nav_val = float(row["unit_nav"])
            existing = await sess.execute(
                select_(FundNav).where(
                    FundNav.fund_code == fund_code,
                    FundNav.nav_date == nav_date
                )
            )
            if existing.scalar_one_or_none() is None:
                sess.add(FundNav(fund_code=fund_code, nav_date=nav_date, nav=nav_val))
                inserted += 1
        await sess.commit()
        logger.info("[NAV回填] ✅ %s 回填完成：插入 %d 条（共 %d 条）", fund_code, inserted, len(df))

@router.post("", status_code=201)
async def add_portfolio_item(
    item: PortfolioItem,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """添加持仓（自动联动扣减现金，根据买入日期计算成本净值）"""
    # 根据买入日期从 fund_nav 表查询成本净值（取买入日或最近的前一个交易日）
    cost_nav = item.cost_nav
    buy_date_parsed = None
    if item.buy_date:
        try:
            from datetime import date as date_type
            buy_date_parsed = date_type.fromisoformat(item.buy_date)
        except (ValueError, TypeError):
            buy_date_parsed = None

    if buy_date_parsed and not (cost_nav and cost_nav > 0):
        # 查询买入日期当天或最近前一个交易日的净值
        nav_stmt = (
            select(FundNav)
            .where(FundNav.fund_code == item.fund_code, FundNav.nav_date <= buy_date_parsed)
            .order_by(FundNav.nav_date.desc())
            .limit(1)
        )
        nav_result = await session.execute(nav_stmt)
        nav_row = nav_result.scalar_one_or_none()
        if nav_row and nav_row.nav and nav_row.nav > 0:
            cost_nav = round(nav_row.nav, 4)

    # 如果仍无 cost_nav，尝试从 Tushare API 获取指定日期的历史净值
    if not cost_nav or cost_nav <= 0:
        api_nav = await _fetch_historical_nav_from_api(item.fund_code, buy_date_parsed)
        if api_nav and api_nav > 0:
            cost_nav = api_nav
        else:
            cost_nav = item.current_nav if item.current_nav > 0 else 1.0

    # Calculate market_value: use explicit value if provided, else holding_shares * current_nav
    if item.market_value is not None and item.market_value > 0:
        market_value = round(item.market_value, 2)
    else:
        market_value = round(item.holding_shares * item.current_nav, 2)

    # 根据投资金额和成本净值计算持有份额
    holding_shares = item.holding_shares
    if market_value > 0 and cost_nav > 0 and (not holding_shares or holding_shares <= 0):
        holding_shares = round(market_value / cost_nav, 4)

    total_return = round((item.current_nav - cost_nav) * holding_shares, 2)
    return_rate = round((item.current_nav / cost_nav - 1) * 100, 2) if cost_nav > 0 else 0

    # Cash linkage: deduct market_value from user_cash
    if market_value > 0:
        cash_stmt = select(UserCash).where(UserCash.user_id == user_id)
        cash_result = await session.execute(cash_stmt)
        cash_row = cash_result.scalar_one_or_none()

        if cash_row:
            current_cash = float(cash_row.cash_amount)
            if current_cash < market_value:
                return {
                    "code": 400,
                    "data": None,
                    "message": f"现金不足：需要 {market_value:.2f}，可用 {current_cash:.2f}",
                }
            cash_row.cash_amount = round(current_cash - market_value, 2)
        else:
            # No cash record exists - create one with 0 and reject
            return {
                "code": 400,
                "data": None,
                "message": f"现金不足：需要 {market_value:.2f}，可用 0.00",
            }

    new_item = UserPortfolio(
        user_id=user_id,
        fund_code=item.fund_code,
        fund_name=item.fund_name or f"基金{item.fund_code}",
        fund_type=item.fund_type,
        holding_shares=holding_shares,
        cost_nav=cost_nav,
        current_nav=item.current_nav,
        market_value=market_value,
        total_return=total_return,
        return_rate=return_rate,
        daily_return=0.0,  # 由 GET 接口动态计算
        buy_date=item.buy_date,
        portfolio_tag=item.portfolio_tag,
        weight_pct=item.weight_pct,
    )
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)

    # 创建交易记录 + 绩效记录（独立提交，互不影响）
    # 先保存所需字段，避免 rollback 后 ORM 对象过期导致 async lazy-load 失败
    from datetime import date as date_type
    exec_date = date_type.fromisoformat(item.buy_date) if item.buy_date else date_type.today()
    _fund_name = new_item.fund_name

    try:
        trade_record = PositionExecution(
            user_id=user_id,
            fund_code=item.fund_code,
            execute_date=exec_date,
            from_position_pct=0.0,
            to_position_pct=item.weight_pct or 0.0,
            amount=market_value,
            operation_type="buy",
            nav=cost_nav,
            signal_level="B",
            confidence_stars=3,
            reason=f"手动添加持仓：买入 {_fund_name} {market_value} 元",
        )
        session.add(trade_record)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create trade record on add: {e}")

    # 计算仓位占比（建仓后该基金在总持仓中的占比）
    _suggested_pos = await _compute_position_pct(session, user_id, market_value)

    try:
        advice_log = AdviceLog(
            user_id=user_id,
            fund_code=item.fund_code,
            advice_date=exec_date,
            index_code=item.fund_code,
            trade_date=datetime.now(),
            sentiment_label="B",
            advice_type="buy",
            advice_content=f"建仓买入 {_fund_name}，金额 {market_value} 元，成本净值 {cost_nav}",
            suggested_position=_suggested_pos,
            actual_result=0.0,
            is_executed=1,
            executed_at=datetime.now(),
            is_executed_at=datetime.now(),
            execution_note=f"建仓：0% -> {_suggested_pos:.1f}%",
            signal_level="B",
            confidence_stars=3,
        )
        session.add(advice_log)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create advice log on add: {e}")

    # Invalidate portfolio cache (summary includes cash_amount and total_assets)
    await cache_delete(f"fsa:portfolio:{user_id}")
    await cache_delete(f"v5:fund_detail:{new_item.fund_code}:{user_id}")

    # 修复P0: 使用 FastAPI BackgroundTasks 替代 asyncio.create_task
    # 确保回填在响应后执行，不会被 event loop 取消
    background_tasks.add_task(_backfill_fund_nav_background, new_item.fund_code)
    import logging as _bg_log
    _bg_log.getLogger(__name__).info("[建仓] BackgroundTasks 触发 %s 净值回填", new_item.fund_code)

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
    existing.daily_return = 0.0  # 由 GET 接口动态计算
    existing.portfolio_tag = item.portfolio_tag
    existing.weight_pct = item.weight_pct

    await session.commit()

    # Invalidate portfolio cache
    await cache_delete(f"fsa:portfolio:{user_id}")
    await cache_delete(f"v5:fund_detail:{existing.fund_code}:{user_id}")




    return {"code": 0, "data": {"id": existing.id}, "message": "更新成功"}


@router.delete("/{item_id}")
async def delete_portfolio_item(
    item_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除持仓（自动退还市值到现金）"""
    # Fetch the position first (need market_value for cash refund)
    stmt = select(UserPortfolio).where(
        UserPortfolio.id == item_id, UserPortfolio.user_id == user_id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}

    refund_amount = float(existing.market_value or 0)

    # 先保存所需字段，避免 commit/rollback 后 ORM 对象过期导致 async lazy-load 失败
    _fund_code = existing.fund_code
    _fund_name = existing.fund_name
    _weight_pct = float(existing.weight_pct or 0.0)
    _market_value = float(existing.market_value or 0.0)
    _return_rate = float(existing.return_rate or 0.0)
    _current_nav = float(existing.current_nav or 0.0)
    # 计算删除前的仓位占比
    _suggested_pos = await _compute_position_pct(session, user_id, _market_value)

    # Delete the position
    del_stmt = delete(UserPortfolio).where(
        UserPortfolio.id == item_id, UserPortfolio.user_id == user_id
    )
    await session.execute(del_stmt)

    # Refund market_value to cash
    if refund_amount > 0:
        cash_stmt = select(UserCash).where(UserCash.user_id == user_id)
        cash_result = await session.execute(cash_stmt)
        cash_row = cash_result.scalar_one_or_none()
        if cash_row:
            cash_row.cash_amount = round(float(cash_row.cash_amount) + refund_amount, 2)

    await session.commit()

    # 创建交易记录 + 绩效记录（独立提交，互不影响）
    from datetime import date as date_type

    try:
        sell_record = PositionExecution(
            user_id=user_id,
            fund_code=_fund_code,
            execute_date=date_type.today(),
            from_position_pct=_weight_pct,
            to_position_pct=0.0,
            amount=refund_amount,
            operation_type="sell",
            nav=_current_nav,
            signal_level="B",
            confidence_stars=3,
            reason=f"手动删除持仓：卖出 {_fund_name} {refund_amount} 元",
        )
        session.add(sell_record)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create trade record on delete: {e}")

    try:
        advice_log = AdviceLog(
            user_id=user_id,
            fund_code=_fund_code,
            advice_date=date_type.today(),
            index_code=_fund_code,
            trade_date=datetime.now(),
            sentiment_label="B",
            advice_type="reduce",
            advice_content=f"清仓卖出 {_fund_name}，金额 {refund_amount} 元",
            suggested_position=_suggested_pos,
            actual_result=_return_rate,
            is_executed=1,
            executed_at=datetime.now(),
            is_executed_at=datetime.now(),
            execution_note=f"清仓：{_suggested_pos:.1f}% -> 0%",
            signal_level="B",
            confidence_stars=3,
        )
        session.add(advice_log)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create advice log on delete: {e}")

    # Invalidate portfolio cache
    await cache_delete(f"fsa:portfolio:{user_id}")
    await cache_delete(f"v5:fund_detail:{_fund_code}:{user_id}")

    return {"code": 0, "data": None, "message": "删除成功"}


# ============================================================
# 手动加仓/减仓接口
# ============================================================

@router.post("/{item_id}/increase")
async def increase_position(
    item_id: int,
    payload: PositionAdjust,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """手动加仓：增加份额，扣减现金，创建交易+绩效记录"""
    if payload.amount <= 0:
        return {"code": 400, "data": None, "message": "加仓金额必须大于0"}

    # 解析操作日期
    from datetime import date as date_type
    try:
        op_date = date_type.fromisoformat(payload.date) if payload.date else date_type.today()
    except (ValueError, TypeError):
        op_date = date_type.today()

    # 查询持仓
    stmt = select(UserPortfolio).where(
        UserPortfolio.id == item_id, UserPortfolio.user_id == user_id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if not existing:
        return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}

    # 检查现金是否充足
    cash_stmt = select(UserCash).where(UserCash.user_id == user_id)
    cash_result = await session.execute(cash_stmt)
    cash_row = cash_result.scalar_one_or_none()
    current_cash = float(cash_row.cash_amount) if cash_row else 0.0
    if current_cash < payload.amount:
        return {
            "code": 400,
            "data": None,
            "message": f"现金不足：需要 {payload.amount:.2f}，可用 {current_cash:.2f}",
        }

    # 查询操作日期对应的净值（用于计算新增份额）
    nav_to_use = existing.current_nav if existing.current_nav > 0 else 1.0
    if op_date < date_type.today():
        nav_stmt = (
            select(FundNav)
            .where(FundNav.fund_code == existing.fund_code, FundNav.nav_date <= op_date)
            .order_by(FundNav.nav_date.desc())
            .limit(1)
        )
        nav_result = await session.execute(nav_stmt)
        nav_row = nav_result.scalar_one_or_none()
        if nav_row and nav_row.nav and nav_row.nav > 0:
            nav_to_use = round(nav_row.nav, 4)
        else:
            # fund_nav 表无数据，从 Tushare API 获取指定日期的历史净值
            api_nav = await _fetch_historical_nav_from_api(existing.fund_code, op_date)
            if api_nav and api_nav > 0:
                nav_to_use = api_nav

    # 加权平均成本法计算
    new_shares = round(payload.amount / nav_to_use, 4)
    old_shares = float(existing.holding_shares or 0)
    old_cost_nav = float(existing.cost_nav or 0)

    # 旧总成本 = 旧份额 × 旧成本净值（如果旧份额为0，旧总成本为0）
    old_total_cost = old_shares * old_cost_nav
    # 本次加仓成本 = 加仓金额
    new_cost = payload.amount
    # 新总成本 = 旧总成本 + 本次成本
    new_total_cost = old_total_cost + new_cost
    # 新总份额
    new_total_shares = old_shares + new_shares
    # 加权平均成本净值
    new_weighted_avg_cost = round(new_total_cost / new_total_shares, 4) if new_total_shares > 0 else 0

    # 查询最新净值（不受操作日期影响，始终用最新净值作为 current_nav）
    latest_nav = nav_to_use  # 默认用操作日净值
    latest_nav_stmt = (
        select(FundNav)
        .where(FundNav.fund_code == existing.fund_code)
        .order_by(FundNav.nav_date.desc())
        .limit(1)
    )
    latest_nav_result = await session.execute(latest_nav_stmt)
    latest_nav_row = latest_nav_result.scalar_one_or_none()
    if latest_nav_row and latest_nav_row.nav and latest_nav_row.nav > 0:
        latest_nav = round(latest_nav_row.nav, 4)
    else:
        # fund_nav 表无数据，尝试从 Tushare API 获取最新净值
        api_nav = await _fetch_latest_nav_from_api(existing.fund_code)
        if api_nav and api_nav > 0:
            latest_nav = api_nav
        elif existing.current_nav and existing.current_nav > 0:
            latest_nav = existing.current_nav

    # 更新持仓（加权平均成本法）
    existing.holding_shares = round(new_total_shares, 4)
    existing.cost_nav = new_weighted_avg_cost  # 关键：更新为加权平均成本
    existing.current_nav = latest_nav  # 用最新净值，不用操作日净值
    existing.market_value = round(new_total_shares * latest_nav, 2)  # 重算市值
    # 收益 = 当前市值 - 总投入成本
    existing.total_return = round(existing.market_value - new_total_cost, 2)
    existing.return_rate = round((existing.market_value / new_total_cost - 1) * 100, 2) if new_total_cost > 0 else 0
    existing.daily_return = 0.0  # 由 GET 接口动态计算

    # 扣减现金
    if cash_row:
        cash_row.cash_amount = round(current_cash - payload.amount, 2)

    await session.commit()
    await session.refresh(existing)

    # 创建交易记录 + 绩效记录（独立提交，互不影响）
    # 先保存所需字段，避免 rollback 后 ORM 对象过期导致 async lazy-load 失败
    old_pct = float(existing.weight_pct or 0.0)
    _fund_code = existing.fund_code
    _fund_name = existing.fund_name
    _new_market_value = float(existing.market_value or 0.0)
    _return_rate = float(existing.return_rate or 0.0)
    # 计算加仓后的仓位占比
    _suggested_pos = await _compute_position_pct(session, user_id, _new_market_value)
    _result = {
        "id": existing.id,
        "fund_code": _fund_code,
        "holding_shares": existing.holding_shares,
        "market_value": existing.market_value,
        "current_nav": existing.current_nav,
        "total_return": existing.total_return,
        "return_rate": existing.return_rate,
    }

    try:
        trade_record = PositionExecution(
            user_id=user_id,
            fund_code=_fund_code,
            execute_date=op_date,
            from_position_pct=old_pct,
            to_position_pct=_suggested_pos / 100 if _suggested_pos > 0 else old_pct,
            amount=payload.amount,
            operation_type="buy",
            nav=nav_to_use,
            signal_level="B",
            confidence_stars=3,
            reason=f"手动加仓：买入 {_fund_name} {payload.amount} 元，净值 {nav_to_use}",
        )
        session.add(trade_record)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create trade record on increase: {e}")

    try:
        advice_log = AdviceLog(
            user_id=user_id,
            fund_code=_fund_code,
            advice_date=op_date,
            index_code=_fund_code,
            trade_date=datetime.now(),
            sentiment_label="B",
            advice_type="buy",
            advice_content=f"手动加仓 {_fund_name}，金额 {payload.amount} 元，净值 {nav_to_use}",
            suggested_position=_suggested_pos,
            actual_result=_return_rate,
            is_executed=1,
            executed_at=datetime.now(),
            is_executed_at=datetime.now(),
            execution_note=f"加仓：{old_pct*100:.1f}% -> {_suggested_pos:.1f}%（+{payload.amount}元）",
            signal_level="B",
            confidence_stars=3,
        )
        session.add(advice_log)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create advice log on increase: {e}")

    # 失效缓存
    await cache_delete(f"fsa:portfolio:{user_id}")
    await cache_delete(f"v5:fund_detail:{existing.fund_code}:{user_id}")

    return {
        "code": 0,
        "data": _result,
        "message": "加仓成功",
    }


@router.post("/{item_id}/decrease")
async def decrease_position(
    item_id: int,
    payload: PositionAdjust,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """手动减仓：减少份额，退还现金，创建交易+绩效记录"""
    if payload.amount <= 0:
        return {"code": 400, "data": None, "message": "减仓金额必须大于0"}

    # 解析操作日期
    from datetime import date as date_type
    try:
        op_date = date_type.fromisoformat(payload.date) if payload.date else date_type.today()
    except (ValueError, TypeError):
        op_date = date_type.today()

    # 查询持仓
    stmt = select(UserPortfolio).where(
        UserPortfolio.id == item_id, UserPortfolio.user_id == user_id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if not existing:
        return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}

    old_market_value = float(existing.market_value or 0)
    if payload.amount > old_market_value:
        return {
            "code": 400,
            "data": None,
            "message": f"减仓金额超过持仓市值：市值 {old_market_value:.2f}，减仓 {payload.amount:.2f}",
        }

    # 查询操作日期对应的净值
    nav_to_use = existing.current_nav if existing.current_nav > 0 else 1.0
    if op_date < date_type.today():
        nav_stmt = (
            select(FundNav)
            .where(FundNav.fund_code == existing.fund_code, FundNav.nav_date <= op_date)
            .order_by(FundNav.nav_date.desc())
            .limit(1)
        )
        nav_result = await session.execute(nav_stmt)
        nav_row = nav_result.scalar_one_or_none()
        if nav_row and nav_row.nav and nav_row.nav > 0:
            nav_to_use = round(nav_row.nav, 4)
        else:
            # fund_nav 表无数据，从 Tushare API 获取指定日期的历史净值
            api_nav = await _fetch_historical_nav_from_api(existing.fund_code, op_date)
            if api_nav and api_nav > 0:
                nav_to_use = api_nav

    # 减仓计算（加权平均成本法）
    reduce_shares = round(payload.amount / nav_to_use, 4)
    old_shares = float(existing.holding_shares or 0)
    old_cost_nav = float(existing.cost_nav or 0)
    # 保存减仓前的成本净值，用于计算实现收益率
    _pre_dec_cost_nav = old_cost_nav

    # 查询最新净值
    latest_nav = nav_to_use
    latest_nav_stmt = (
        select(FundNav)
        .where(FundNav.fund_code == existing.fund_code)
        .order_by(FundNav.nav_date.desc())
        .limit(1)
    )
    latest_nav_result = await session.execute(latest_nav_stmt)
    latest_nav_row = latest_nav_result.scalar_one_or_none()
    if latest_nav_row and latest_nav_row.nav and latest_nav_row.nav > 0:
        latest_nav = round(latest_nav_row.nav, 4)
    else:
        # fund_nav 表无数据，尝试从 Tushare API 获取最新净值
        api_nav = await _fetch_latest_nav_from_api(existing.fund_code)
        if api_nav and api_nav > 0:
            latest_nav = api_nav
        elif existing.current_nav and existing.current_nav > 0:
            latest_nav = existing.current_nav

    # 旧总成本
    old_total_cost = old_shares * old_cost_nav
    # 减仓比例
    decrease_ratio = payload.amount / old_market_value if old_market_value > 0 else 1.0
    # 新份额
    new_shares = max(0, old_shares - reduce_shares)
    # 新总成本 = 旧总成本 × (1 - 减仓比例)（按比例减少成本基础）
    new_total_cost = old_total_cost * (1 - decrease_ratio)
    # cost_nav 不变（加权平均成本不随卖出改变）

    # 更新持仓
    existing.holding_shares = round(new_shares, 4)
    existing.current_nav = latest_nav  # 用最新净值
    existing.market_value = round(new_shares * latest_nav, 2)  # 重算市值
    # 收益 = 剩余市值 - 剩余成本
    if new_shares > 0 and new_total_cost > 0:
        existing.total_return = round(existing.market_value - new_total_cost, 2)
        existing.return_rate = round((existing.market_value / new_total_cost - 1) * 100, 2)
    else:
        existing.total_return = 0.0
        existing.return_rate = 0.0
    existing.daily_return = 0.0  # 由 GET 接口动态计算

    # 退还现金
    cash_stmt = select(UserCash).where(UserCash.user_id == user_id)
    cash_result = await session.execute(cash_stmt)
    cash_row = cash_result.scalar_one_or_none()
    if cash_row:
        cash_row.cash_amount = round(float(cash_row.cash_amount) + payload.amount, 2)

    await session.commit()
    await session.refresh(existing)

    # 创建交易记录 + 绩效记录（独立提交，互不影响）
    # 先保存所需字段，避免 rollback 后 ORM 对象过期导致 async lazy-load 失败
    old_pct = float(existing.weight_pct or 0.0)
    _fund_code = existing.fund_code
    _fund_name = existing.fund_name
    _new_market_value = float(existing.market_value or 0.0)
    _return_rate = float(existing.return_rate or 0.0)
    # 计算减仓后的仓位占比
    _suggested_pos = await _compute_position_pct(session, user_id, _new_market_value)
    # 减仓实现的收益率 = (减仓时净值 - 成本净值) / 成本净值 * 100
    _realized_return = round((nav_to_use - _pre_dec_cost_nav) / _pre_dec_cost_nav * 100, 2) if _pre_dec_cost_nav > 0 else 0.0
    _result = {
        "id": existing.id,
        "fund_code": _fund_code,
        "holding_shares": existing.holding_shares,
        "market_value": existing.market_value,
        "current_nav": existing.current_nav,
        "total_return": existing.total_return,
        "return_rate": existing.return_rate,
    }

    try:
        trade_record = PositionExecution(
            user_id=user_id,
            fund_code=_fund_code,
            execute_date=op_date,
            from_position_pct=old_pct,
            to_position_pct=_suggested_pos / 100 if _suggested_pos > 0 else old_pct,
            amount=payload.amount,
            operation_type="sell",
            nav=nav_to_use,
            signal_level="B",
            confidence_stars=3,
            reason=f"手动减仓：卖出 {_fund_name} {payload.amount} 元，净值 {nav_to_use}",
        )
        session.add(trade_record)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create trade record on decrease: {e}")

    try:
        advice_log = AdviceLog(
            user_id=user_id,
            fund_code=_fund_code,
            advice_date=op_date,
            index_code=_fund_code,
            trade_date=datetime.now(),
            sentiment_label="B",
            advice_type="reduce",
            advice_content=f"手动减仓 {_fund_name}，金额 {payload.amount} 元，净值 {nav_to_use}",
            suggested_position=_suggested_pos,
            actual_result=_realized_return,
            is_executed=1,
            executed_at=datetime.now(),
            is_executed_at=datetime.now(),
            execution_note=f"减仓：{old_pct*100:.1f}% -> {_suggested_pos:.1f}%（-{payload.amount}元）",
            signal_level="B",
            confidence_stars=3,
        )
        session.add(advice_log)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).warning(f"Failed to create advice log on decrease: {e}")

    # 失效缓存
    await cache_delete(f"fsa:portfolio:{user_id}")
    await cache_delete(f"v5:fund_detail:{existing.fund_code}:{user_id}")

    return {
        "code": 0,
        "data": _result,
        "message": "减仓成功",
    }


@router.get("/overlap")
async def get_portfolio_overlap(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """持仓重叠分析（基于真实重仓股数据）"""
    from app.utils.eastmoney import get_fund_holdings
    import asyncio

    stmt = select(UserPortfolio).where(UserPortfolio.user_id == user_id)
    result = await session.execute(stmt)
    items = result.scalars().all()

    if len(items) < 2:
        return {
            "code": 0,
            "data": {
                "overall_overlap_score": 0.0,
                "overlap_level": "low",
                "details": [],
                "suggestion": "持仓基金不足2只，无法进行重叠分析",
            },
            "message": "ok",
        }

    # 并行获取每只基金的重仓股
    async def fetch_holdings(fund_code: str) -> set:
        try:
            holdings = await get_fund_holdings(fund_code)
            if holdings:
                return {h["stock_code"] for h in holdings if h.get("stock_code")}
        except Exception:
            pass
        return set()

    holdings_map = {}
    results = await asyncio.gather(
        *[fetch_holdings(it.fund_code) for it in items],
        return_exceptions=True,
    )
    for item, res in zip(items, results):
        if isinstance(res, Exception):
            holdings_map[item.fund_code] = set()
        else:
            holdings_map[item.fund_code] = res

    overlap_data: list[dict] = []
    fund_list = list(items)
    for i in range(len(fund_list)):
        for j in range(i + 1, len(fund_list)):
            fa, fb = fund_list[i], fund_list[j]
            stocks_a = holdings_map.get(fa.fund_code, set())
            stocks_b = holdings_map.get(fb.fund_code, set())

            if not stocks_a or not stocks_b:
                overlap_data.append({
                    "pair": [fa.fund_name, fb.fund_name],
                    "overlap_score": 0.0,
                    "overlap_sectors": [],
                    "suggestion": "重仓股数据不足，无法计算重叠度",
                })
                continue

            intersection = stocks_a & stocks_b
            union = stocks_a | stocks_b
            score = round(len(intersection) / len(union) * 100, 1) if union else 0.0

            overlap_stocks = sorted(list(intersection))[:10]
            suggestion = (
                f"重仓股重叠{len(intersection)}只，重叠度{score}%，建议关注持仓分散度"
                if score > 0
                else "重仓股无重叠，持仓分散度良好"
            )

            overlap_data.append({
                "pair": [fa.fund_name, fb.fund_name],
                "overlap_score": score,
                "overlap_sectors": overlap_stocks,
                "suggestion": suggestion,
            })

    scores = [d["overlap_score"] for d in overlap_data]
    overall = round(sum(scores) / len(scores), 1) if scores else 0.0
    if overall < 15:
        level = "low"
    elif overall < 40:
        level = "medium"
    else:
        level = "high"

    level_text = {"low": "低", "medium": "中等", "high": "较高"}.get(level, "中等")
    overall_suggestion = (
        "持仓分散度良好" if level == "low"
        else "建议关注持仓分散度，适当增加不同风格基金"
    )

    return {
        "code": 0,
        "data": {
            "overall_overlap_score": overall,
            "overlap_level": level,
            "details": overlap_data,
            "suggestion": f"整体持仓重叠度{level_text}，{overall_suggestion}",
        },
        "message": "ok",
    }


# ============================================================
# 现金管理接口
# ============================================================

@router.get("/cash")
async def get_cash(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取用户可用现金"""
    stmt = select(UserCash).where(UserCash.user_id == user_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        # 自动创建默认行（处理并发插入竞态）
        try:
            row = UserCash(user_id=user_id, cash_amount=0)
            session.add(row)
            await session.commit()
            await session.refresh(row)
        except Exception:
            await session.rollback()
            # 并发插入导致重复，重新查询
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

    return {
        "code": 0,
        "data": {
            "cash_amount": float(row.cash_amount) if row else 0,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else "",
        },
        "message": "ok",
    }


@router.post("/cash")
async def update_cash(
    payload: CashUpdate,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """更新用户可用现金"""
    if payload.cash_amount < 0:
        return {"code": 400, "data": None, "message": "现金金额不能为负"}

    stmt = select(UserCash).where(UserCash.user_id == user_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        row = UserCash(user_id=user_id, cash_amount=payload.cash_amount)
        session.add(row)
    else:
        row.cash_amount = round(payload.cash_amount, 2)

    await session.commit()
    await session.refresh(row)

    # 失效持仓缓存（因为 summary 包含 cash_amount 和 total_assets）
    await cache_delete(f"fsa:portfolio:{user_id}")
    # 失效所有基金的详情缓存（total_assets 变化影响所有基金的建议）
    _fd_stmt = select(UserPortfolio.fund_code).where(UserPortfolio.user_id == user_id)
    _fd_result = await session.execute(_fd_stmt)
    for (_fc,) in _fd_result:
        await cache_delete(f"v5:fund_detail:{_fc}:{user_id}")

    return {
        "code": 0,
        "data": {
            "cash_amount": float(row.cash_amount),
            "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        },
        "message": "现金更新成功",
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
    from app.services.sentiment_service import SentimentService
    from app.engine.position_v5 import PositionEngineV5

    # 获取市场信号（默认沪深300）
    result = await SentimentService(session).run_pipeline("SH000300", persist=False)
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
            "advice_date": row.advice_date.strftime("%Y-%m-%d") if row.advice_date else "",
            "signal_level": row.signal_level or row.sentiment_label,
            "confidence_stars": row.confidence_stars,
            "advice_type": row.advice_type,
            "advice_content": row.advice_content,
            "suggested_position": row.suggested_position,
            "is_executed": bool(row.is_executed) or row.is_executed_at is not None,
            "is_verified": bool(row.is_verified),
            "actual_result": row.actual_result,
            "accuracy_score": row.accuracy_score,
            "execution_note": row.execution_note or "",
        })

    # 计算胜率统计
    verified = [r for r in rows if r.is_verified]
    correct = [r for r in verified if r.accuracy_score is not None and r.accuracy_score > 0.5]
    win_rate = round(len(correct) / len(verified) * 100, 1) if verified else 0

    # 按建议类型分类统计
    buy_advice = [r for r in rows if r.advice_type == "buy"]
    reduce_advice = [r for r in rows if r.advice_type == "reduce"]
    hold_advice = [r for r in rows if r.advice_type == "hold"]
    buy_verified = [r for r in buy_advice if r.is_verified]
    reduce_verified = [r for r in reduce_advice if r.is_verified]
    buy_correct = [r for r in buy_verified if r.accuracy_score is not None and r.accuracy_score > 0.5]
    reduce_correct = [r for r in reduce_verified if r.accuracy_score is not None and r.accuracy_score > 0.5]

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
                "buy_count": len(buy_advice),
                "reduce_count": len(reduce_advice),
                "hold_count": len(hold_advice),
                "buy_verified": len(buy_verified),
                "buy_correct": len(buy_correct),
                "buy_win_rate": round(len(buy_correct) / len(buy_verified) * 100, 1) if buy_verified else 0,
                "reduce_verified": len(reduce_verified),
                "reduce_correct": len(reduce_correct),
                "reduce_win_rate": round(len(reduce_correct) / len(reduce_verified) * 100, 1) if reduce_verified else 0,
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
        # 判断交易类型：优先使用 operation_type 字段
        op_type = getattr(row, "operation_type", None)
        if op_type == "buy":
            trade_type = "买入"
        elif op_type == "sell":
            trade_type = "卖出"
        elif row.to_position_pct > row.from_position_pct:
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
            "nav": getattr(row, "nav", None) or 0,
            "fee": 0,
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
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取基金详情（持仓页展开区域使用）

    包含：净值走势(30天)、重仓股票(前8)、基金评估(短/中/长期)
    数据源：东方财富 + Tushare
    Redis 缓存 5min（盘中估值会变化，不宜太长）
    """
    # 查缓存（按 fund_code + user_id 组合，因 positionAdvice 是个性化的）
    _fund_detail_cache_key = f"v5:fund_detail:{fund_code}:{user_id}"
    cached = await cache_get(_fund_detail_cache_key)
    if cached:
        return {"code": 0, "data": cached, "message": "ok", "cached": True}

    start_fd = datetime.now()
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

    # trend_guard_data 将从 positionAdvice 结果里统一获取（Phase 0c: 合并双调用）
    # 不再直接调用 calculate_position_v5，避免两份数据矛盾
    trend_guard_data = {}

    # 获取仓位建议和市场现状（per-fund 差异化）
    market_status = None
    position_advice_data = None
    try:
        from app.services.position_service import PositionService
        # 查询用户该基金的持仓记录
        pf_stmt = select(UserPortfolio).where(
            UserPortfolio.user_id == user_id,
            UserPortfolio.fund_code == fund_code,
        ).limit(1)
        pf_result = await session.execute(pf_stmt)
        pf_item = pf_result.scalar_one_or_none()

        # 计算该基金的实际仓位占比（V5.1: 分母=总资产=市值+现金）
        # weight_pct 字段可能未正确维护（默认0），需从 market_value 计算
        total_stmt = select(func.sum(UserPortfolio.market_value)).where(
            UserPortfolio.user_id == user_id,
        )
        total_result = await session.execute(total_stmt)
        total_market_value = total_result.scalar() or 0.0
        
        # 查现金余额
        cash_stmt2 = select(UserCash).where(UserCash.user_id == user_id)
        cash_result2 = await session.execute(cash_stmt2)
        cash_row2 = cash_result2.scalar_one_or_none()
        cash_amount = float(cash_row2.cash_amount) if cash_row2 else 0.0
        
        # 根据配置选择分母
        from app.core.config import settings
        if settings.V5_POSITION_DENOMINATOR == 'total_assets':
            denominator = total_market_value + cash_amount
        else:
            denominator = total_market_value
        
        if pf_item and denominator > 0 and pf_item.market_value > 0:
            current_position_pct = pf_item.market_value / denominator
        elif pf_item and denominator > 0:
            current_position_pct = 0.01  # 有持仓记录但市值为0，极小默认值(empty级)
        else:
            current_position_pct = 0.01  # 无持仓记录，极小默认值(empty级)

        pos_service = PositionService(db_session=session)
        advice_result = await pos_service.get_position_advice(
            user_id=user_id,
            fund_code=fund_code,
            current_position_pct=current_position_pct,
            cash_amount=cash_amount,        # V5.1: 传入现金余额
            total_assets=denominator,      # V5.1: 传入总资产(分母值)
        )
        if advice_result.get("code") == 0 and advice_result.get("data"):
            ad = advice_result["data"]
            market_status = ad.get("market_status")
            # target_position_pct 转为 0-100 百分比供前端展示
            raw_target_pct = ad.get("target_position_pct", 0) or 0
            raw_current_pct = ad.get("current_position_pct", 0) or 0

            # 取结构化 gates 数据
            ad_gates = ad.get("gates")  # 新结构化 Gate 对象（来自 position_service）
            ad_track_type = ad.get("track_type")  # 轨道类型顶层字段
            ad_tg = ad.get("trend_guard", {})

            # 如果 gates 不在 advice 顶层，从 trend_guard 内取
            if ad_gates is None and isinstance(ad_tg, dict) and "gate_1" in ad_tg:
                ad_gates = ad_tg
            if ad_track_type is None and isinstance(ad_tg, dict):
                ad_track_type = ad_tg.get("sector_track")

            position_advice_data = {
                "action": ad.get("action"),
                "target_position_pct": round(raw_target_pct * 100, 1),
                "reason": ad.get("reason", ""),
                "trend_guard_text": ad.get("trend_guard_text", "") or ad.get("trend_text", ""),
                # 结构化 Gate 数据（Phase 0a/0b）
                "gates": ad_gates,
                "track_type": ad_track_type,  # 轨道类型顶层（前端直接读）
                # 兼容字段（保留旧字段名供过渡）
                "recommendation": ad.get("action"),
                "suggested_action": ad.get("action"),
                "suggested_amount": round(raw_target_pct * 100, 1),  # DEPRECATED: 此值是百分比而非金额, 请用 suggested_target_pct
                "suggested_target_pct": round(raw_target_pct * 100, 1),  # 目标仓位百分比(占总资产)
                "suggested_buy_amount": round((raw_target_pct - raw_current_pct) * denominator, 0) if raw_target_pct > raw_current_pct else 0,  # 建议加仓金额(元)
                "suggested_sell_amount": round((raw_current_pct - raw_target_pct) * denominator, 0) if raw_current_pct > raw_target_pct else 0,  # 建议减仓金额(元)
                "recommendationReason": ad.get("reason"),
                "signal_level": ad.get("signal_level"),
                "confidence_stars": ad.get("confidence_stars"),
                "current_position_pct": round(raw_current_pct * 100, 1),
                "regime": ad.get("regime"),
                "composite_score": ad.get("composite_score"),
                "denominator_type": settings.V5_POSITION_DENOMINATOR,  # 分母类型标记
                "total_assets": round(denominator, 2),  # 总资产(分母值), 供前端金额计算
                "cash_warning": ad.get("cash_warning"),  # V5.1: 现金不足警告
                "sentiment_source": ad.get("sentiment_source", "broad"),  # V5.2: 情绪来源(broad/sector)
                "portfolio_constraints": ad.get("portfolio_constraints", []),  # V5.1: 组合约束说明
                "constraint_detail": ad.get("constraint_detail", {}),  # V5.1: 约束细节
                "trend_text": ad.get("trend_text"),
                "trend_guard": ad.get("trend_guard"),  # DEPRECATED: 请改用 gates
            }


            # Phase 0c: 用 positionAdvice 的 trend_guard 填充顶层 trend_guard_data
            # （单一来源，不再有两份矛盾数据）
            if ad_tg and isinstance(ad_tg, dict):
                trend_guard_data = {
                    "trend_signal": ad_tg.get("trend_signal", ""),
                    "macd_signal": ad_tg.get("macd_signal", ""),
                    "macd_detail": ad_tg.get("macd_detail", {}),             # 新增：完整 dict 详情
                    "oscillation_silence": ad_tg.get("oscillation_silence", False),
                    "gate_triggered": ad_tg.get("gate_triggered"),  # DEPRECATED
                    "gates": ad_gates,
                    "sector_track": ad_track_type,
                    "operation_suggestion": ad_tg.get("operation_suggestion", ""),
                    "trend_narrative": ad_tg.get("trend_narrative", ""),
                }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"获取仓位建议失败(fund-detail): {e}")

    # 获取用户现金余额和总资产（前端加仓建议联动现金需要）
    cash_amount_val = 0.0
    total_assets_val = 0.0
    try:
        cash_stmt_fd = select(UserCash).where(UserCash.user_id == user_id)
        cash_result_fd = await session.execute(cash_stmt_fd)
        cash_row_fd = cash_result_fd.scalar_one_or_none()
        if cash_row_fd:
            cash_amount_val = float(cash_row_fd.cash_amount)
        # 计算总资产 = 持仓总额 + 现金
        total_assets_val = round(total_market_value + cash_amount_val, 2) if total_market_value else round(cash_amount_val, 2)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"获取现金余额失败(fund-detail): {e}")

    # Phase 2: signal_switched_today — 信号当日切换检测
    signal_switched_today = False
    try:
        from sqlalchemy import text as sa_text
        fm_result = await session.execute(
            sa_text("SELECT index_code FROM fund_mapping WHERE fund_code = :code LIMIT 1"),
            {"code": fund_code},
        )
        fm_row = fm_result.first()
        ts_index = "000300.SH"  # 默认沪深300
        if fm_row and fm_row[0]:
            ts_index = to_tushare(fm_row[0])
        # 比对今日vs昨日 signal_level
        today_r = await session.execute(
            sa_text("SELECT signal_level FROM market_sentiment WHERE index_code = :ts_code AND trade_date = CURDATE() LIMIT 1"),
            {"ts_code": ts_index},
        )
        yesterday_r = await session.execute(
            sa_text("SELECT signal_level FROM market_sentiment WHERE index_code = :ts_code AND trade_date = DATE_SUB(CURDATE(), INTERVAL 1 DAY) LIMIT 1"),
            {"ts_code": ts_index},
        )
        t_sig = today_r.first()
        y_sig = yesterday_r.first()
        if t_sig and y_sig and t_sig[0] != y_sig[0]:
            signal_switched_today = True
    except Exception:
        pass

    # 获取情绪因子详情（用于前端推荐理由展示）
    # 因子数据始终取沪深300宽基pipeline结果（板块基金也用宽基因子）
    sentiment_detail = None
    try:
        from app.core.redis_client import cache_get as _cache_get
        from datetime import date as _date, timedelta as _td
        _today_str = _date.today().isoformat()
        _yesterday_str = (_date.today() - _td(days=1)).isoformat()
        for _d in (_today_str, _yesterday_str):
            _cached = await _cache_get(f"fsa:sentiment:SH000300:{_d}")
            if _cached and _cached.get("factor_details"):
                sentiment_detail = {"factors": _cached["factor_details"]}
                break
    except Exception:
        pass

    data = {
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
        "market_status": market_status,
        "positionAdvice": position_advice_data,
        "cash_amount": round(cash_amount_val, 2),
        "total_assets": round(total_assets_val, 2),
        "signal_switched_today": signal_switched_today,
        "sentiment_detail": sentiment_detail,
    }

    # 写入缓存（TTL=300s，盘中估值5分钟过期）
    try:
        await cache_set(_fund_detail_cache_key, data, ttl=300)
    except Exception:
        pass

    elapsed_fd = (datetime.now() - start_fd).total_seconds()
    return {
        "code": 0,
        "data": data,
        "message": "ok",
        "cached": False,
        "elapsed_seconds": round(elapsed_fd, 2),
    }


# ============================================================
# V5.0 信号切换检测接口（轻量查询，不走缓存）
# ============================================================

@router.get("/signal-switched")
async def check_signal_switched(
    fund_codes: str = Query(..., description="逗号分隔的基金代码列表，如 004643,008714"),
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    检测持仓基金对应的指数今日信号是否发生切换。
    逻辑: fund_code -> fund_mapping查index_code -> to_tushare()
          -> market_sentiment查今日和昨日signal_level -> 比对是否不同
    """
    from sqlalchemy import text
    from app.utils.code_format import to_tushare, to_display

    codes = [c.strip() for c in fund_codes.split(",") if c.strip()]
    result_map: dict[str, bool] = {}

    for fund_code in codes:
        # 1. 查 fund_mapping 获取 index_code
        default_ts_index = "000300.SH"  # 沪深300 Tushare格式
        ts_index = default_ts_index
        try:
            fm_result = await session.execute(
                text("SELECT index_code FROM fund_mapping WHERE fund_code = :code LIMIT 1"),
                {"code": fund_code},
            )
            fm_row = fm_result.first()
            if fm_row and fm_row[0]:
                ts_index = to_tushare(fm_row[0])
        except Exception:
            pass

        # 2. 查 market_sentiment 今日和昨日的 signal_level
        try:
            today_result = await session.execute(
                text(
                    "SELECT signal_level FROM market_sentiment "
                    "WHERE index_code = :ts_code AND trade_date = CURDATE() "
                    "LIMIT 1"
                ),
                {"ts_code": ts_index},
            )
            today_row = today_result.first()
            today_signal = today_row[0] if today_row else None

            yesterday_result = await session.execute(
                text(
                    "SELECT signal_level FROM market_sentiment "
                    "WHERE index_code = :ts_code AND trade_date = DATE_SUB(CURDATE(), INTERVAL 1 DAY) "
                    "LIMIT 1"
                ),
                {"ts_code": ts_index},
            )
            yesterday_row = yesterday_result.first()
            yesterday_signal = yesterday_row[0] if yesterday_row else None

            # 3. 比对
            if today_signal and yesterday_signal and today_signal != yesterday_signal:
                result_map[fund_code] = True
            else:
                result_map[fund_code] = False
        except Exception:
            result_map[fund_code] = False

    return {"code": 0, "data": result_map}


# ============================================================
# V3.0 Batch endpoints - Portfolio page first-screen optimization (53->4 requests)
# ============================================================

class BatchFundDetailRequest(BaseModel):
    """Batch fund detail request"""
    fund_codes: list[str]


@router.post("/batch-fund-detail")
async def batch_fund_detail(
    body: BatchFundDetailRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Batch fetch fund details (V3.0 portfolio optimization).

    Parallel processing of N funds, each with independent session.
    Internally reuses get_fund_detail_for_portfolio logic (with cache).

    Returns: { fund_code: detail_data, ... }
    """
    from app.core.database import get_session_factory as _get_sf

    async def _fetch_one(fc: str) -> tuple[str, dict | None]:
        try:
            sf = _get_sf()
            async with sf() as sess:
                result = await get_fund_detail_for_portfolio(
                    fund_code=fc,
                    user_id=user_id,
                    session=sess,
                )
                if result.get("code") == 0 and result.get("data"):
                    return (fc, result["data"])
                return (fc, None)
        except Exception as e:
            logger.error("batch-fund-detail error for %s: %s", fc, e)
            return (fc, None)

    tasks = [_fetch_one(fc) for fc in body.fund_codes if fc]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    data = {fc: detail for fc, detail in results if detail is not None}

    return {
        "code": 0,
        "data": data,
        "message": "ok",
        "total_requested": len(body.fund_codes),
        "total_returned": len(data),
    }


@router.post("/batch-advice-trade")
async def batch_advice_trade(
    body: BatchFundDetailRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Batch fetch advice history + trade records (V3.0 portfolio optimization).

    Single DB query for all funds, avoiding N+1 queries.

    Returns: { fund_code: { "advice": {...}, "trades": {...} }, ... }
    """
    from app.models.advice_log import AdviceLog
    from app.models.position_execution import PositionExecution

    fund_codes = [fc for fc in body.fund_codes if fc]
    if not fund_codes:
        return {"code": 0, "data": {}, "message": "ok"}

    # Batch query advice history
    advice_stmt = (
        select(AdviceLog)
        .where(
            AdviceLog.user_id == user_id,
            AdviceLog.index_code.in_(fund_codes),
        )
        .order_by(AdviceLog.trade_date.desc())
        .limit(len(fund_codes) * 20)
    )
    advice_result = await session.execute(advice_stmt)
    advice_rows = advice_result.scalars().all()

    advice_by_code: dict[str, list] = {fc: [] for fc in fund_codes}
    advice_stats_by_code: dict[str, dict] = {fc: {"total": 0, "verified": 0, "correct": 0} for fc in fund_codes}

    for row in advice_rows:
        fc = row.index_code
        if fc not in advice_by_code:
            continue
        advice_by_code[fc].append({
            "id": row.id,
            "date": row.trade_date.strftime("%Y-%m-%d %H:%M") if row.trade_date else "",
            "advice_date": row.advice_date.strftime("%Y-%m-%d") if row.advice_date else "",
            "signal_level": row.signal_level or row.sentiment_label,
            "confidence_stars": row.confidence_stars,
            "advice_type": row.advice_type,
            "advice_content": row.advice_content,
            "suggested_position": row.suggested_position,
            "is_executed": bool(row.is_executed) or row.is_executed_at is not None,
            "is_verified": bool(row.is_verified),
            "actual_result": row.actual_result,
            "accuracy_score": row.accuracy_score,
            "execution_note": row.execution_note or "",
        })
        advice_stats_by_code[fc]["total"] += 1
        if row.is_verified:
            advice_stats_by_code[fc]["verified"] += 1
            if row.accuracy_score is not None and row.accuracy_score > 0.5:
                advice_stats_by_code[fc]["correct"] += 1

    # Batch query trade records
    trade_stmt = (
        select(PositionExecution)
        .where(
            PositionExecution.user_id == user_id,
            PositionExecution.fund_code.in_(fund_codes),
        )
        .order_by(PositionExecution.execute_date.desc())
        .limit(len(fund_codes) * 20)
    )
    trade_result = await session.execute(trade_stmt)
    trade_rows = trade_result.scalars().all()

    trade_by_code: dict[str, list] = {fc: [] for fc in fund_codes}

    for row in trade_rows:
        fc = row.fund_code
        if fc not in trade_by_code:
            continue
        op_type = getattr(row, "operation_type", None)
        if op_type == "buy":
            trade_type = "买入"
        elif op_type == "sell":
            trade_type = "卖出"
        elif row.to_position_pct > row.from_position_pct:
            trade_type = "买入"
        elif row.to_position_pct < row.from_position_pct:
            trade_type = "卖出"
        else:
            trade_type = "调仓"

        trade_by_code[fc].append({
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
            "nav": getattr(row, "nav", None) or 0,
            "fee": 0,
        })

    # Assemble return data
    data = {}
    for fc in fund_codes:
        stats = advice_stats_by_code[fc]
        verified = stats["verified"]
        correct = stats["correct"]
        win_rate = round(correct / verified * 100, 1) if verified > 0 else 0

        data[fc] = {
            "advice": {
                "items": advice_by_code[fc][:10],
                "stats": {
                    "total_advice": stats["total"],
                    "verified_count": verified,
                    "win_rate": win_rate,
                },
            },
            "trades": {
                "items": trade_by_code[fc][:10],
            },
        }

    return {"code": 0, "data": data, "message": "ok"}
