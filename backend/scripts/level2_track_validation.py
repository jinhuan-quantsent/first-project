#!/usr/bin/env python3
"""二期赛道独立验证 - V5.0
1. 更新 track_index_code (16个主题指数)
2. AKShare获取价格数据 -> 计算5因子
3. IC/IR验证
4. factor_history回填
5. 信号边界分布检查
"""
import sys
sys.path.insert(0, '/opt/fund-sentiment/v5-deploy/backend')

import asyncio
import numpy as np
import akshare as ak
from datetime import date, timedelta
from sqlalchemy import text
from app.core.database import init_db, close_db, get_session_factory

# ============================================================
# 二级赛道 -> 主题指数代码映射
# ============================================================
TRACK_INDEX_MAP = {
    '012725': ('000814', '中证畜牧养殖'),
    '010770': ('000849', '中证农业主题'),
    '020274': ('000813', '中证细分化工'),
    '011036': ('000152', '中证稀有金属'),
    '014111': ('000152', '中证稀有金属'),
    '008888': ('399394', '国证半导体芯片'),
    '014907': ('931494', '中证消费电子'),
    '007301': ('931160', '中证全指半导体'),
    '001632': ('930653', '中证食品饮料'),
    '019667': ('931152', '中证创新药产业'),
    '021251': ('930903', '中证医疗器械'),
    '022873': ('000995', '中证全指公用事业'),
    '017175': ('399358', '国证绿色电力'),
    '012680': ('931151', '中证光伏产业'),
    '018049': ('000136', '中证TMT产业'),
    '020900': ('931877', '中证全指通信设备'),
    '008087': ('931079', '中证5G通信'),
    '008591': ('931039', '中证全指证券公司'),
}

V5_FACTORS = ['TURN', 'VOL', 'NHNL', 'RSI', 'DIV']

def fetch_index_prices(code, start_date='20240101', end_date='20260627'):
    try:
        df = ak.index_zh_a_hist(symbol=code, period='daily', start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            return []
        prices = []
        for _, row in df.iterrows():
            prices.append({
                'date': str(row['日期']),
                'close': float(row['收盘']),
                'volume': float(row.get('成交量', 0)),
                'amount': float(row.get('成交额', 0)),
            })
        return prices
    except Exception as e:
        print(f'  ERROR {code}: {e}')
        return []

def compute_factors_from_prices(prices):
    if not prices or len(prices) < 20:
        return {}
    closes = np.array([p['close'] for p in prices], dtype=float)
    amounts = np.array([p.get('amount', 0) for p in prices], dtype=float)
    result = {}
    returns = np.diff(closes) / closes[:-1]
    if len(returns) >= 20:
        result['VOL'] = float(np.std(returns[-20:]) * np.sqrt(252))
    if len(closes) >= 15:
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_gain = gains[:14].mean()
        avg_loss = losses[:14].mean()
        for i in range(14, len(deltas)):
            avg_gain = (avg_gain * 13 + gains[i]) / 14
            avg_loss = (avg_loss * 13 + losses[i]) / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 999
        result['RSI'] = float(100.0 - (100.0 / (1.0 + rs)))
    if len(closes) >= 20:
        window = closes[-20:]
        result['NHNL'] = 1.0 if closes[-1] >= np.max(window) else (-1.0 if closes[-1] <= np.min(window) else 0.0)
    if len(amounts) >= 20 and np.mean(amounts[-20:]) > 0:
        result['TURN'] = float(amounts[-1] / np.mean(amounts[-20:]))
    return result

def compute_factors_timeseries(prices):
    if len(prices) < 30:
        return []
    closes = np.array([p['close'] for p in prices], dtype=float)
    amounts = np.array([p.get('amount', 0) for p in prices], dtype=float)
    dates = [p['date'] for p in prices]
    ts = []
    for i in range(20, len(prices)):
        window_closes = closes[:i+1]
        window_amounts = amounts[:i+1]
        factors = {}
        returns = np.diff(window_closes) / window_closes[:-1]
        if len(returns) >= 20:
            factors['VOL'] = float(np.std(returns[-20:]) * np.sqrt(252))
        if len(window_closes) >= 15:
            deltas = np.diff(window_closes)
            gains = np.where(deltas > 0, deltas, 0.0)
            losses = np.where(deltas < 0, -deltas, 0.0)
            avg_gain = gains[:14].mean()
            avg_loss = losses[:14].mean()
            for j in range(14, len(deltas)):
                avg_gain = (avg_gain * 13 + gains[j]) / 14
                avg_loss = (avg_loss * 13 + losses[j]) / 14
            rs = avg_gain / avg_loss if avg_loss > 0 else 999
            factors['RSI'] = float(100.0 - (100.0 / (1.0 + rs)))
        if len(window_closes) >= 20:
            w = window_closes[-20:]
            factors['NHNL'] = 1.0 if window_closes[-1] >= np.max(w) else (-1.0 if window_closes[-1] <= np.min(w) else 0.0)
        if len(window_amounts) >= 20 and np.mean(window_amounts[-20:]) > 0:
            factors['TURN'] = float(window_amounts[-1] / np.mean(window_amounts[-20:]))
        if i < len(prices) - 1:
            factors['next_return'] = float((closes[i+1] - closes[i]) / closes[i])
        factors['date'] = dates[i]
        ts.append(factors)
    return ts

def calc_ic_ir(timeseries, factor_name):
    ic_values = []
    for item in timeseries:
        fv = item.get(factor_name)
        nr = item.get('next_return')
        if fv is not None and nr is not None and fv != 0:
            ic_values.append(1.0 if (fv * nr) > 0 else -1.0)
    if len(ic_values) < 10:
        return None
    ic_mean = np.mean(ic_values)
    ic_std = np.std(ic_values)
    ir = ic_mean / ic_std if ic_std > 0 else 0
    icir = ic_mean / (ic_std / np.sqrt(len(ic_values))) if ic_std > 0 else 0
    return {'ic_mean': ic_mean, 'ic_std': ic_std, 'ir': ir, 'icir': icir, 'n': len(ic_values)}

async def main():
    await init_db()
    sf = get_session_factory()

    print('=' * 70)
    print(f'V5.0 二期赛道独立验证报告 - {date.today()}')
    print('=' * 70)

    # 1. 更新 track_index_code
    print('\n## 1. 更新 track_index_code')
    async with sf() as s:
        updated = 0
        for fund_code, (track_code, track_name) in TRACK_INDEX_MAP.items():
            r = await s.execute(text(
                'UPDATE position_rating_fund_map SET track_index_code=:tc '
                'WHERE fund_code=:fc AND status!="invalid"'
            ), {'tc': track_code, 'fc': fund_code})
            updated += r.rowcount
        await s.commit()
        print(f'  已更新 {updated} 条记录的 track_index_code')

    # 2. 获取价格数据 + 计算因子
    print('\n## 2. 获取主题指数价格数据 + 计算因子')
    unique_indices = {}
    for fc, (tc, tn) in TRACK_INDEX_MAP.items():
        if tc not in unique_indices:
            unique_indices[tc] = tn
    print(f'  唯一主题指数: {len(unique_indices)} 个')

    all_factor_data = {}
    for track_code, track_name in unique_indices.items():
        print(f'  获取 {track_code} {track_name}...', end=' ')
        prices = fetch_index_prices(track_code)
        if not prices:
            print('FAIL')
            continue
        latest_factors = compute_factors_from_prices(prices)
        ts = compute_factors_timeseries(prices)
        all_factor_data[track_code] = {
            'name': track_name,
            'latest': latest_factors,
            'timeseries': ts,
            'n_prices': len(prices),
        }
        print(f'OK {len(prices)}d, {len(ts)}ts')

    # 3. IC/IR验证
    print('\n## 3. 因子IC/IR验证 (|IR| > 0.1 = valid)')
    factor_ir_results = {}
    for fn in ['TURN', 'VOL', 'NHNL', 'RSI']:
        all_ics = []
        for tc, data in all_factor_data.items():
            result = calc_ic_ir(data['timeseries'], fn)
            if result:
                all_ics.append(result)
        if all_ics:
            avg_ic = np.mean([r['ic_mean'] for r in all_ics])
            avg_ir = np.mean([r['ir'] for r in all_ics])
            avg_icir = np.mean([r['icir'] for r in all_ics])
            total_n = sum(r['n'] for r in all_ics)
            factor_ir_results[fn] = {'ir': avg_ir, 'ic': avg_ic, 'icir': avg_icir}
            status = 'PASS' if abs(avg_ir) > 0.1 else 'WARN'
            print(f'  [{status}] {fn}: IC={avg_ic:.4f}, IR={avg_ir:.4f}, ICIR={avg_icir:.4f}, n_tracks={len(all_ics)}, n_obs={total_n}')
        else:
            factor_ir_results[fn] = None
            print(f'  [WARN] {fn}: insufficient data')
    print(f'  [INFO] DIV: cross-track divergence, calculated separately')

    # 4. factor_history回填
    print('\n## 4. factor_history回填')
    all_dates = set()
    for tc, data in all_factor_data.items():
        for item in data['timeseries']:
            all_dates.add(item['date'])
    all_dates = sorted(all_dates)

    # DIV: 每日跨赛道composite std
    div_by_date = {}
    for d in all_dates:
        scores = []
        for tc, data in all_factor_data.items():
            for item in data['timeseries']:
                if item['date'] == d:
                    vol = item.get('VOL', 0.5)
                    rsi = item.get('RSI', 50)
                    nhnl = item.get('NHNL', 0)
                    turn = item.get('TURN', 1)
                    vol_s = max(0, min(100, (vol - 0.1) / 0.3 * 100))
                    rsi_s = rsi
                    nhnl_s = 50 + nhnl * 50
                    turn_s = max(0, min(100, (turn - 0.5) / 1.5 * 100))
                    comp = vol_s * 0.25 + rsi_s * 0.15 + nhnl_s * 0.20 + turn_s * 0.28
                    scores.append(comp)
                    break
        if len(scores) >= 3:
            div_by_date[d] = float(np.std(scores))

    inserted = 0
    async with sf() as s:
        for track_code, data in all_factor_data.items():
            ts = data['timeseries']
            for item in ts:
                td = item['date']
                for fn in ['TURN', 'VOL', 'NHNL', 'RSI']:
                    raw_val = item.get(fn)
                    if raw_val is None:
                        continue
                    exists = await s.execute(text(
                        'SELECT COUNT(*) FROM factor_history WHERE factor_name=:fn '
                        'AND index_code=:ic AND trade_date=:td'
                    ), {'fn': fn, 'ic': track_code, 'td': td})
                    if exists.fetchone()[0] > 0:
                        continue
                    await s.execute(text(
                        'INSERT INTO factor_history (factor_name, index_code, trade_date, raw_value, quantile_percentile) '
                        'VALUES (:fn, :ic, :td, :rv, :qp)'
                    ), {'fn': fn, 'ic': track_code, 'td': td, 'rv': float(raw_val), 'qp': 50})
                    inserted += 1
            # DIV
            for d, div_val in div_by_date.items():
                exists = await s.execute(text(
                    'SELECT COUNT(*) FROM factor_history WHERE factor_name="DIV" '
                    'AND index_code=:ic AND trade_date=:td'
                ), {'ic': track_code, 'td': d})
                if exists.fetchone()[0] > 0:
                    continue
                await s.execute(text(
                    'INSERT INTO factor_history (factor_name, index_code, trade_date, raw_value, quantile_percentile) '
                    'VALUES ("DIV", :ic, :td, :rv, :qp)'
                ), {'ic': track_code, 'td': d, 'rv': div_val, 'qp': 50})
                inserted += 1
        await s.commit()
    print(f'  已插入 {inserted} 条因子记录到 factor_history')

    # 5. 信号边界分布检查
    print('\n## 5. 信号边界分布检查')
    for track_code, data in all_factor_data.items():
        lf = data['latest']
        if not lf:
            continue
        vol_s = max(0, min(100, (lf.get('VOL', 0.2) - 0.1) / 0.3 * 100))
        rsi_s = lf.get('RSI', 50)
        nhnl_s = 50 + lf.get('NHNL', 0) * 50
        turn_s = max(0, min(100, (lf.get('TURN', 1) - 0.5) / 1.5 * 100))
        comp = vol_s * 0.25 + rsi_s * 0.15 + nhnl_s * 0.20 + turn_s * 0.28
        if comp < 36: sig = 'S+'
        elif comp < 40: sig = 'S'
        elif comp < 45: sig = 'A'
        elif comp < 55: sig = 'B'
        elif comp < 58: sig = 'C'
        elif comp < 62: sig = 'D'
        else: sig = 'E'
        print(f'  {data["name"]}({track_code}): score={comp:.1f} -> {sig} | VOL={lf.get("VOL",0):.3f} RSI={lf.get("RSI",0):.1f} NHNL={lf.get("NHNL",0):.0f} TURN={lf.get("TURN",0):.2f}')

    # 6. 对比
    print('\n## 6. 二期 vs 一期因子IR对比')
    print('  一期(申万一级): NHNL IR=-0.61, RSI IR=-0.12, TURN IR=-0.09, VOL IR=0.005')
    print('  二期(主题指数):')
    for fn in ['TURN', 'VOL', 'NHNL', 'RSI']:
        r = factor_ir_results.get(fn)
        if r:
            print(f'    {fn}: IR={r["ir"]:.4f}')

    # 7. 总结
    print('\n' + '=' * 70)
    print('## 总结')
    print(f'  主题指数数: {len(all_factor_data)}')
    print(f'  factor_history回填: {inserted} 条')
    valid_ir = sum(1 for r in factor_ir_results.values() if r and abs(r['ir']) > 0.1)
    print(f'  有效因子(|IR|>0.1): {valid_ir}/4')

    await close_db()

if __name__ == '__main__':
    asyncio.run(main())
