#!/usr/bin/env python3
"""
板块情绪系统 — 价格回测 + 策略验证 (T8)

在 sector_backtest_results.csv (情绪分数+信号) 基础上，
引入 sector_price 表的真实价格数据，执行策略回测。

策略逻辑:
  - 买入: S+/S 信号 → 满仓 (contrarian 逆向买入)
  - 持有: A/B/C 信号 + MA20上升 → 保持持仓 (trend_follow 顺势)
  - 减仓: E 信号 → 减至50% (Gate-E 极度贪婪止盈)
  - 清仓: D 信号 → 清仓 (excluded 贪婪排除)
  - 无信号/空仓: 保持空仓

前视偏差控制: 信号 T 日生成, T+1 日开盘执行
初始资金: 1.0 (归一化)
每日收益 = 前一日仓位 × 当日板块涨跌幅
"""
import sys
import os
import csv
import math
import time
import warnings
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np
import pandas as pd

# Add backend to path
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

SECTOR_CODES = sorted(SW_SECTOR_NAMES.keys())


# ============================================================
# Load backtest results (sentiment signals)
# ============================================================
def load_backtest_results():
    """Load sector_backtest_results.csv into DataFrame"""
    csv_path = os.path.join(os.path.dirname(__file__), 'sector_backtest_results.csv')
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    # Clean: remove BOM if present
    df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
    # Ensure sector_code is string
    df['sector_code'] = df['sector_code'].astype(str).str.strip()
    # Ensure trade_date is string YYYY-MM-DD
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
    """Load sector_price table into DataFrame"""
    conn = get_db_conn()
    query = """
        SELECT sector_code, sector_name, trade_date,
               open, high, low, close, volume, amount, pct_change
        FROM sector_price
        ORDER BY sector_code, trade_date
    """
    df = pd.read_sql(query, conn)
    conn.close()

    # Ensure sector_code is string
    df['sector_code'] = df['sector_code'].astype(str).str.strip()
    # Ensure trade_date is string
    df['trade_date'] = df['trade_date'].astype(str).str.strip()
    # Convert pct_change to decimal (it's in percentage form)
    df['daily_return'] = df['pct_change'] / 100.0

    print(f"  价格数据: {len(df)} 条, {df['sector_code'].nunique()} 板块")
    print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
    return df


# ============================================================
# Compute MA20 trend for each sector
# ============================================================
def compute_ma20_trend(price_df):
    """
    For each sector, compute MA20 and determine trend.
    trend = "上升" if close > MA20, else "下降"/"震荡"

    Returns DataFrame with columns: sector_code, trade_date, close, ma20, trend
    """
    results = []
    for scode, group in price_df.groupby('sector_code'):
        group = group.sort_values('trade_date').reset_index(drop=True)
        group['ma20'] = group['close'].rolling(window=20, min_periods=20).mean()
        # Trend: close above MA20 and MA20 rising
        group['ma20_prev'] = group['ma20'].shift(1)
        group['trend'] = '震荡'
        # 上升: close > MA20 and MA20 rising
        mask_up = (group['close'] > group['ma20']) & (group['ma20'] > group['ma20_prev'])
        # 下降: close < MA20 and MA20 falling
        mask_down = (group['close'] < group['ma20']) & (group['ma20'] < group['ma20_prev'])
        group.loc[mask_up, 'trend'] = '上升'
        group.loc[mask_down, 'trend'] = '下降'
        results.append(group[['sector_code', 'trade_date', 'close', 'ma20', 'trend', 'daily_return']])

    return pd.concat(results, ignore_index=True)


# ============================================================
# Merge signals with prices
# ============================================================
def merge_signals_prices(signals_df, prices_df):
    """
    Merge backtest signals with price data on (sector_code, trade_date).
    Also attach MA20 trend.
    """
    # Compute MA20 trend
    trend_df = compute_ma20_trend(prices_df)

    # Merge signals with trend/price info
    merged = signals_df.merge(
        trend_df[['sector_code', 'trade_date', 'close', 'ma20', 'trend', 'daily_return']],
        on=['sector_code', 'trade_date'],
        how='inner'
    )

    print(f"  合并后: {len(merged)} 条 (signals={len(signals_df)}, matched={len(merged)})")
    if len(merged) < len(signals_df):
        unmatched = len(signals_df) - len(merged)
        print(f"  ⚠ {unmatched} 条信号未匹配到价格数据 (可能日期不对齐)")

    return merged


# ============================================================
# Reassign tracks with price data
# ============================================================
def reassign_tracks(df):
    """
    Reassign tracks using MA20 trend from price data.

    trend_follow: signal in [A,B,C] + trend=="上升" + stars>=2 + factor_completeness>=0.9
    contrarian: signal in [S+,S] + stars>=3(S+)/>=2(S) + factor_completeness>=0.9
    excluded: everything else (including D, E)
    """
    def _get_track(row):
        signal = row['signal']
        stars = row['stars']
        fc = row['factor_completeness']
        trend = row.get('trend', '震荡')

        if fc < 0.90:
            return 'excluded'

        # Contrarian check
        if signal == 'S+' and stars >= 3:
            return 'contrarian'
        if signal == 'S' and stars >= 2:
            return 'contrarian'

        # Trend follow check
        if signal in ['A', 'B', 'C'] and trend == '上升' and stars >= 2:
            return 'trend_follow'

        return 'excluded'

    df['track_v2'] = df.apply(_get_track, axis=1)
    track_counts = df['track_v2'].value_counts()
    print(f"  重新分配轨道: {dict(track_counts)}")
    return df


# ============================================================
# Run price backtest for a single sector
# ============================================================
def backtest_single_sector(sector_df):
    """
    Run price backtest for a single sector.

    Strategy:
    - Buy (position=1.0): contrarian S+/S OR trend_follow A/B/C
    - Hold: A/B/C on excluded track → keep current position
    - Reduce (position=0.5): E signal (Gate-E)
    - Clear (position=0.0): D signal
    - No signal: keep current position

    Signal T day → execute T+1 day (no look-ahead bias)

    Returns dict with daily positions, returns, and metrics.
    """
    sector_df = sector_df.sort_values('trade_date').reset_index(drop=True)
    n = len(sector_df)

    if n < 2:
        return None

    # Arrays for positions and returns
    positions = np.zeros(n)
    daily_returns = np.zeros(n)

    # Get arrays for fast access
    signals = sector_df['signal'].values
    tracks = sector_df['track_v2'].values
    returns = sector_df['daily_return'].values

    # Handle NaN returns
    returns = np.nan_to_num(returns, nan=0.0)

    current_position = 0.0

    for i in range(n):
        # Position was set yesterday, earn today's return
        daily_returns[i] = current_position * returns[i]

        # Determine tomorrow's position based on today's signal
        signal = signals[i]
        track = tracks[i]

        if signal in ['S+', 'S'] and track == 'contrarian':
            current_position = 1.0  # Buy: contrarian entry
        elif signal in ['A', 'B', 'C'] and track == 'trend_follow':
            current_position = 1.0  # Buy: trend_follow entry
        elif signal == 'E':
            current_position = min(current_position, 0.5)  # Reduce to 50%
        elif signal == 'D':
            current_position = 0.0  # Clear
        # A/B/C on excluded → hold current position (no change)

        positions[i] = current_position

    # Calculate cumulative returns
    cumulative = np.cumprod(1 + daily_returns)

    # Metrics
    total_return = cumulative[-1] - 1.0
    n_days = len(daily_returns)
    annual_return = (1 + total_return) ** (252 / n_days) - 1 if n_days > 0 else 0

    # Max drawdown
    peak = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - peak) / peak
    max_drawdown = drawdown.min()

    # Sharpe ratio (annualized, rf=2%)
    rf_daily = 0.02 / 252
    excess_returns = daily_returns - rf_daily
    std_excess = np.std(excess_returns)
    if std_excess > 1e-10:
        sharpe = np.mean(excess_returns) / std_excess * math.sqrt(252)
    else:
        sharpe = 0.0

    # Win rate (days with positive returns when positioned)
    positioned_days = daily_returns[positions > 0]
    if len(positioned_days) > 0:
        win_rate = np.mean(positioned_days > 0)
    else:
        win_rate = 0.0

    # Trading stats
    position_changes = np.diff(positions, prepend=0.0)
    buy_count = np.sum(position_changes > 0.1)  # Count significant position increases
    # Average holding period
    in_position = positions > 0
    if np.any(in_position):
        # Count consecutive runs of in_position
        runs = 0
        run_length = 0
        total_holding_days = 0
        for j in range(n):
            if in_position[j]:
                run_length += 1
            else:
                if run_length > 0:
                    runs += 1
                    total_holding_days += run_length
                    run_length = 0
        if run_length > 0:
            runs += 1
            total_holding_days += run_length
        avg_holding_days = total_holding_days / runs if runs > 0 else 0
    else:
        avg_holding_days = 0
        runs = 0

    return {
        'sector_code': sector_df['sector_code'].iloc[0],
        'sector_name': sector_df['sector_name'].iloc[0],
        'n_days': n_days,
        'total_return': total_return,
        'annual_return': annual_return,
        'max_drawdown': max_drawdown,
        'sharpe': sharpe,
        'win_rate': win_rate,
        'buy_count': int(buy_count),
        'avg_holding_days': avg_holding_days,
        'position_pct': np.mean(positions > 0),
        'daily_returns': daily_returns,
        'positions': positions,
        'cumulative': cumulative,
        'trade_dates': sector_df['trade_date'].values,
    }


# ============================================================
# Run backtest for all sectors
# ============================================================
def run_all_sectors(merged_df):
    """Run price backtest for all 31 sectors"""
    results = {}
    print(f"\n  回测 {merged_df['sector_code'].nunique()} 个板块...")

    for i, (scode, group) in enumerate(merged_df.groupby('sector_code')):
        result = backtest_single_sector(group)
        if result:
            results[scode] = result
            if (i + 1) % 10 == 0:
                print(f"    进度: {i+1}/{len(SECTOR_CODES)}")

    return results


# ============================================================
# Calculate benchmark returns
# ============================================================
def calculate_benchmarks(merged_df, sector_results):
    """
    Benchmark 1: Equal-weight buy-and-hold all 31 sectors
    Benchmark 2: Average sector return (daily cross-sectional mean)
    """
    # Benchmark 1: Equal-weight daily average return
    daily_avg_returns = merged_df.groupby('trade_date')['daily_return'].mean()
    daily_avg_returns = daily_avg_returns.fillna(0).values
    bench1_cumulative = np.cumprod(1 + daily_avg_returns)
    bench1_total = bench1_cumulative[-1] - 1
    n_days = len(daily_avg_returns)
    bench1_annual = (1 + bench1_total) ** (252 / n_days) - 1 if n_days > 0 else 0

    # Benchmark 1 max drawdown
    bench1_peak = np.maximum.accumulate(bench1_cumulative)
    bench1_dd = ((bench1_cumulative - bench1_peak) / bench1_peak).min()

    # Benchmark 1 Sharpe
    rf_daily = 0.02 / 252
    bench1_excess = daily_avg_returns - rf_daily
    if np.std(bench1_excess) > 0:
        bench1_sharpe = np.mean(bench1_excess) / np.std(bench1_excess) * math.sqrt(252)
    else:
        bench1_sharpe = 0.0

    # Strategy: average across all sectors (equal weight portfolio)
    # Align all sector daily returns
    all_dates = sorted(merged_df['trade_date'].unique())
    strategy_daily = np.zeros(len(all_dates))
    bench2_daily = np.zeros(len(all_dates))
    date_idx = {d: i for i, d in enumerate(all_dates)}

    n_sectors = 0
    for scode, result in sector_results.items():
        n_sectors += 1
        for j, date in enumerate(result['trade_dates']):
            if date in date_idx:
                idx = date_idx[date]
                strategy_daily[idx] += result['daily_returns'][j]
                bench2_daily[idx] += result['daily_returns'][j]  # Same as buy-hold for benchmark

    if n_sectors > 0:
        strategy_daily /= n_sectors
        bench2_daily /= n_sectors  # This is the same as benchmark 1

    strategy_cumulative = np.cumprod(1 + strategy_daily)
    strategy_total = strategy_cumulative[-1] - 1
    strategy_annual = (1 + strategy_total) ** (252 / len(all_dates)) - 1 if len(all_dates) > 0 else 0

    strategy_peak = np.maximum.accumulate(strategy_cumulative)
    strategy_dd = ((strategy_cumulative - strategy_peak) / strategy_peak).min()

    strategy_excess = strategy_daily - rf_daily
    if np.std(strategy_excess) > 0:
        strategy_sharpe = np.mean(strategy_excess) / np.std(strategy_excess) * math.sqrt(252)
    else:
        strategy_sharpe = 0.0

    # Strategy win rate
    strategy_positioned = strategy_daily[strategy_daily != 0]
    strategy_win = np.mean(strategy_daily > 0) if len(strategy_daily) > 0 else 0

    return {
        'strategy': {
            'total_return': strategy_total,
            'annual_return': strategy_annual,
            'max_drawdown': strategy_dd,
            'sharpe': strategy_sharpe,
            'win_rate': strategy_win,
            'cumulative': strategy_cumulative,
            'daily_returns': strategy_daily,
        },
        'benchmark_equal_weight': {
            'total_return': bench1_total,
            'annual_return': bench1_annual,
            'max_drawdown': bench1_dd,
            'sharpe': bench1_sharpe,
            'cumulative': bench1_cumulative,
            'daily_returns': daily_avg_returns,
        },
        'all_dates': all_dates,
    }


# ============================================================
# Signal-specific return analysis
# ============================================================
def signal_return_analysis(merged_df):
    """
    Analyze forward returns after each signal type.
    For each signal occurrence, compute 5-day, 10-day, 20-day forward returns.
    """
    # Sort by sector and date
    df = merged_df.sort_values(['sector_code', 'trade_date']).reset_index(drop=True)

    # For each sector, compute forward returns
    results = defaultdict(list)

    for scode, group in df.groupby('sector_code'):
        group = group.reset_index(drop=True)
        n = len(group)
        returns = group['daily_return'].values
        signals = group['signal'].values

        for i in range(n):
            sig = signals[i]
            # Compute forward returns: 5d, 10d, 20d
            for fwd_days in [5, 10, 20]:
                if i + fwd_days < n:
                    fwd_return = np.prod(1 + returns[i+1:i+1+fwd_days]) - 1
                    results[(sig, fwd_days)].append(fwd_return)

    # Aggregate statistics
    signal_stats = []
    signal_order = ['S+', 'S', 'A', 'B', 'C', 'D', 'E']
    for sig in signal_order:
        for fwd in [5, 10, 20]:
            rets = results.get((sig, fwd), [])
            if rets:
                arr = np.array(rets)
                signal_stats.append({
                    'signal': sig,
                    'forward_days': fwd,
                    'count': len(arr),
                    'mean_return': np.mean(arr),
                    'median_return': np.median(arr),
                    'win_rate': np.mean(arr > 0),
                    'std_return': np.std(arr),
                })
            else:
                signal_stats.append({
                    'signal': sig,
                    'forward_days': fwd,
                    'count': 0,
                    'mean_return': 0,
                    'median_return': 0,
                    'win_rate': 0,
                    'std_return': 0,
                })

    return pd.DataFrame(signal_stats)


# ============================================================
# Save results
# ============================================================
def save_results(sector_results, benchmark_results, signal_stats_df):
    """Save backtest results to CSV and summary to txt"""
    script_dir = os.path.dirname(__file__)

    # 1. Per-sector results CSV
    csv_path = os.path.join(script_dir, 'sector_backtest_price_results.csv')
    rows = []
    for scode, res in sector_results.items():
        rows.append({
            'sector_code': res['sector_code'],
            'sector_name': res['sector_name'],
            'n_days': res['n_days'],
            'total_return': round(res['total_return'], 4),
            'annual_return': round(res['annual_return'], 4),
            'max_drawdown': round(res['max_drawdown'], 4),
            'sharpe': round(res['sharpe'], 2),
            'win_rate': round(res['win_rate'], 4),
            'buy_count': res['buy_count'],
            'avg_holding_days': round(res['avg_holding_days'], 1),
            'position_pct': round(res['position_pct'], 4),
        })
    sector_df = pd.DataFrame(rows)
    sector_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"  板块结果已保存: {csv_path}")

    # 2. Summary text
    summary_path = os.path.join(script_dir, 'sector_backtest_summary.txt')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("板块情绪系统 V5.0 — 价格回测策略验证报告 (T8)\n")
        f.write("=" * 70 + "\n\n")

        # Strategy vs Benchmark
        f.write("--- 1. 策略 vs 基准对比 ---\n")
        strat = benchmark_results['strategy']
        bench = benchmark_results['benchmark_equal_weight']

        f.write(f"{'指标':>16s}  {'策略':>10s}  {'等权基准':>10s}  {'超额':>10s}\n")
        f.write(f"{'-'*16}  {'-'*10}  {'-'*10}  {'-'*10}\n")
        f.write(f"{'累计收益率':>16s}  {strat['total_return']:>10.2%}  {bench['total_return']:>10.2%}  {strat['total_return']-bench['total_return']:>10.2%}\n")
        f.write(f"{'年化收益率':>16s}  {strat['annual_return']:>10.2%}  {bench['annual_return']:>10.2%}  {strat['annual_return']-bench['annual_return']:>10.2%}\n")
        f.write(f"{'最大回撤':>16s}  {strat['max_drawdown']:>10.2%}  {bench['max_drawdown']:>10.2%}  {strat['max_drawdown']-bench['max_drawdown']:>10.2%}\n")
        f.write(f"{'夏普比率':>16s}  {strat['sharpe']:>10.2f}  {bench['sharpe']:>10.2f}  {strat['sharpe']-bench['sharpe']:>10.2f}\n")
        f.write(f"{'胜率':>16s}  {strat['win_rate']:>10.2%}  {'—':>10s}  {'—':>10s}\n")
        f.write("\n")

        # Per-sector top/bottom
        f.write("--- 2. 板块表现 Top 5 / Bottom 5 ---\n")
        sorted_sectors = sector_df.sort_values('annual_return', ascending=False)
        f.write(f"  Top 5 (年化收益):\n")
        for _, row in sorted_sectors.head(5).iterrows():
            f.write(f"    {row['sector_name']}({row['sector_code']})  年化={row['annual_return']:.2%}  回撤={row['max_drawdown']:.2%}  夏普={row['sharpe']:.2f}  胜率={row['win_rate']:.2%}\n")
        f.write(f"  Bottom 5 (年化收益):\n")
        for _, row in sorted_sectors.tail(5).iterrows():
            f.write(f"    {row['sector_name']}({row['sector_code']})  年化={row['annual_return']:.2%}  回撤={row['max_drawdown']:.2%}  夏普={row['sharpe']:.2f}  胜率={row['win_rate']:.2%}\n")
        f.write("\n")

        # Average across sectors
        f.write(f"  31板块平均: 年化={sector_df['annual_return'].mean():.2%}  回撤={sector_df['max_drawdown'].mean():.2%}  夏普={sector_df['sharpe'].mean():.2f}\n")
        f.write(f"  盈利板块数: {(sector_df['total_return'] > 0).sum()}/31  亏损板块数: {(sector_df['total_return'] <= 0).sum()}/31\n")
        f.write("\n")

        # Signal-specific analysis
        f.write("--- 3. 分信号前瞻收益统计 ---\n")
        f.write(f"{'信号':>4s}  {'天数':>4s}  {'5日均值':>10s}  {'5日胜率':>8s}  {'10日均值':>10s}  {'10日胜率':>8s}  {'20日均值':>10s}  {'20日胜率':>8s}\n")
        f.write(f"{'-'*4}  {'-'*4}  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*8}\n")
        for sig in ['S+', 'S', 'A', 'B', 'C', 'D', 'E']:
            row_5 = signal_stats_df[(signal_stats_df['signal'] == sig) & (signal_stats_df['forward_days'] == 5)]
            row_10 = signal_stats_df[(signal_stats_df['signal'] == sig) & (signal_stats_df['forward_days'] == 10)]
            row_20 = signal_stats_df[(signal_stats_df['signal'] == sig) & (signal_stats_df['forward_days'] == 20)]
            if len(row_5) > 0:
                r5 = row_5.iloc[0]
                r10 = row_10.iloc[0]
                r20 = row_20.iloc[0]
                f.write(f"{sig:>4s}  {r5['count']:>4d}  {r5['mean_return']:>10.2%}  {r5['win_rate']:>8.1%}  {r10['mean_return']:>10.2%}  {r10['win_rate']:>8.1%}  {r20['mean_return']:>10.2%}  {r20['win_rate']:>8.1%}\n")
        f.write("\n")

        # Signal interpretation
        f.write("--- 4. 信号有效性结论 ---\n")
        s_stats = signal_stats_df[signal_stats_df['signal'] == 'S']
        d_stats = signal_stats_df[signal_stats_df['signal'] == 'D']
        e_stats = signal_stats_df[signal_stats_df['signal'] == 'E']

        if len(s_stats) > 0:
            s_10 = s_stats[s_stats['forward_days'] == 10].iloc[0]
            f.write(f"  S信号 (恐惧逆向): 10日均收益={s_10['mean_return']:.2%}, 胜率={s_10['win_rate']:.1%}, 样本={s_10['count']}\n")
            if s_10['mean_return'] > 0:
                f.write(f"    → S信号后短期表现正向, 逆向买入策略有效 ✓\n")
            else:
                f.write(f"    → S信号后短期表现负向, 需进一步优化 ⚠\n")

        if len(d_stats) > 0:
            d_10 = d_stats[d_stats['forward_days'] == 10].iloc[0]
            f.write(f"  D信号 (贪婪排除): 10日均收益={d_10['mean_return']:.2%}, 胜率={d_10['win_rate']:.1%}, 样本={d_10['count']}\n")
            if d_10['mean_return'] < 0:
                f.write(f"    → D信号后短期下跌, excluded排除逻辑正确 ✓\n")
            else:
                f.write(f"    → D信号后短期仍上涨, 排除逻辑需审视 ⚠\n")

        if len(e_stats) > 0:
            e_10 = e_stats[e_stats['forward_days'] == 10].iloc[0]
            f.write(f"  E信号 (极度贪婪): 10日均收益={e_10['mean_return']:.2%}, 胜率={e_10['win_rate']:.1%}, 样本={e_10['count']}\n")
            if e_10['mean_return'] < 0:
                f.write(f"    → E信号后短期下跌, Gate-E减仓逻辑有效 ✓\n")
            else:
                f.write(f"    → E信号后短期仍上涨, Gate-E需审视 ⚠\n")
        else:
            f.write(f"  E信号 (极度贪婪): 回测期间无E信号触发\n")

        f.write("\n")

        # Overall conclusion
        f.write("--- 5. 总结 ---\n")
        excess = strat['annual_return'] - bench['annual_return']
        f.write(f"  策略年化收益: {strat['annual_return']:.2%} vs 基准 {bench['annual_return']:.2%} (超额 {excess:+.2%})\n")
        f.write(f"  策略最大回撤: {strat['max_drawdown']:.2%} vs 基准 {bench['max_drawdown']:.2%}\n")
        f.write(f"  策略夏普比率: {strat['sharpe']:.2f} vs 基准 {bench['sharpe']:.2f}\n")
        if excess > 0:
            f.write(f"  结论: 策略跑赢基准 {excess:.2%}, 情绪信号具有选alpha能力 ✓\n")
        else:
            f.write(f"  结论: 策略跑输基准 {abs(excess):.2%}, 需优化信号触发条件 ⚠\n")

    print(f"  摘要已保存: {summary_path}")

    # Print summary to console
    with open(summary_path, 'r', encoding='utf-8') as f:
        print(f.read())


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 70)
    print("板块情绪系统 V5.0 — 价格回测策略验证 (T8)")
    print("=" * 70)

    start_time = time.time()

    # 1. Load backtest results
    print("\n[1/6] 加载回测信号数据...")
    signals_df = load_backtest_results()

    # 2. Load price data
    print("\n[2/6] 加载价格数据...")
    prices_df = load_sector_prices()

    # 3. Merge signals with prices
    print("\n[3/6] 合并信号与价格数据...")
    merged_df = merge_signals_prices(signals_df, prices_df)

    # 4. Reassign tracks with MA20 trend
    print("\n[4/6] 重新分配轨道 (使用MA20趋势)...")
    merged_df = reassign_tracks(merged_df)

    # 5. Run price backtest
    print("\n[5/6] 执行价格回测...")
    sector_results = run_all_sectors(merged_df)

    # Calculate benchmarks
    print("\n  计算基准对比...")
    benchmark_results = calculate_benchmarks(merged_df, sector_results)

    # Signal return analysis
    print("\n  分信号收益分析...")
    signal_stats_df = signal_return_analysis(merged_df)

    # 6. Save results
    print("\n[6/6] 保存结果...")
    save_results(sector_results, benchmark_results, signal_stats_df)

    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f}s")
    print("=" * 70)


if __name__ == '__main__':
    main()
