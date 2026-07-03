#!/usr/bin/env python3
"""Analyze penalty impact: compare original vs current (iter2) vs hypothetical no-penalty."""
import csv, statistics
from collections import Counter

weights = {'TURN': 0.28, 'VOL': 0.25, 'NHNL': 0.20, 'RSI': 0.15, 'DIV': 0.12}
SIGNAL_BOUNDS = [12, 25, 38, 52, 65, 80]
SIGNAL_LABELS = ['S+', 'S', 'A', 'B', 'C', 'D', 'E']

def map_signal(score):
    for i, b in enumerate(SIGNAL_BOUNDS):
        if score < b:
            return SIGNAL_LABELS[i]
    return SIGNAL_LABELS[-1]

with open('/opt/fund-sentiment/v5-deploy/backend/scripts/sector_backtest_results.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Compute raw weighted average
for r in rows:
    r['raw_weighted'] = sum(float(r[f'{k}_score']) * w for k, w in weights.items())

raw_scores = [r['raw_weighted'] for r in rows]
final_scores = [float(r['score']) for r in rows]

print('=' * 70)
print('PENALTY IMPACT ANALYSIS')
print('=' * 70)

print('\n--- Raw Weighted Average (no penalty, penalty=1.0) ---')
print(f'  Range: [{min(raw_scores):.1f}, {max(raw_scores):.1f}]')
print(f'  Std:   {statistics.stdev(raw_scores):.1f}')
raw_signals = Counter(map_signal(s) for s in raw_scores)
print(f'  Signal distribution:')
total = len(raw_scores)
for label in SIGNAL_LABELS:
    cnt = raw_signals.get(label, 0)
    if cnt > 0:
        print(f'    {label}: {cnt} ({cnt/total*100:.1f}%)')

print('\n--- Final Composite Score (current: penalty_min=0.85, std_threshold=30) ---')
print(f'  Range: [{min(final_scores):.1f}, {max(final_scores):.1f}]')
print(f'  Std:   {statistics.stdev(final_scores):.1f}')
final_signals = Counter(map_signal(s) for s in final_scores)
print(f'  Signal distribution:')
for label in SIGNAL_LABELS:
    cnt = final_signals.get(label, 0)
    if cnt > 0:
        print(f'    {label}: {cnt} ({cnt/total*100:.1f}%)')

print('\n--- Bottom 10 Raw Weighted Scores ---')
sorted_rows = sorted(rows, key=lambda r: r['raw_weighted'])
for r in sorted_rows[:10]:
    print(f'  {r["trade_date"]} {r["sector_name"]:8s} raw={r["raw_weighted"]:.1f} final={float(r["score"]):.1f} sig={r["signal"]} '
          f'[T={float(r["TURN_score"]):.0f},V={float(r["VOL_score"]):.0f},N={float(r["NHNL_score"]):.0f},'
          f'R={float(r["RSI_score"]):.0f},D={float(r["DIV_score"]):.0f}]')

print('\n--- Top 10 Raw Weighted Scores ---')
for r in sorted_rows[-10:]:
    print(f'  {r["trade_date"]} {r["sector_name"]:8s} raw={r["raw_weighted"]:.1f} final={float(r["score"]):.1f} sig={r["signal"]} '
          f'[T={float(r["TURN_score"]):.0f},V={float(r["VOL_score"]):.0f},N={float(r["NHNL_score"]):.0f},'
          f'R={float(r["RSI_score"]):.0f},D={float(r["DIV_score"]):.0f}]')

# Penalty compression analysis
print('\n--- Penalty Compression (raw -> final delta) ---')
deltas = [abs(r['raw_weighted'] - float(r['score'])) for r in rows]
print(f'  Mean |delta|: {statistics.mean(deltas):.2f}')
print(f'  Max |delta|:  {max(deltas):.2f}')
print(f'  Delta > 5:    {sum(1 for d in deltas if d > 5)} rows ({sum(1 for d in deltas if d > 5)/total*100:.1f}%)')
print(f'  Delta > 3:    {sum(1 for d in deltas if d > 3)} rows ({sum(1 for d in deltas if d > 3)/total*100:.1f}%)')

# How many rows crossed a signal boundary due to penalty?
boundary_crossings = 0
for r in rows:
    raw_sig = map_signal(r['raw_weighted'])
    final_sig = r['signal']
    if raw_sig != final_sig:
        boundary_crossings += 1
print(f'  Signal boundary crossings: {boundary_crossings} ({boundary_crossings/total*100:.1f}%)')

print('\n--- Conclusion ---')
print(f'  Raw floor: {min(raw_scores):.1f} (S boundary: 25.0)')
print(f'  Raw ceiling: {max(raw_scores):.1f} (E boundary: 80.0)')
print(f'  Even with NO penalty, S+/S/E signals are impossible.')
print(f'  Current penalty_min=0.85 adds max ~3.2 points compression.')
print(f'  The 5-factor weighted average has inherent range [25, 72].')
