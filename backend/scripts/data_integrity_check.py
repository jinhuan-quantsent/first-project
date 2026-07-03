#!/usr/bin/env python3
"""数据完整性校验脚本 — V5.0
每日运行，核对31板块×5因子×交易日理论值与实际值，标注缺失原因
""" 
import sys
sys.path.insert(0, '/opt/fund-sentiment/v5-deploy/backend')

import asyncio
from datetime import date, timedelta
from sqlalchemy import text
from app.core.config import settings
from app.core.database import init_db, close_db, get_session_factory

# V5核心因子
V5_FACTORS = ['TURN', 'VOL', 'NHNL', 'RSI', 'DIV']
# 预期板块数（31个申万一级 + 4个宽基指数 = 35）
EXPECTED_SECTOR_COUNT = 31
EXPECTED_BROAD_COUNT = 4

async def main():
    await init_db()
    sf = get_session_factory()
    async with sf() as s:
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        print('='*60)
        print(f'📊 V5.0 数据完整性校验报告 — {today}')
        print('='*60)
        
        # === 1. factor_history 表覆盖 ===
        print('\n## 1. factor_history 表覆盖')
        
        # 1a. V5核心5因子概况
        for f in V5_FACTORS:
            r = await s.execute(text(
                f'SELECT COUNT(*) as cnt, COUNT(DISTINCT index_code) as n_codes, '
                f'MIN(trade_date) as min_d, MAX(trade_date) as max_d '
                f'FROM factor_history WHERE factor_name=:fn'
            ), {'fn': f})
            row = r.fetchone()
            status = '✅' if row.n_codes >= EXPECTED_SECTOR_COUNT else '⚠️'
            print(f'  {status} {f}: {row.cnt} rows, {row.n_codes} codes, {row.min_d} ~ {row.max_d}')
        
        # 1b. COMPOSITE因子
        r = await s.execute(text(
            'SELECT COUNT(*) as cnt, COUNT(DISTINCT index_code) as n_codes, '
            'MIN(trade_date) as min_d, MAX(trade_date) as max_d '
            'FROM factor_history WHERE factor_name=:fn'
        ), {'fn': 'COMPOSITE'})
        row = r.fetchone()
        status = '⚠️' if row.n_codes < EXPECTED_SECTOR_COUNT else '✅'
        print(f'  {status} COMPOSITE: {row.cnt} rows, {row.n_codes} codes, {row.min_d} ~ {row.max_d}')
        
        # 1c. 近7天每日覆盖
        print('\n  近7天每日数据覆盖:')
        r = await s.execute(text(
            'SELECT trade_date, COUNT(DISTINCT index_code) as n_codes, '
            'COUNT(DISTINCT factor_name) as n_factors, COUNT(*) as total '
            'FROM factor_history WHERE trade_date >= :cutoff '
            'GROUP BY trade_date ORDER BY trade_date DESC'
        ), {'cutoff': str(today - timedelta(days=7))})
        for row in r.fetchall():
            expected = EXPECTED_SECTOR_COUNT * len(V5_FACTORS)  # 31*5=155 per day
            pct = (row.total / expected * 100) if expected > 0 else 0
            status = '✅' if pct >= 90 else '⚠️' if pct >= 30 else '🔴'
            print(f'  {status} {row.trade_date}: {row.n_codes} codes, {row.n_factors} factors, '
                  f'{row.total} rows ({pct:.1f}% of expected {expected})')
        
        # === 2. sector_sentiment 表覆盖 ===
        print('\n## 2. sector_sentiment 表覆盖')
        r = await s.execute(text(
            'SELECT COUNT(*) as cnt, MIN(calc_date) as min_d, MAX(calc_date) as max_d '
            'FROM sector_sentiment'
        ))
        row = r.fetchone()
        print(f'  总计: {row.cnt} rows, {row.min_d} ~ {row.max_d}')
        
        # 近7天
        r = await s.execute(text(
            'SELECT calc_date, COUNT(*) as cnt FROM sector_sentiment '
            'WHERE calc_date >= :cutoff GROUP BY calc_date ORDER BY calc_date DESC'
        ), {'cutoff': str(today - timedelta(days=7))})
        for row in r.fetchall():
            status = '✅' if row.cnt >= EXPECTED_SECTOR_COUNT else '⚠️'
            print(f'  {status} {row.calc_date}: {row.cnt} sectors (expected {EXPECTED_SECTOR_COUNT})')
        
        # === 3. market_sentiment 表覆盖 ===
        print('\n## 3. market_sentiment 表覆盖（4宽基指数）')
        r = await s.execute(text(
            'SELECT COUNT(*) as cnt, MIN(trade_date) as min_d, MAX(trade_date) as max_d '
            'FROM market_sentiment'
        ))
        row = r.fetchone()
        print(f'  总计: {row.cnt} rows, {row.min_d} ~ {row.max_d}')
        
        r = await s.execute(text(
            'SELECT trade_date, COUNT(*) as cnt FROM market_sentiment '
            'WHERE trade_date >= :cutoff GROUP BY trade_date ORDER BY trade_date DESC'
        ), {'cutoff': str(today - timedelta(days=7))})
        for row in r.fetchall():
            status = '✅' if row.cnt >= EXPECTED_BROAD_COUNT else '⚠️'
            print(f'  {status} {row.trade_date}: {row.cnt} indices (expected {EXPECTED_BROAD_COUNT})')
        
        # === 4. DIV因子专项 ===
        print('\n## 4. DIV因子专项（跨板块分歧度）')
        r = await s.execute(text(
            'SELECT COUNT(*) as cnt, MIN(trade_date) as min_d, MAX(trade_date) as max_d '
            'FROM factor_history WHERE factor_name=:fn AND index_code=:ic'
        ), {'fn': 'DIV', 'ic': 'SW_L1_DIV'})
        row = r.fetchone()
        print(f'  DIV (SW_L1_DIV): {row.cnt} rows, {row.min_d} ~ {row.max_d}')
        
        # DIV近3天
        r = await s.execute(text(
            'SELECT trade_date, raw_value, quantile_percentile FROM factor_history '
            'WHERE factor_name=:fn AND index_code=:ic AND trade_date >= :cutoff '
            'ORDER BY trade_date DESC'
        ), {'fn': 'DIV', 'ic': 'SW_L1_DIV', 'cutoff': str(today - timedelta(days=3))})
        for row in r.fetchall():
            print(f'  {row.trade_date}: raw={row.raw_value}, percentile={row.quantile_percentile}')
        
        # === 5. 缺失标注 ===
        print('\n## 5. 缺失标注')
        
        # 检查近3天板块级factor缺失
        for td in [today, yesterday, today - timedelta(days=2)]:
            td_str = str(td)
            r = await s.execute(text(
                'SELECT COUNT(DISTINCT index_code) as n_codes FROM factor_history '
                'WHERE factor_name IN (:f1,:f2,:f3,:f4) AND trade_date=:td '
                'AND index_code NOT IN (:i1,:i2,:i3,:i4)'
            ), {'f1':'TURN','f2':'VOL','f3':'NHNL','f4':'RSI',
                'td': td_str, 'i1':'000001.SH','i2':'000300.SH','i3':'399001.SZ','i4':'399006.SZ'})
            row = r.fetchone()
            if row.n_codes < EXPECTED_SECTOR_COUNT:
                print(f'  🔴 {td_str}: 板块级factor缺失! 仅{row.n_codes}个板块有数据(预期{EXPECTED_SECTOR_COUNT})')
                print(f'     原因: score_sectors()不持久化板块因子到factor_history')
            else:
                print(f'  ✅ {td_str}: {row.n_codes}板块有factor数据')
        
        # sector_sentiment缺失
        for td in [today, yesterday]:
            td_str = str(td)
            r = await s.execute(text(
                'SELECT COUNT(*) as cnt FROM sector_sentiment WHERE calc_date=:td'
            ), {'td': td_str})
            row = r.fetchone()
            if row.cnt < EXPECTED_SECTOR_COUNT:
                print(f'  🔴 {td_str}: sector_sentiment缺失! 仅{row.cnt}条(预期{EXPECTED_SECTOR_COUNT})')
            else:
                print(f'  ✅ {td_str}: sector_sentiment {row.cnt}条完整')

    await close_db()

if __name__ == '__main__':
    asyncio.run(main())
