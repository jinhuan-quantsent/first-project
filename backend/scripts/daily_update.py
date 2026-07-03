#!/usr/bin/env python3
"""
增强版 daily_update.py
- 自动检测 fund_basic 和 user_portfolio 中的基金
- 自动回填新基金的历史数据（最近 365 天）
- 更新最近5天的数据（防止周末/节假日漏数据）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import date, timedelta
from sqlalchemy import select, text

from app.core.config import settings
from app.core.database import init_db, close_db, get_session
from app.models.fund_nav import FundNav
from app.models.fund_basic import FundBasic
from app.models.user_portfolio import UserPortfolio


async def main():
    await init_db()
    print('✅ 数据库初始化完成')

    session_gen = get_session()
    session = await session_gen.__anext__()

    try:
        # 1. 获取 fund_basic 中的所有基金代码
        result = await session.execute(select(FundBasic.fund_code))
        basic_codes = [row[0] for row in result.all()]
        print(f'📊 fund_basic 中共有 {len(basic_codes)} 只基金')

        # 2. 获取 user_portfolio 中的所有基金代码（确保持仓基金被纳入更新）
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        portfolio_codes = [row[0] for row in result.all() if row[0]]
        print(f'💼 user_portfolio 中共有 {len(portfolio_codes)} 只基金: {portfolio_codes}')

        # 3. 合并去重
        all_fund_codes = list(set(basic_codes + portfolio_codes))
        print(f'📋 总共需要更新 {len(all_fund_codes)} 只基金')

        # 4. 获取 fund_nav 中已有数据的基金代码
        result = await session.execute(select(FundNav.fund_code).distinct())
        existing_fund_codes = {row[0] for row in result.all()}

        # 5. 找出新基金（在 fund_basic+portfolio 但不在 fund_nav）
        new_fund_codes = [code for code in all_fund_codes if code not in existing_fund_codes]

        if new_fund_codes:
            print(f'🆕 发现 {len(new_fund_codes)} 只新基金，开始回填历史数据：{new_fund_codes}')
            await backfill_funds(session, new_fund_codes, days=365)
        else:
            print('✅ 没有新基金')

        # 6. 更新最近5天的数据（补漏机制，防止周末/节假日漏数据）
        end_date = date.today()
        start_date = end_date - timedelta(days=5)
        print(f'📅 更新最近5天数据（{start_date.strftime("%Y%m%d")} ~ {end_date.strftime("%Y%m%d")}）')

        await update_recent(session, all_fund_codes, start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d'))

        await session.commit()
        print('✅ 全部完成')

    except Exception as e:
        print(f'❌ 更新失败：{e}')
        import traceback
        traceback.print_exc()
    finally:
        await session_gen.aclose()
        await close_db()


async def backfill_funds(session, fund_codes, days=365):
    """回填多只基金的历史数据"""
    import tushare as ts

    if not settings.TUSHARE_TOKEN:
        print('⚠️ TUSHARE_TOKEN 未配置，跳过回填')
        return

    pro = ts.pro_api(settings.TUSHARE_TOKEN)

    start_date = (date.today() - timedelta(days=days)).strftime('%Y%m%d')
    end_date = date.today().strftime('%Y%m%d')

    print(f'📥 回填历史数据：{start_date} ~ {end_date}')

    count = 0
    for fund_code in fund_codes:
        try:
            df = pro.fund_nav(ts_code=f'{fund_code}.OF', start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                print(f'  ⚠️ {fund_code}：无数据')
                continue

            for _, row in df.iterrows():
                nav = FundNav(
                    fund_code=fund_code,
                    nav_date=str(row['nav_date']),
                    nav=float(row['unit_nav']),
                    accumulated_nav=float(row['accum_nav']) if 'accum_nav' in row and row['accum_nav'] else None,
                    daily_return=float(row['daily_return']) if 'daily_return' in row and row['daily_return'] else None,
                )
                session.add(nav)
                count += 1

            print(f'  ✅ {fund_code}：添加 {len(df)} 条历史数据')

        except Exception as e:
            print(f'  ⚠️ {fund_code} 失败：{e}')

    print(f'✅ 历史数据回填完成：共 {count} 条')


async def update_recent(session, fund_codes, start_date, end_date):
    """更新最近N天的数据（补漏机制）"""
    import tushare as ts

    if not settings.TUSHARE_TOKEN:
        print('⚠️ TUSHARE_TOKEN 未配置，跳过更新')
        return

    pro = ts.pro_api(settings.TUSHARE_TOKEN)

    count = 0
    for fund_code in fund_codes:
        try:
            df = pro.fund_nav(ts_code=f'{fund_code}.OF', start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                # 检查是否已存在
                from sqlalchemy import select as sa_select
                existing = await session.execute(
                    sa_select(FundNav).where(
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
                count += 1

        except Exception as e:
            print(f'  ⚠️ {fund_code}: {e}')

    print(f'✅ 最近数据更新完成：新增 {count} 条')


if __name__ == '__main__':
    asyncio.run(main())
