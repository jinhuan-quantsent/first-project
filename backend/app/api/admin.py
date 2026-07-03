from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, timedelta
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.database import get_session
from app.models.fund_basic import FundBasic
from app.models.fund_nav import FundNav
from app.models.user_portfolio import UserPortfolio
from app.models.position_execution import PositionExecution
from app.core.config import settings
from app.utils.eastmoney import code_to_tushare

router = APIRouter(prefix="/api/v5/admin")
logger = logging.getLogger(__name__)


class BackfillRequest(BaseModel):
    fund_code: Optional[str] = None
    all: Optional[bool] = False
    days: Optional[int] = 365


class BackfillResponse(BaseModel):
    status: str
    message: str
    fund_codes: List[str]
    days: int
    total_records: int
    reconciled: int = 0


class ReconcileRequest(BaseModel):
    fund_code: Optional[str] = None
    all: Optional[bool] = False


@router.post("/backfill-fund", response_model=BackfillResponse)
async def backfill_fund(req: BackfillRequest, session: AsyncSession = Depends(get_session)):
    """
    手动触发基金历史数据回填
    回填后自动对账：修正持仓的成本净值（如果建仓时用了错误净值）
    """
    if not req.all and not req.fund_code:
        raise HTTPException(status_code=400, detail="必须指定 fund_code 或 all=true")

    if req.all and req.fund_code:
        raise HTTPException(status_code=400, detail="不能同时使用 fund_code 和 all=true")

    if req.all:
        # 修复④: 同时覆盖 fund_basic + user_portfolio，避免持仓基金不在 basic 表中无法回填
        from app.models.user_portfolio import UserPortfolio
        basic_result = await session.execute(select(FundBasic.fund_code))
        basic_codes = [row[0] for row in basic_result.all()]
        portfolio_result = await session.execute(select(UserPortfolio.fund_code).distinct())
        portfolio_codes = [row[0] for row in portfolio_result.all()]
        fund_codes = list(set(basic_codes + portfolio_codes))
    else:
        fund_codes = [req.fund_code]

    if not fund_codes:
        raise HTTPException(status_code=404, detail="没有找到基金")

    total_records, funds_with_data, funds_no_data = await _backfill_funds(session, fund_codes, req.days)

    # 回填后自动对账：修正持仓成本净值
    reconciled_count = await _reconcile_portfolio_navs(session, fund_codes)

    await session.commit()

    # 构建更清晰的提示消息
    if total_records > 0:
        msg = f"回填完成：{len(fund_codes)} 只基金，新增 {total_records} 条数据"
    elif funds_with_data:
        msg = f"回填完成：{len(fund_codes)} 只基金，共 0 条新增（{len(funds_with_data)} 只已有完整数据）"
    else:
        msg = f"回填完成：{len(fund_codes)} 只基金，共 0 条数据（{len(funds_no_data)} 只无数据源）"

    if reconciled_count > 0:
        msg += f"，已修正 {reconciled_count} 条持仓成本净值"

    return BackfillResponse(
        status="success",
        message=msg,
        fund_codes=fund_codes,
        days=req.days,
        total_records=total_records,
        reconciled=reconciled_count,
    )


@router.post("/reconcile-portfolio")
async def reconcile_portfolio(req: ReconcileRequest, session: AsyncSession = Depends(get_session)):
    """
    对账修正持仓成本净值
    当建仓时 fund_nav 表无数据导致用了最新净值作为成本净值时，
    此接口会根据 fund_nav 历史数据修正 cost_nav 及相关字段。
    """
    if not req.all and not req.fund_code:
        raise HTTPException(status_code=400, detail="必须指定 fund_code 或 all=true")

    if req.all:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]
    else:
        fund_codes = [req.fund_code]

    if not fund_codes:
        return {"status": "success", "message": "没有需要对账的持仓", "reconciled": 0}

    reconciled_count = await _reconcile_portfolio_navs(session, fund_codes)
    await session.commit()

    return {
        "status": "success",
        "message": f"对账完成：修正 {reconciled_count} 条持仓",
        "fund_codes": fund_codes,
        "reconciled": reconciled_count,
    }


async def _backfill_funds(session: AsyncSession, fund_codes: List[str], days: int):
    """回填多只基金的历史数据，返回 (新增条数, 有数据的基金列表, 无数据的基金列表)"""
    import tushare as ts

    if not settings.TUSHARE_TOKEN:
        raise HTTPException(status_code=500, detail="TUSHARE_TOKEN 未配置")

    pro = ts.pro_api(settings.TUSHARE_TOKEN)

    start_date = (date.today() - timedelta(days=days)).strftime('%Y%m%d')
    end_date = date.today().strftime('%Y%m%d')

    print(f"📥 回填历史数据：{start_date} ~ {end_date}")

    total_count = 0
    funds_with_data = []
    funds_no_data = []

    for fund_code in fund_codes:
        try:
            ts_code = code_to_tushare(fund_code)
            base_code = ts_code.split(".")[0]
            primary_suffix = ts_code.split(".")[-1] if "." in ts_code else "OF"
            suffixes = [primary_suffix]
            if primary_suffix == "OF":
                suffixes.extend(["SH", "SZ"])
            elif primary_suffix in ("SH", "SZ"):
                suffixes.extend(["OF", "SZ" if primary_suffix == "SH" else "SH"])

            df = None
            for suf in suffixes:
                try_code = f"{base_code}.{suf}"
                df = pro.fund_nav(ts_code=try_code, start_date=start_date, end_date=end_date)
                if df is not None and not df.empty:
                    break
                df = None
            if df is None or df.empty:
                print(f"  WARNING {fund_code}: no data (tried: {suffixes})")
                funds_no_data.append(fund_code)
                continue

            funds_with_data.append(fund_code)
            new_count = 0
            for _, row in df.iterrows():
                existing = await session.execute(
                    select(FundNav).where(
                        FundNav.fund_code == fund_code,
                        FundNav.nav_date == str(row['nav_date'])
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                nav = FundNav(
                    fund_code=fund_code,
                    nav_date=str(row['nav_date']),
                    nav=float(row['unit_nav']),
                    accumulated_nav=float(row['accum_nav']) if 'accum_nav' in row and row['accum_nav'] else None,
                    daily_return=float(row['daily_return']) if 'daily_return' in row and row['daily_return'] else None,
                )
                session.add(nav)
                total_count += 1
                new_count += 1

            if new_count > 0:
                print(f"  ✅ {fund_code}：新增 {new_count} 条（API返回 {len(df)} 条）")
            else:
                print(f"  ℹ️  {fund_code}：0 条新增（{len(df)} 条已存在）")
            await asyncio.sleep(0.3)

        except Exception as e:
            print(f"  ❌ {fund_code} 失败：{e}")
            funds_no_data.append(fund_code)

    print(f"✅ 历史数据回填完成：新增 {total_count} 条")
    return total_count, funds_with_data, funds_no_data


async def _reconcile_portfolio_navs(session: AsyncSession, fund_codes: List[str]) -> int:
    """
    对账修正持仓成本净值

    对于每只基金：
    1. 查找 user_portfolio 中有 buy_date 的持仓
    2. 从 fund_nav 查找 buy_date 当天或最近前一交易日的净值（正确 cost_nav）
    3. 从 fund_nav 查找最新净值（正确 current_nav）
    4. 如果 cost_nav 不匹配，重算 holding_shares / market_value / total_return / return_rate
    5. 同步修正 position_execution 的 nav 字段

    注意：仅修正单次买入、无后续加减仓的持仓，避免破坏加权平均成本。
    """
    fixed_count = 0

    for fund_code in fund_codes:
        # 查找该基金的所有持仓
        portfolio_result = await session.execute(
            select(UserPortfolio).where(UserPortfolio.fund_code == fund_code)
        )
        portfolios = portfolio_result.scalars().all()

        for portfolio in portfolios:
            if not portfolio.buy_date:
                continue

            # 检查是否有多次操作（buy/sell），如果有则跳过（加权平均成本场景）
            exec_result = await session.execute(
                select(PositionExecution).where(
                    and_(
                        PositionExecution.fund_code == fund_code,
                        PositionExecution.user_id == portfolio.user_id,
                    )
                ).order_by(PositionExecution.execute_date)
            )
            executions = exec_result.scalars().all()

            # 仅修正只有单次买入操作的持仓
            buy_ops = [e for e in executions if e.operation_type == 'buy']
            sell_ops = [e for e in executions if e.operation_type == 'sell']
            if len(buy_ops) != 1 or len(sell_ops) > 0:
                continue

            buy_exec = buy_ops[0]
            original_amount = buy_exec.amount or portfolio.market_value or 0
            if original_amount <= 0:
                continue

            # 从 fund_nav 查找 buy_date 当天或最近前一交易日的净值
            nav_result = await session.execute(
                select(FundNav).where(
                    and_(
                        FundNav.fund_code == fund_code,
                        FundNav.nav_date <= portfolio.buy_date,
                    )
                ).order_by(FundNav.nav_date.desc()).limit(1)
            )
            nav_row = nav_result.scalar_one_or_none()
            if not nav_row or not nav_row.nav or nav_row.nav <= 0:
                continue

            correct_cost_nav = round(float(nav_row.nav), 4)

            # 如果 cost_nav 已经正确，跳过
            if abs(portfolio.cost_nav - correct_cost_nav) < 0.0001:
                continue

            # 查找最新净值作为 current_nav
            latest_nav_result = await session.execute(
                select(FundNav).where(
                    FundNav.fund_code == fund_code,
                ).order_by(FundNav.nav_date.desc()).limit(1)
            )
            latest_nav_row = latest_nav_result.scalar_one_or_none()
            if latest_nav_row and latest_nav_row.nav and latest_nav_row.nav > 0:
                latest_nav = round(float(latest_nav_row.nav), 4)
            else:
                latest_nav = portfolio.current_nav

            # 记录旧值用于日志
            old_cost_nav = portfolio.cost_nav
            old_shares = portfolio.holding_shares

            # 重算
            new_holding_shares = round(original_amount / correct_cost_nav, 4)
            new_market_value = round(new_holding_shares * latest_nav, 2)
            new_total_return = round(new_market_value - original_amount, 2)
            new_return_rate = round((latest_nav / correct_cost_nav - 1) * 100, 2) if correct_cost_nav > 0 else 0

            # 更新 user_portfolio
            portfolio.cost_nav = correct_cost_nav
            portfolio.holding_shares = new_holding_shares
            portfolio.current_nav = latest_nav
            portfolio.market_value = new_market_value
            portfolio.total_return = new_total_return
            portfolio.return_rate = new_return_rate

            # 同步修正 position_execution
            buy_exec.nav = correct_cost_nav

            logger.info(
                f"Reconciled {fund_code} (portfolio id={portfolio.id}): "
                f"cost_nav {old_cost_nav} -> {correct_cost_nav}, "
                f"shares {old_shares} -> {new_holding_shares}, "
                f"current_nav={latest_nav}, market_value={new_market_value}, "
                f"return_rate={new_return_rate}%"
            )
            print(
                f"  🔧 对账修正 {fund_code}: cost_nav {old_cost_nav} -> {correct_cost_nav}, "
                f"shares {old_shares} -> {new_holding_shares}, return_rate={new_return_rate}%"
            )
            fixed_count += 1

    if fixed_count > 0:
        print(f"✅ 对账完成：修正 {fixed_count} 条持仓")

    return fixed_count
