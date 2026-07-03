#!/usr/bin/env python3
"""Gate阈值敏感度分析 (T-G2 补充)"""
import sys, os, pymysql
import pandas as pd, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
from gate_frequency_test import calculate_ma20_trend_rolling, calculate_drawdown_rolling, assign_track

df_sig = pd.read_csv(os.path.join(os.path.dirname(__file__), 'sector_backtest_results.csv'), encoding='utf-8-sig')
df_sig.columns = [c.strip().replace('\ufeff','') for c in df_sig.columns]
df_sig['sector_code'] = df_sig['sector_code'].astype(str).str.strip()
df_sig['trade_date'] = df_sig['trade_date'].astype(str).str.strip()

conn = pymysql.connect(host='rm-bp1iqpeh04issog45uo.mysql.rds.aliyuncs.com', port=3306, user='Jin0220', password='Jinhuan0220', db='fund_sentiment', charset='utf8mb4')
df_p = pd.read_sql('SELECT sector_code, trade_date, close FROM sector_price ORDER BY sector_code, trade_date', conn)
conn.close()
df_p['sector_code'] = df_p['sector_code'].astype(str).str.strip()
df_p['trade_date'] = df_p['trade_date'].astype(str).str.strip()

feat_list = []
for scode, group in df_p.groupby('sector_code'):
    group = group.sort_values('trade_date').reset_index(drop=True)
    prices = group['close'].values.astype(float)
    group['ma20'] = group['close'].rolling(20, min_periods=20).mean()
    group['trend'] = calculate_ma20_trend_rolling(prices)
    group['drawdown'] = calculate_drawdown_rolling(prices, 60)
    group['below_ma20'] = group['close'] < group['ma20']
    feat_list.append(group)
feats = pd.concat(feat_list, ignore_index=True)

merged = df_sig.merge(feats[['sector_code','trade_date','close','ma20','trend','drawdown','below_ma20']], on=['sector_code','trade_date'], how='inner')
merged['track_v2'] = merged.apply(assign_track, axis=1)
merged = merged.sort_values(['sector_code','trade_date']).reset_index(drop=True)

n_sectors = 31
years = 1.0

print('=' * 60)
print('Gate2 阈值敏感度 (趋势下降 + 排除contrarian)')
print('=' * 60)
print(f'{"回撤阈值":>8s} {"触发次数":>8s} {"每板块/年":>10s} {"判定":>10s}')
print(f'{"-"*8} {"-"*8} {"-"*10} {"-"*10}')
for th in [0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.15, 0.20, 0.25, 0.30]:
    cnt = int(((merged['trend']=='下降') & (merged['drawdown']>=th) & (merged['track_v2']!='contrarian')).sum())
    py = cnt / n_sectors / years
    if py > 30: verdict = '过频'
    elif py >= 10: verdict = '合理'
    elif py >= 5: verdict = '可接受'
    else: verdict = '偏少'
    print(f'{th:>7.0%} {cnt:>8d} {py:>10.1f} {verdict:>10s}')

print()
print('=' * 60)
print('Gate1 阈值敏感度 (回撤>=阈值, 所有板块)')
print('=' * 60)
print(f'{"回撤阈值":>8s} {"触发次数":>8s} {"每板块/年":>10s} {"判定":>10s}')
print(f'{"-"*8} {"-"*8} {"-"*10} {"-"*10}')
for th in [0.18, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35]:
    cnt = int((merged['drawdown']>=th).sum())
    py = cnt / n_sectors / years
    if py <= 3: verdict = '正常'
    elif py <= 5: verdict = '可接受'
    else: verdict = '偏多'
    print(f'{th:>7.0%} {cnt:>8d} {py:>10.1f} {verdict:>10s}')

print()
print('=' * 60)
print('Gate2 连续2日确认 (趋势下降 + 回撤>=阈值 + 前一日也触发)')
print('=' * 60)
for th in [0.08, 0.10, 0.12, 0.15]:
    triggered = (merged['trend']=='下降') & (merged['drawdown']>=th) & (merged['track_v2']!='contrarian')
    prev_triggered = triggered.groupby(merged['sector_code']).shift(1).fillna(False)
    confirmed = triggered & prev_triggered
    cnt = int(confirmed.sum())
    py = cnt / n_sectors / years
    print(f'  回撤>={th:.0%} + 连续2日确认: {cnt}次, {py:.1f}/年')

print()
print('=' * 60)
print('Gate2 不同回撤窗口 x 10%阈值 (趋势下降 + 排除contrarian)')
print('=' * 60)
for win in [20, 40, 60, 90]:
    feat_list2 = []
    for scode, group in df_p.groupby('sector_code'):
        group = group.sort_values('trade_date').reset_index(drop=True)
        prices = group['close'].values.astype(float)
        group['dd_win'] = calculate_drawdown_rolling(prices, win)
        feat_list2.append(group[['sector_code','trade_date','dd_win']])
    dd_df = pd.concat(feat_list2, ignore_index=True)
    merged2 = merged.merge(dd_df, on=['sector_code','trade_date'], how='left')
    cnt = int(((merged2['trend']=='下降') & (merged2['dd_win']>=0.10) & (merged2['track_v2']!='contrarian')).sum())
    py = cnt / n_sectors / years
    print(f'  窗口{win}日 + 回撤>=10%: {cnt}次, {py:.1f}/年')

print()
print('=' * 60)
print('Gate2 组合方案: 连续2日确认 + 不同阈值/窗口')
print('=' * 60)
# Test: 8% threshold + 2-day confirmation + 40-day window
for win in [40, 60]:
    for th in [0.08, 0.10, 0.12]:
        feat_list2 = []
        for scode, group in df_p.groupby('sector_code'):
            group = group.sort_values('trade_date').reset_index(drop=True)
            prices = group['close'].values.astype(float)
            group['dd_win'] = calculate_drawdown_rolling(prices, win)
            feat_list2.append(group[['sector_code','trade_date','dd_win']])
        dd_df = pd.concat(feat_list2, ignore_index=True)
        merged2 = merged.merge(dd_df, on=['sector_code','trade_date'], how='left')
        triggered = (merged2['trend']=='下降') & (merged2['dd_win']>=th) & (merged2['track_v2']!='contrarian')
        prev_t = triggered.groupby(merged2['sector_code']).shift(1).fillna(False)
        confirmed = triggered & prev_t
        cnt = int(confirmed.sum())
        py = cnt / n_sectors / years
        verdict = '合理' if 10 <= py <= 20 else ('过频' if py > 20 else '偏少')
        print(f'  窗口{win}日 + 回撤>={th:.0%} + 连续2日: {cnt}次, {py:.1f}/年 [{verdict}]')
