"""
拉取基金历史数据并保存到数据库
用法：
    cd /opt/fund-sentiment/v5-deploy/backend
    source venv/bin/activate
    python3 scripts/fetch_fund_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import tushare as ts
from datetime import datetime, timedelta
from typing import List, Dict

# 设置 Tushare token
ts.set_token('297759fe167c66dd6973fe0cbe1606f1b7d3913b9e5d61bddeb31f68')
pro = ts.pro_api()

async def fetch_and_save_fund_nav(fund_code: str, start_date: str = "20250101", end_date: str = None):
    """
    拉取基金净值数据并保存到数据库
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    
    print(f"正在拉取 {fund_code} 净值数据（{start_date} 至 {end_date}）...")
    
    try:
        # 拉取数据
        df = pro.fund_nav(ts_code=f"{fund_code}.OF", start_date=start_date, end_date=end_date)
        
        if df is None or df.empty:
            print(f"  ⚠️ 基金 {fund_code} 无数据")
            return 0
        
        print(f"  ✅ 拉取成功，共 {len(df)} 条数据")
        
        # 保存到数据库
        from app.core.database import init_db, get_session
        from app.models.fund_nav import FundNav
        
        await init_db()
        
        async with get_session() as session:
            count = 0
            for _, row in df.iterrows():
                # 检查是否已存在
                from sqlalchemy import select
                stmt = select(FundNav).where(
                    FundNav.fund_code == fund_code,
                    FundNav.nav_date == str(row["nav_date"])
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    continue
                
                # 创建新记录
                nav = FundNav(
                    fund_code=fund_code,
                    nav_date=str(row["nav_date"]),
                    nav=float(row["unit_nav"]),
                    accumulated_nav=float(row["accum_nav"]) if "accum_nav" in row and row["accum_nav"] else None,
                    daily_return=float(row["daily_return"]) if "daily_return" in row and row["daily_return"] else None,
                )
                session.add(nav)
                count += 1
            
            await session.commit()
            print(f"  ✅ 保存成功，新增 {count} 条记录")
            return count
        
    except Exception as e:
        print(f"  ❌ 拉取失败：{e}")
        return 0

async def main():
    # 测试基金列表
    test_funds = [
        "110022",  # 易方达消费行业
        "510300",  # 沪深300ETF
        "510050",  # 上证50ETF
    ]
    
    for fund_code in test_funds:
        await fetch_and_save_fund_nav(fund_code)
        print()

if __name__ == "__main__":
    asyncio.run(main())
