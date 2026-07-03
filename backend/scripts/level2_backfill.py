#!/usr/bin/env python3
"""二期赛道factor_history批量回填 - 优化版"""
import sys
sys.path.insert(0, '/opt/fund-sentiment/v5-deploy/backend')

import asyncio
import numpy as np
import akshare as ak
from datetime import date
from sqlalchemy import text
from app.core.database import init_db, close_db, get_session_factory

TRACK_INDICES = {
    '000814': '中证畜牧养殖',
    '000849': '中证农业主题',
    '000813': '中证细分化工',
    '000152': '中证稀有金属',
    '399394': '国证半导体芯片',
    '931494': '中证消费电子',
    '931160': '中证全指半导体',
    '930653': '中证食品饮料',
    '931152': '中证创新药产业',
    '930903': '中证医疗器械',
    '000995': '中证全指公用事业',
    '399358': '国证绿色电力',
    '931151': '中证光伏产业',
    '000136': '中证TMT产业',
    '931877': '中证全指通信设备',
    '931079': '中证5G通信',
    '931039': '中证全指证券公司',
}

def fetch_prices(code, start_date='20240101', end_date='20260627'):
    try:
        df = ak.index_zh_a_hist(symbol=code, period='daily', start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []
        prices = []
        for _, row in df.iterrows():
            prices.append({
                'date': str(row['日期']),
                'close': float(row['收盘']),
                'amount': float(row.get('成交额', 0)),
            })
        return prices
    except Exception as e:
        print(f'  ERR {code}: {e}')
        return []

def compute_factors_ts(prices):
    if len(prices) < 30:
        return []
    closes = np.array([p['close'] for p in prices], dtype=float)
    amounts = np.array([p.get('amount', 0) for p in prices], dtype=float)
    dates = [p['date'] for p in prices]
    ts = []
    for i in range(20, len(prices)):
        wc = closes[:i+1]
        wa = amounts[:i+1]
        f = {}
        rets = np.diff(wc) / wc[:-1]
        if len(rets) >= 20:
            f['VOL'] = float(np.std(rets[-20:]) * np.sqrt(252))
        if len(wc) >= 15:
            d = np.diff(wc)
            g = np.where(d > 0, d, 0.0)
            l = np.where(d < 0, -d, 0.0)
            ag = g[:14].mean()
            al = l[:14].mean()
            for j in range(14, len(d)):
                ag = (ag * 13 + g[j]) / 14
                al = (al * 13 + l[j]) / 14
            rs = ag / al if al > 0 else 999
            f['RSI'] = float(100.0 - (100.0 / (1.0 + rs)))
        if len(wc) >= 20:
            w = wc[-20:]
            f['NHNL'] = 1.0 if wc[-1] >= np.max(w) else (-1.0 if wc[-1] <= np.min(w) else 0.0)
        if len(wa) >= 20 and np.mean(wa[-20:]) > 0:
            f['TURN'] = float(wa[-1] / np.mean(wa[-20:]))
        f['date'] = dates[i]
        ts.append(f)
    return ts

async def main():
    await init_db()
    sf = get_session_factory()

    print(f'factor_history batch backfill - {date.today()}')
    print(f'Indices: {len(TRACK_INDICES)}')

    # 1. Fetch all price data
    all_ts = {}
    for code, name in TRACK_INDICES.items():
        print(f'  {code} {name}...', end=' ')
        prices = fetch_prices(code)
        if not prices:
            print('FAIL')
            continue
        ts = compute_factors_ts(prices)
        all_ts[code] = ts
        print(f'OK {len(prices)}d {len(ts)}ts')

    # 2. Compute DIV (cross-track divergence per date)
    print('Computing DIV...')
    all_dates = set()
    for ts in all_ts.values():
        for item in ts:
            all_dates.add(item['date'])
    all_dates = sorted(all_dates)

    div_by_date = {}
    for d in all_dates:
        scores = []
        for code, ts in all_ts.items():
            for item in ts:
                if item['date'] == d:
                    vol = item.get('VOL', 0.5)
                    rsi = item.get('RSI', 50)
                    nhnl = item.get('NHNL', 0)
                    turn = item.get('TURN', 1)
                    vol_s = max(0, min(100, (vol - 0.1) / 0.3 * 100))
                    nhnl_s = 50 + nhnl * 50
                    turn_s = max(0, min(100, (turn - 0.5) / 1.5 * 100))
                    comp = vol_s * 0.25 + rsi * 0.15 + nhnl_s * 0.20 + turn_s * 0.28
                    scores.append(comp)
                    break
        if len(scores) >= 3:
            div_by_date[d] = float(np.std(scores))

    # 3. Batch insert
    print('Batch inserting...')
    total_inserted = 0

    async with sf() as s:
        for code, ts in all_ts.items():
            # Build batch rows
            batch = []
            for item in ts:
                td = item['date']
                for fn in ['TURN', 'VOL', 'NHNL', 'RSI']:
                    rv = item.get(fn)
                    if rv is not None:
                        batch.append((fn, code, td, float(rv), 50))

            # DIV for this track
            for d, dv in div_by_date.items():
                batch.append(('DIV', code, d, dv, 50))

            # Batch insert 200 at a time
            for i in range(0, len(batch), 200):
                chunk = batch[i:i+200]
                values_sql = ','.join(['(:fn%d,:ic%d,:td%d,:rv%d,:qp%d)' % (j, j, j, j, j) for j in range(len(chunk))])
                params = {}
                for j, row in enumerate(chunk):
                    params[f'fn{j}'] = row[0]
                    params[f'ic{j}'] = row[1]
                    params[f'td{j}'] = row[2]
                    params[f'rv{j}'] = row[3]
                    params[f'qp{j}'] = row[4]

                try:
                    # Use INSERT IGNORE to skip duplicates
                    sql = f'INSERT IGNORE INTO factor_history (factor_name, index_code, trade_date, raw_value, quantile_percentile) VALUES {values_sql}'
                    r = await s.execute(text(sql), params)
                    total_inserted += r.rowcount
                except Exception as e:
                    print(f'  Batch err {code}: {str(e)[:80]}')

            await s.commit()
            print(f'  {code}: batch={len(batch)}, inserted so far={total_inserted}')

    print(f'\nTotal inserted: {total_inserted}')

    # 4. Verify
    codes_str = "','".join(TRACK_INDICES.keys())
    async with sf() as s:
        r = await s.execute(text(
            f"SELECT COUNT(*) FROM factor_history WHERE index_code IN ('{codes_str}')"
        ))
        total = r.fetchone()[0]
        print(f'Verified: {total} rows in factor_history for theme indices')

        r = await s.execute(text(
            f"SELECT factor_name, COUNT(*) as cnt FROM factor_history "
            f"WHERE index_code IN ('{codes_str}') "
            f"GROUP BY factor_name ORDER BY cnt DESC"
        ))
        for row in r.fetchall():
            print(f'  {row[0]}: {row[1]} rows')

    await close_db()

if __name__ == '__main__':
    asyncio.run(main())
