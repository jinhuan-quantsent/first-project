#!/usr/bin/env python3
"""
Gate触发频率验证脚本 (T-G2)
统计252天×31板块中各Gate的触发次数和分布

Gate定义（V5.0重构版）:
  Gate1: 阶段回撤≥20%（60日窗口max→current）→ 极端情况才触发
  Gate2: 跌破MA20 + 回撤≥10% → 趋势破位离场闸（contrarian轨道豁免）
  Gate-E: 情绪信号=E级 → 极度贪婪止盈

MA20趋势逻辑完全复刻 trend_guard.py 的 _calculate_ma20_trend：
  - 20日均线
  - 震荡市过滤（振幅≤5% / 交叉次数≥3 / 斜率≤0.003 三维度，≥2维则判震荡）
  - 非震荡时：close>MA20+短趋势>0→上升, close<MA20+短趋势<0→下降
"""
import sys
import os
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
warnings.filterwarnings('ignore')

# ============================================================
# Database helper
# ============================================================
def get_db_conn():
    import pymysql
    return pymysql.connect(
        host='rm-bp1iqpeh04issog45uo.mysql.rds.aliyuncs.com',
        port=3306, user='Jin0220', password='Jinhuan0220',
        db='fund_sentiment', charset='utf8mb4',
    )


# ============================================================
# SW industry names (31 sectors)
# ============================================================
SW_SECTOR_NAMES = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}


# ============================================================
# Load backtest results (sentiment signals)
# ============================================================
def load_backtest_results():
    csv_path = os.path.join(os.path.dirname(__file__), 'sector_backtest_results.csv')
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
    df['sector_code'] = df['sector_code'].astype(str).str.strip()
    df['trade_date'] = df['trade_date'].astype(str).str.strip()
    print(f"  回测结果: {len(df)} 条, {df['sector_code'].nunique()} 板块, "
          f"{df['trade_date'].nunique()} 交易日")
    print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    print(f"  信号分布: {dict(df['signal'].value_counts())}")
    return df


# ============================================================
# Load sector prices from MySQL
# ============================================================
def load_sector_prices():
    conn = get_db_conn()
    query = """
        SELECT sector_code, sector_name, trade_date,
               open, high, low, close, volume, amount, pct_change
        FROM sector_price
        ORDER BY sector_code, trade_date
    """
    df = pd.read_sql(query, conn)
    conn.close()
    df['sector_code'] = df['sector_code'].astype(str).str.strip()
    df['trade_date'] = df['trade_date'].astype(str).str.strip()
    print(f"  价格数据: {len(df)} 条, {df['sector_code'].nunique()} 板块")
    print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    return df


# ============================================================
# MA20 trend calculation (replicating trend_guard._calculate_ma20_trend)
# ============================================================
OSCILLATION_AMPLITUDE_MAX = 0.05
OSCILLATION_CROSSING_MIN = 3
OSCILLATION_SLOPE_MAX = 0.003


def calculate_ma20_trend_rolling(prices):
    """
    对价格序列逐日计算MA20趋势。
    完全复刻 trend_guard.py 的 _calculate_ma20_trend 逻辑。
    需要≥20日数据，返回 list[str]: "上升"/"下降"/"震荡"
    """
    n = len(prices)
    trends = ["震荡"] * n

    for i in range(n):
        if i < 19:
            continue

        window = np.array(prices[i - 19:i + 1], dtype=float)  # 20 prices
        ma20 = np.mean(window)
        current_price = window[-1]

        if ma20 <= 0:
            continue

        # short_trend: 5-day return
        short_trend = (window[-1] - window[-5]) / window[-5] if window[-5] > 0 else 0.0

        # amplitude over 20-day window
        max_p = np.max(window)
        min_p = np.min(window)
        amplitude = (max_p - min_p) / min_p if min_p > 0 else 0.0

        # crossings: price crossing MA20 line
        crossings = 0
        for j in range(1, len(window)):
            if (window[j - 1] <= ma20 < window[j]) or \
               (window[j - 1] >= ma20 > window[j]):
                crossings += 1

        # ma20_slope: 10-day normalized
        ma20_slope = (window[-1] - window[-10]) / window[-10] / 10 if window[-10] > 0 else 0.0

        # oscillation check (3 dimensions, ≥2 → 震荡)
        dim1 = amplitude <= OSCILLATION_AMPLITUDE_MAX
        dim2 = crossings >= OSCILLATION_CROSSING_MIN
        dim3 = abs(ma20_slope) <= OSCILLATION_SLOPE_MAX
        osc_score = int(dim1) + int(dim2) + int(dim3)

        if osc_score >= 2:
            trends[i] = "震荡"
        else:
            if current_price > ma20 and short_trend > 0:
                trends[i] = "上升"
            elif current_price < ma20 and short_trend < 0:
                trends[i] = "下降"
            else:
                trends[i] = "下降" if current_price < ma20 else "上升"

    return trends


# ============================================================
# Drawdown calculation (60-day window max→current)
# ============================================================
def calculate_drawdown_rolling(prices, window=60):
    """
    逐日计算回撤: (max(prices[-60:]) - current) / max(prices[-60:])
    与 trend_guard.py Gate2 回撤逻辑一致。
    """
    n = len(prices)
    drawdowns = np.zeros(n)

    for i in range(n):
        start = max(0, i - window + 1)
        w = prices[start:i + 1]
        max_p = np.max(w)
        if max_p > 0:
            drawdowns[i] = (max_p - prices[i]) / max_p
        else:
            drawdowns[i] = 0.0

    return drawdowns


# ============================================================
# Assign tracks (same logic as sector_backtest_with_prices.py)
# ============================================================
def assign_track(row):
    signal = row['signal']
    stars = row['stars']
    fc = row['factor_completeness']
    trend = row.get('trend', '震荡')

    if fc < 0.90:
        return 'excluded'
    if signal == 'S+' and stars >= 3:
        return 'contrarian'
    if signal == 'S' and stars >= 2:
        return 'contrarian'
    if signal in ['A', 'B', 'C'] and trend == '上升' and stars >= 2:
        return 'trend_follow'
    return 'excluded'


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 70)
    print("Gate触发频率验证 (T-G2)")
    print("=" * 70)

    # 1. Load signals
    print("\n[1/5] 加载回测信号数据...")
    signals_df = load_backtest_results()

    # 2. Load prices
    print("\n[2/5] 加载价格数据...")
    prices_df = load_sector_prices()

    # 3. Compute MA20 trend + drawdown for each sector
    print("\n[3/5] 计算MA20趋势 + 60日回撤...")
    feat_list = []
    for scode, group in prices_df.groupby('sector_code'):
        group = group.sort_values('trade_date').reset_index(drop=True)
        prices = group['close'].values.astype(float)

        group['ma20'] = group['close'].rolling(window=20, min_periods=20).mean()
        group['trend'] = calculate_ma20_trend_rolling(prices)
        group['drawdown'] = calculate_drawdown_rolling(prices, 60)
        group['below_ma20'] = group['close'] < group['ma20']

        feat_list.append(group)

    price_features = pd.concat(feat_list, ignore_index=True)
    print(f"  特征计算完成: {len(price_features)} 条")

    # 4. Merge signals with price features
    print("\n[4/5] 合并信号与价格特征...")
    merged = signals_df.merge(
        price_features[['sector_code', 'trade_date', 'close', 'ma20',
                        'trend', 'drawdown', 'below_ma20']],
        on=['sector_code', 'trade_date'],
        how='inner'
    )
    merged['track_v2'] = merged.apply(assign_track, axis=1)
    print(f"  合并后: {len(merged)} 条 (signals={len(signals_df)}, matched={len(merged)})")

    # 5. Compute Gate triggers
    print("\n[5/5] 统计Gate触发...")

    # Gate1: 阶段回撤≥20%
    merged['gate1'] = merged['drawdown'] >= 0.20

    # Gate2 (trend=下降): MA20趋势下降 + 回撤≥10%
    merged['gate2_down'] = (merged['trend'] == '下降') & (merged['drawdown'] >= 0.10)
    merged['gate2_down_excl'] = merged['gate2_down'] & (merged['track_v2'] != 'contrarian')

    # Gate2 (close<MA20): 收盘价跌破MA20 + 回撤≥10%  (字面定义对照)
    merged['gate2_below'] = merged['below_ma20'] & (merged['drawdown'] >= 0.10)
    merged['gate2_below_excl'] = merged['gate2_below'] & (merged['track_v2'] != 'contrarian')

    # Gate-E: signal == E
    merged['gate_e'] = merged['signal'] == 'E'

    # ── Summary statistics ──────────────────────────────
    n_dates = merged['trade_date'].nunique()
    n_sectors = merged['sector_code'].nunique()
    n_rows = len(merged)
    years = n_dates / 252.0

    print(f"\n{'=' * 70}")
    print(f"数据覆盖: {n_dates} 交易日 × {n_sectors} 板块 = {n_rows} 条")
    print(f"时间跨度: {merged['trade_date'].min()} ~ {merged['trade_date'].max()}")
    print(f"折合 {years:.2f} 年 (252交易日/年)")
    print(f"{'=' * 70}")

    # ── Overall trigger counts ──────────────────────────
    gates = {
        'Gate1 (回撤≥20%)': 'gate1',
        'Gate2-趋势下降 (含contrarian)': 'gate2_down',
        'Gate2-趋势下降 (排除contrarian)': 'gate2_down_excl',
        'Gate2-跌破MA20 (含contrarian)': 'gate2_below',
        'Gate2-跌破MA20 (排除contrarian)': 'gate2_below_excl',
        'Gate-E (signal=E)': 'gate_e',
    }

    print(f"\n--- 1. 总触发次数 ---")
    print(f"{'Gate':<40s} {'触发次数':>8s} {'占比':>8s} {'每板块/年':>10s}")
    print(f"{'-' * 40} {'-' * 8} {'-' * 8} {'-' * 10}")
    gate_totals = {}
    for label, col in gates.items():
        count = int(merged[col].sum())
        pct = count / n_rows * 100 if n_rows > 0 else 0
        per_sector_year = count / n_sectors / years if years > 0 else 0
        gate_totals[label] = count
        print(f"{label:<40s} {count:>8d} {pct:>7.1f}% {per_sector_year:>10.1f}")

    # ── Per-sector breakdown ────────────────────────────
    print(f"\n--- 2. 按板块统计 ---")

    sector_stats = []
    for scode, group in merged.groupby('sector_code'):
        sname = SW_SECTOR_NAMES.get(scode, scode)
        sector_stats.append({
            'sector_code': scode,
            'sector_name': sname,
            'gate1': int(group['gate1'].sum()),
            'gate2_down': int(group['gate2_down'].sum()),
            'gate2_down_excl': int(group['gate2_down_excl'].sum()),
            'gate2_below': int(group['gate2_below'].sum()),
            'gate2_below_excl': int(group['gate2_below_excl'].sum()),
            'gate_e': int(group['gate_e'].sum()),
            'contrarian_days': int((group['track_v2'] == 'contrarian').sum()),
            'n_days': len(group),
        })
    sector_df = pd.DataFrame(sector_stats)

    # Per-sector per-year
    for col in ['gate1', 'gate2_down_excl', 'gate2_below_excl', 'gate_e']:
        sector_df[col + '_py'] = sector_df[col] / years

    print(f"\n  Gate2-趋势下降(排除contrarian) 每板块每年触发次数:")
    print(f"  {'板块':<12s} {'触发':>4s} {'次/年':>6s}  {'板块':<12s} {'触发':>4s} {'次/年':>6s}")
    print(f"  {'-' * 12} {'-' * 4} {'-' * 6}  {'-' * 12} {'-' * 4} {'-' * 6}")
    sorted_df = sector_df.sort_values('gate2_down_excl', ascending=False).reset_index(drop=True)
    half = (len(sorted_df) + 1) // 2
    for i in range(half):
        left = sorted_df.iloc[i]
        line = f"  {left['sector_name']:<12s} {left['gate2_down_excl']:>4d} {left['gate2_down_excl_py']:>6.1f}"
        if i + half < len(sorted_df):
            right = sorted_df.iloc[i + half]
            line += f"  {right['sector_name']:<12s} {right['gate2_down_excl']:>4d} {right['gate2_down_excl_py']:>6.1f}"
        print(line)

    # ── Top 5 / Bottom 5 ────────────────────────────────
    print(f"\n--- 3. Gate2(趋势下降,排除contrarian) 触发最多/最少 ---")
    print(f"  Top 5 (触发最多):")
    for _, row in sorted_df.head(5).iterrows():
        print(f"    {row['sector_name']}({row['sector_code']})  "
              f"Gate2={row['gate2_down_excl']}次  ({row['gate2_down_excl_py']:.1f}/年)  "
              f"Gate1={row['gate1']}  Gate-E={row['gate_e']}  contrarian天={row['contrarian_days']}")
    print(f"  Bottom 5 (触发最少):")
    for _, row in sorted_df.tail(5).iterrows():
        print(f"    {row['sector_name']}({row['sector_code']})  "
              f"Gate2={row['gate2_down_excl']}次  ({row['gate2_down_excl_py']:.1f}/年)  "
              f"Gate1={row['gate1']}  Gate-E={row['gate_e']}  contrarian天={row['contrarian_days']}")

    # ── Gate2 distribution histogram ────────────────────
    print(f"\n--- 4. Gate2(趋势下降,排除contrarian) 分布直方图 ---")
    vals = sector_df['gate2_down_excl_py'].values
    bins = [0, 5, 10, 15, 20, 25, 30, 40, 50, 999]
    labels = ['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-40', '40-50', '50+']
    for lo, hi, lab in zip(bins[:-1], bins[1:], labels):
        cnt = int(np.sum((vals >= lo) & (vals < hi)))
        bar = '#' * cnt
        print(f"  {lab:>6s} 次/年: {cnt:>2d} 板块 {bar}")

    # ── Contrarian exemption analysis ───────────────────
    print(f"\n--- 5. Contrarian轨道Gate2豁免情况 ---")
    contrarian_sectors = sector_df[sector_df['contrarian_days'] > 0].sort_values('contrarian_days', ascending=False)
    if len(contrarian_sectors) > 0:
        print(f"  有contrarian信号的板块: {len(contrarian_sectors)} 个")
        print(f"  {'板块':<12s} {'contrarian天':>12s} {'Gate2含':>8s} {'Gate2排':>8s} {'豁免':>6s}")
        print(f"  {'-' * 12} {'-' * 12} {'-' * 8} {'-' * 8} {'-' * 6}")
        total_with = 0
        total_excl = 0
        for _, row in contrarian_sectors.iterrows():
            exempt = row['gate2_down'] - row['gate2_down_excl']
            total_with += row['gate2_down']
            total_excl += row['gate2_down_excl']
            print(f"  {row['sector_name']:<12s} {row['contrarian_days']:>12d} "
                  f"{row['gate2_down']:>8d} {row['gate2_down_excl']:>8d} {exempt:>6d}")
        print(f"  {'合计':<12s} {'':>12s} {total_with:>8d} {total_excl:>8d} {total_with - total_excl:>6d}")
        print(f"  豁免率: {(total_with - total_excl) / total_with * 100:.1f}%" if total_with > 0 else "  豁免率: N/A")
    else:
        print(f"  无板块有contrarian信号")

    # ── Trend distribution ──────────────────────────────
    print(f"\n--- 6. MA20趋势分布 ---")
    trend_counts = merged['trend'].value_counts()
    for t, c in trend_counts.items():
        print(f"  {t}: {c} ({c / n_rows * 100:.1f}%)")

    # ── Drawdown distribution ───────────────────────────
    print(f"\n--- 7. 回撤分布 ---")
    dd = merged['drawdown']
    print(f"  平均回撤: {dd.mean():.1%}")
    print(f"  中位回撤: {dd.median():.1%}")
    print(f"  最大回撤: {dd.max():.1%}")
    print(f"  回撤≥10%: {(dd >= 0.10).sum()} ({(dd >= 0.10).sum() / n_rows * 100:.1f}%)")
    print(f"  回撤≥15%: {(dd >= 0.15).sum()} ({(dd >= 0.15).sum() / n_rows * 100:.1f}%)")
    print(f"  回撤≥20%: {(dd >= 0.20).sum()} ({(dd >= 0.20).sum() / n_rows * 100:.1f}%)")

    # ── Judgment ────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"--- 8. 判定结论 ---")
    print(f"{'=' * 70}")

    g1_py = gate_totals['Gate1 (回撤≥20%)'] / n_sectors / years
    g2_down_py = gate_totals['Gate2-趋势下降 (排除contrarian)'] / n_sectors / years
    g2_below_py = gate_totals['Gate2-跌破MA20 (排除contrarian)'] / n_sectors / years
    ge_py = gate_totals['Gate-E (signal=E)'] / n_sectors / years

    print(f"\n  Gate1 (回撤≥20%):")
    print(f"    每板块每年 {g1_py:.1f} 次", end="")
    if g1_py <= 3:
        print(f" → ✅ 正常 (极端情况才触发)")
    else:
        print(f" → ⚠️ 偏多 (预期0-3次)")

    print(f"\n  Gate2-趋势下降 (排除contrarian):")
    print(f"    每板块每年 {g2_down_py:.1f} 次", end="")
    if g2_down_py > 30:
        print(f" → ⚠️ 过频！需要加过滤条件")
    elif g2_down_py >= 10:
        print(f" → ✅ 合理 (10-20次区间)")
    elif g2_down_py >= 5:
        print(f" → ✅ 可接受 (5-10次区间)")
    else:
        print(f" → ⚠️ 过于宽松，可能漏掉该止损的场景")

    print(f"\n  Gate2-跌破MA20 (排除contrarian) [字面定义对照]:")
    print(f"    每板块每年 {g2_below_py:.1f} 次", end="")
    if g2_below_py > 30:
        print(f" → ⚠️ 过频！")
    elif g2_below_py >= 10:
        print(f" → ✅ 合理")
    elif g2_below_py >= 5:
        print(f" → ✅ 可接受")
    else:
        print(f" → ⚠️ 过于宽松")

    print(f"\n  Gate-E (signal=E):")
    print(f"    每板块每年 {ge_py:.1f} 次")
    print(f"    总计 {gate_totals['Gate-E (signal=E)']} 次 / {n_rows} 条 = "
          f"{gate_totals['Gate-E (signal=E)'] / n_rows * 100:.1f}%")

    # ── Recommendation ──────────────────────────────────
    print(f"\n--- 9. 参数调整建议 ---")
    if g2_down_py > 30:
        print(f"  ⚠️ Gate2(趋势下降)过频 ({g2_down_py:.1f}次/年)，建议:")
        print(f"     - 提高回撤阈值: 5% → 7% 或 8%")
        print(f"     - 增加确认条件: 连续2日跌破MA20")
        print(f"     - 缩小回撤窗口: 60日 → 40日")
        # Simulate with higher thresholds
        for new_th in [0.07, 0.08, 0.10]:
            cnt = int(((merged['trend'] == '下降') & (merged['drawdown'] >= new_th) &
                       (merged['track_v2'] != 'contrarian')).sum())
            py = cnt / n_sectors / years
            print(f"     - 回撤阈值={new_th:.0%}: {py:.1f}次/年 (触发{cnt}次)")
    elif g2_down_py < 5:
        print(f"  ⚠️ Gate2(趋势下降)偏少 ({g2_down_py:.1f}次/年)，建议:")
        print(f"     - 降低回撤阈值: 5% → 3%")
        for new_th in [0.03, 0.04]:
            cnt = int(((merged['trend'] == '下降') & (merged['drawdown'] >= new_th) &
                       (merged['track_v2'] != 'contrarian')).sum())
            py = cnt / n_sectors / years
            print(f"     - 回撤阈值={new_th:.0%}: {py:.1f}次/年 (触发{cnt}次)")
    else:
        print(f"  ✅ Gate2(趋势下降)频率合理 ({g2_down_py:.1f}次/年)，5%回撤阈值合适")

    if g2_below_py > 30:
        print(f"  ⚠️ Gate2(跌破MA20字面)过频 ({g2_below_py:.1f}次/年)")
        print(f"     → 建议使用趋势下降版本(含震荡过滤)，而非纯close<MA20")

    print(f"\n{'=' * 70}")
    print(f"验证完成")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
