#!/usr/bin/env python3
"""
板块情绪系统历史回测验证脚本

遍历 factor_history 历史数据，对每个交易日计算31个板块的V5评分和双轨制轨道，
验证系统在不同市场状态下的信号分布、轨道覆盖度和推荐频率。

简化方案:
  - 使用 factor_history 表中的 raw_value 直接走分位数→sigmoid→聚合流水线
  - 分位数使用 point-in-time 计算（仅用截至该日期的历史数据）
  - 跳过 AKShare 价格数据获取
  - 趋势判断（MA20）无历史价格数据，trend_follow 轨道无法通过
  - 逆向轨道 S+ 信号可无背离数据通过

输出:
  - 控制台统计摘要
  - CSV: sector_backtest_results.csv
"""
import sys
import os
import csv
import math
import time
import logging
import warnings
from datetime import datetime, date
from collections import defaultdict, Counter
from bisect import bisect_right

import numpy as np

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')

# ============================================================
# Import V5 engine components
# ============================================================
from app.core.config import settings
from app.engine.sector_scorer import (
    V5_SECTOR_FACTOR_CONFIG,
    SECTOR_FACTOR_NAMES,
    NON_DIV_FACTORS,
    COLD_START_MIN_SAMPLES,
    DIV_INDEX_CODE,
    SectorFactorResult,
    _sigmoid_map_factor,
    _aggregate_sector_scores,
    _apply_sigmoid,
    _sentiment_label,
)
from app.engine.sector_scorer import _map_sector_signal
from app.engine.confidence import ConfidenceEngine
from app.engine.sector_scorer import calculate_sector_filter

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
# Pre-load factor_history data into memory
# ============================================================
def load_factor_history():
    """
    Returns:
        factor_data: {(index_code, factor_name): [(trade_date_str, raw_value), ...]}
        div_data: {trade_date_str: (raw_value, quantile_percentile)}
        all_dates: sorted list of trade_date strings (non-DIV)
    """
    conn = get_db_conn()
    cur = conn.cursor()

    # Load non-DIV factors
    cur.execute("""
        SELECT index_code, factor_name, trade_date, raw_value, quantile_percentile
        FROM factor_history
        WHERE index_code LIKE '801%%'
        ORDER BY index_code, factor_name, trade_date
    """)
    factor_data = defaultdict(list)
    for row in cur.fetchall():
        code, fname, tdate, rval, qpct = row
        if rval is not None:
            factor_data[(code, fname)].append((str(tdate), float(rval)))

    # Load DIV factor
    cur.execute("""
        SELECT trade_date, raw_value, quantile_percentile
        FROM factor_history
        WHERE index_code = 'SW_L1_DIV'
        ORDER BY trade_date
    """)
    div_data = {}
    for row in cur.fetchall():
        tdate, rval, qpct = row
        div_data[str(tdate)] = (float(rval), float(qpct) if qpct else None)

    # Collect all unique trade dates from non-DIV data
    all_dates_set = set()
    for (code, fname), series in factor_data.items():
        for tdate, _ in series:
            all_dates_set.add(tdate)
    all_dates = sorted(all_dates_set)

    conn.close()
    return factor_data, div_data, all_dates


# ============================================================
# Point-in-time percentile calculation
# ============================================================
def compute_point_in_time_percentile(series_up_to_date, raw_value):
    """
    Compute percentile of raw_value in the series (only values up to the backtest date).
    Uses rank-based percentile: (rank + 0.5) / total

    Args:
        series_up_to_date: list of (trade_date_str, raw_value) sorted by date
        raw_value: the value to compute percentile for

    Returns:
        (percentile 0.0-1.0, sample_count) or (None, count) if insufficient
    """
    values = [v for _, v in series_up_to_date]
    count = len(values)

    if count < COLD_START_MIN_SAMPLES:
        return None, count

    # Use scipy-style percentileofscore (rank method)
    sorted_vals = sorted(values)
    # Find rank position
    rank = bisect_right(sorted_vals, raw_value)
    pct = (rank + 0.5) / count
    return round(pct, 6), count


# ============================================================
# Score a single sector for a given date
# ============================================================
def score_sector_for_date(
    sector_code: str,
    trade_date: str,
    factor_data: dict,
    div_data: dict,
    conf_engine: ConfidenceEngine,
    signal_mapper=None,  # deprecated, unused
) -> dict:
    """
    Compute V5 score for a single sector on a specific date.
    Uses point-in-time percentiles from factor_history.
    """
    sector_name = SW_SECTOR_NAMES.get(sector_code, sector_code)
    factor_results = []
    cold_start = False

    # --- Non-DIV factors ---
    for factor_name in NON_DIV_FACTORS:
        series = factor_data.get((sector_code, factor_name), [])

        # Find raw_value for this date
        raw_val = None
        for tdate, rval in series:
            if tdate == trade_date:
                raw_val = rval
                break

        if raw_val is None or not np.isfinite(raw_val):
            continue

        # Compute point-in-time percentile
        # Filter series to only dates <= trade_date
        series_up_to = [(t, v) for t, v in series if t <= trade_date]
        percentile, sample_count = compute_point_in_time_percentile(series_up_to, raw_val)

        if percentile is None and sample_count < COLD_START_MIN_SAMPLES:
            cold_start = True

        fr = _sigmoid_map_factor(
            factor_name, percentile, raw_val,
            cold_start=(percentile is None and sample_count < COLD_START_MIN_SAMPLES)
        )
        factor_results.append(fr)

    # --- DIV factor ---
    div_info = div_data.get(trade_date)
    if div_info and div_info[1] is not None:
        div_fr = _sigmoid_map_factor("DIV", div_info[1], div_info[0], cold_start=False)
        factor_results.append(div_fr)
    else:
        div_fr = _sigmoid_map_factor("DIV", 0.5, 0.0, cold_start=True)
        factor_results.append(div_fr)

    if not factor_results:
        return {
            "sector_code": sector_code,
            "sector_name": sector_name,
            "trade_date": trade_date,
            "score": 50.0,
            "signal": "B",
            "stars": 0,
            "track": "excluded",
            "cold_start": True,
            "factor_completeness": 0.0,
            "factor_scores": {},
        }

    # --- Aggregate ---
    composite_score, agg_detail = _aggregate_sector_scores(factor_results)

    # --- Signal mapping ---
    signal_level = _map_sector_signal(composite_score)

    # --- Regime ---
    scores = [fr.sigmoid_score for fr in factor_results]
    mean_score = float(np.mean(scores))
    std_score = float(np.std(scores))
    if std_score > settings.V5_DIVERGENCE_STD_THRESHOLD:
        regime = "extreme_volatility"
    elif mean_score > 60:
        regime = "bull"
    elif mean_score < 40:
        regime = "bear"
    else:
        regime = "sideways"

    # --- Confidence ---
    from app.engine.factor_engine.base import FactorSigmoidResult
    sigmoid_results = []
    for fr in factor_results:
        sigmoid_results.append(FactorSigmoidResult(
            factor_name=fr.factor_name,
            percentile=fr.percentile if fr.percentile is not None else 0.5,
            sigmoid_score=fr.sigmoid_score,
            c_param=V5_SECTOR_FACTOR_CONFIG[fr.factor_name]["sigmoid_c"],
            k_param=V5_SECTOR_FACTOR_CONFIG[fr.factor_name]["sigmoid_k"],
            slope_at_midpoint=0.0,
        ))

    try:
        stars, detail, triggered = conf_engine.calculate(
            sigmoid_results=sigmoid_results,
            signal_level=signal_level,
            regime=regime,
            price_series=None,
            sentiment_series=None,
        )
    except Exception:
        stars = 1
        triggered = []

    # --- Factor completeness ---
    expected = len(V5_SECTOR_FACTOR_CONFIG)
    available = len([fr for fr in factor_results if not fr.cold_start])
    fc = available / expected

    # --- Track (no price history → MA20 trend = "震荡") ---
    track = calculate_sector_filter(
        sector_code=sector_code,
        sentiment_score=composite_score,
        signal_level=signal_level,
        confidence_stars=stars,
        sector_price_history=None,
        factor_completeness=fc,
    )

    return {
        "sector_code": sector_code,
        "sector_name": sector_name,
        "trade_date": trade_date,
        "score": composite_score,
        "signal": signal_level,
        "stars": stars,
        "track": track,
        "cold_start": cold_start,
        "factor_completeness": fc,
        "factor_scores": {fr.factor_name: round(fr.sigmoid_score, 1) for fr in factor_results},
        "regime": regime,
    }


# ============================================================
# Main backtest
# ============================================================
def run_backtest():
    print("=" * 70)
    print("板块情绪系统历史回测验证")
    print("=" * 70)

    start_time = time.time()

    # 1. Load data
    print("\n[1/4] 加载 factor_history 数据...")
    factor_data, div_data, all_dates = load_factor_history()
    print(f"  因子数据: {len(factor_data)} 个 (sector×factor) 组合")
    print(f"  DIV 数据: {len(div_data)} 天")
    print(f"  交易日总数: {len(all_dates)} 天")
    print(f"  日期范围: {all_dates[0]} ~ {all_dates[-1]}")

    # 2. Determine backtest date range
    # COLD_START_MIN_SAMPLES = 252, so start from date where we have 252+ samples
    # Find the date index where we have enough data
    # Since data starts ~2024-06-19, 252 trading days later ≈ 2025-06
    bt_start_idx = max(0, len(all_dates) - 252)  # Last 252 trading days (~12 months)
    # But also ensure we have at least 252 days before start
    if len(all_dates) > 252 * 2:
        bt_start_idx = 252  # Start from day 253
    else:
        bt_start_idx = max(0, len(all_dates) - 252)

    bt_dates = all_dates[bt_start_idx:]
    print(f"\n  回测起始日 (跳过冷启动): {bt_dates[0]}")
    print(f"  回测结束日: {bt_dates[-1]}")
    print(f"  回测天数: {len(bt_dates)} 天")

    # 3. Run backtest
    print(f"\n[2/4] 执行回测 ({len(bt_dates)} 天 × {len(SECTOR_CODES)} 板块)...")
    # signal_mapper no longer needed (using _map_sector_signal)
    conf_engine = ConfidenceEngine()

    results = []
    daily_stats = []

    for i, tdate in enumerate(bt_dates):
        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{len(bt_dates)} ({(i+1)/len(bt_dates)*100:.0f}%)")

        daily_tracks = Counter()
        daily_signals = Counter()
        daily_scores = []
        daily_recommendations = {"contrarian": 0, "trend_follow": 0}

        for scode in SECTOR_CODES:
            result = score_sector_for_date(
                scode, tdate, factor_data, div_data, conf_engine
            )
            results.append(result)
            daily_tracks[result["track"]] += 1
            daily_signals[result["signal"]] += 1
            daily_scores.append(result["score"])

            if result["track"] == "contrarian":
                daily_recommendations["contrarian"] += 1
            elif result["track"] == "trend_follow":
                daily_recommendations["trend_follow"] += 1

        daily_stats.append({
            "date": tdate,
            "trend_follow": daily_tracks["trend_follow"],
            "contrarian": daily_tracks["contrarian"],
            "excluded": daily_tracks["excluded"],
            "total_sectors": len(SECTOR_CODES),
            "avg_score": round(np.mean(daily_scores), 1) if daily_scores else 0,
            "min_score": round(min(daily_scores), 1) if daily_scores else 0,
            "max_score": round(max(daily_scores), 1) if daily_scores else 0,
            "contrarian_recs": min(daily_recommendations["contrarian"], 3),
            "trend_recs": min(daily_recommendations["trend_follow"], 5),
            "signal_dist": dict(daily_signals),
        })

    elapsed = time.time() - start_time
    print(f"  回测完成，耗时 {elapsed:.1f}s，共 {len(results)} 条记录")

    # 4. Write CSV
    print(f"\n[3/4] 写入 CSV...")
    csv_path = os.path.join(os.path.dirname(__file__), 'sector_backtest_results.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            'trade_date', 'sector_code', 'sector_name', 'score', 'signal',
            'stars', 'track', 'cold_start', 'factor_completeness', 'regime',
            'TURN_score', 'VOL_score', 'NHNL_score', 'RSI_score', 'DIV_score'
        ])
        for r in results:
            fs = r.get('factor_scores', {})
            writer.writerow([
                r['trade_date'], r['sector_code'], r['sector_name'],
                r['score'], r['signal'], r['stars'], r['track'],
                r['cold_start'], round(r['factor_completeness'], 2),
                r.get('regime', ''),
                fs.get('TURN', ''), fs.get('VOL', ''),
                fs.get('NHNL', ''), fs.get('RSI', ''),
                fs.get('DIV', ''),
            ])
    print(f"  CSV 已保存: {csv_path} ({len(results)} 行)")

    # 5. Analysis & Report
    print(f"\n[4/4] 统计分析")
    print("=" * 70)

    # --- 5.1 轨道覆盖度 ---
    total_records = len(results)
    track_counts = Counter(r["track"] for r in results)
    tf_pct = track_counts.get("trend_follow", 0) / total_records * 100
    ct_pct = track_counts.get("contrarian", 0) / total_records * 100
    ex_pct = track_counts.get("excluded", 0) / total_records * 100

    print("\n--- 5.1 轨道覆盖度 ---")
    print(f"  trend_follow: {track_counts.get('trend_follow', 0):5d} ({tf_pct:.1f}%)")
    print(f"  contrarian:   {track_counts.get('contrarian', 0):5d} ({ct_pct:.1f}%)")
    print(f"  excluded:     {track_counts.get('excluded', 0):5d} ({ex_pct:.1f}%)")
    coverage = tf_pct + ct_pct
    verdict = "✓ 合理" if 5 <= coverage <= 80 else ("⚠ 偏低" if coverage < 5 else "⚠ 偏高")
    print(f"  覆盖度 (tf+ct): {coverage:.1f}%  {verdict}")

    # --- 5.2 信号分布 ---
    signal_counts = Counter(r["signal"] for r in results)
    print("\n--- 5.2 信号分布 ---")
    signal_order = ["S+", "S", "A", "B", "C", "D", "E"]
    for sig in signal_order:
        cnt = signal_counts.get(sig, 0)
        pct = cnt / total_records * 100
        bar = "█" * int(pct / 2)
        print(f"  {sig:2s} ({_sentiment_label(_sig_to_score(sig)):4s}): {cnt:5d} ({pct:5.1f}%) {bar}")

    b_pct = signal_counts.get("B", 0) / total_records * 100
    verdict = "✓ 分布合理" if b_pct < 80 else "⚠ B信号占比过高"
    print(f"  B信号占比: {b_pct:.1f}%  {verdict}")

    # --- 5.3 推荐频率 ---
    total_days = len(daily_stats)
    days_with_contrarian = sum(1 for d in daily_stats if d["contrarian_recs"] > 0)
    days_with_trend = sum(1 for d in daily_stats if d["trend_recs"] > 0)
    days_with_any_rec = sum(1 for d in daily_stats if d["contrarian_recs"] + d["trend_recs"] > 0)
    total_contrarian_recs = sum(d["contrarian_recs"] for d in daily_stats)
    total_trend_recs = sum(d["trend_recs"] for d in daily_stats)

    print("\n--- 5.3 推荐频率 ---")
    print(f"  回测天数: {total_days}")
    print(f"  有逆向推荐的天数: {days_with_contrarian} ({days_with_contrarian/total_days*100:.1f}%)")
    print(f"  有趋势推荐的天数: {days_with_trend} ({days_with_trend/total_days*100:.1f}%)")
    print(f"  有任何推荐的天数: {days_with_any_rec} ({days_with_any_rec/total_days*100:.1f}%)")
    print(f"  逆向推荐总数: {total_contrarian_recs} (平均 {total_contrarian_recs/total_days:.2f}/天)")
    print(f"  趋势推荐总数: {total_trend_recs} (平均 {total_trend_recs/total_days:.2f}/天)")
    verdict = "✓ 有推荐" if days_with_any_rec > 0 else "⚠ 长期无推荐"
    print(f"  {verdict}")

    # --- 5.4 极端市场响应 ---
    print("\n--- 5.4 极端市场响应 ---")
    # Find days with lowest/highest avg score
    sorted_days = sorted(daily_stats, key=lambda x: x["avg_score"])
    print("  平均分最低5天 (恐惧极值):")
    for d in sorted_days[:5]:
        print(f"    {d['date']} | avg={d['avg_score']:5.1f} | min={d['min_score']} | max={d['max_score']} | tf={d['trend_follow']} ct={d['contrarian']} ex={d['excluded']}")
    print("  平均分最高5天 (贪婪极值):")
    for d in sorted_days[-5:]:
        print(f"    {d['date']} | avg={d['avg_score']:5.1f} | min={d['min_score']} | max={d['max_score']} | tf={d['trend_follow']} ct={d['contrarian']} ex={d['excluded']}")

    # --- 5.5 因子贡献 ---
    print("\n--- 5.5 因子 Sigmoid 分数分布 ---")
    for fname in SECTOR_FACTOR_NAMES:
        scores = [r["factor_scores"].get(fname) for r in results if fname in r.get("factor_scores", {})]
        if scores:
            arr = np.array(scores)
            print(f"  {fname:5s}: mean={np.mean(arr):5.1f} std={np.std(arr):5.1f} min={np.min(arr):5.1f} max={np.max(arr):5.1f} P25={np.percentile(arr,25):5.1f} P75={np.percentile(arr,75):5.1f}")
        else:
            print(f"  {fname:5s}: 无数据")

    # --- 5.6 月度趋势 ---
    print("\n--- 5.6 月度轨道分布 ---")
    monthly = defaultdict(lambda: {"tf": 0, "ct": 0, "ex": 0, "days": 0})
    for d in daily_stats:
        month = d["date"][:7]  # YYYY-MM
        monthly[month]["tf"] += d["trend_follow"]
        monthly[month]["ct"] += d["contrarian"]
        monthly[month]["ex"] += d["excluded"]
        monthly[month]["days"] += 1
    print(f"  {'月份':8s} {'天数':>4s} {'趋势':>6s} {'逆向':>6s} {'排除':>6s} {'覆盖率':>8s}")
    for month in sorted(monthly.keys()):
        m = monthly[month]
        total = m["tf"] + m["ct"] + m["ex"]
        cov = (m["tf"] + m["ct"]) / total * 100 if total > 0 else 0
        print(f"  {month:8s} {m['days']:4d} {m['tf']:6d} {m['ct']:6d} {m['ex']:6d} {cov:7.1f}%")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("回测验证总结")
    print("=" * 70)
    print(f"  回测期间: {bt_dates[0]} ~ {bt_dates[-1]} ({len(bt_dates)} 交易日)")
    print(f"  板块数: {len(SECTOR_CODES)}")
    print(f"  总记录: {total_records}")
    print(f"  耗时: {elapsed:.1f}s")

    print(f"\n  5项关键指标结论:")
    print(f"  1. 轨道覆盖度: {coverage:.1f}% (tf={tf_pct:.1f}% + ct={ct_pct:.1f}%) — {verdict}")
    print(f"  2. 信号分布: B占比={b_pct:.1f}% — {'合理' if b_pct < 80 else '过于集中'}")
    print(f"  3. 推荐频率: {days_with_any_rec}/{total_days}天有推荐 ({days_with_any_rec/total_days*100:.1f}%)")
    print(f"  4. 极端响应: 最低avg={sorted_days[0]['avg_score']}, 最高avg={sorted_days[-1]['avg_score']}")
    print(f"  5. 因子分布: 见上方详细统计")

    return results, daily_stats


def _sig_to_score(sig):
    """Map signal level to approximate score for label lookup"""
    mapping = {"S+": 10, "S": 25, "A": 40, "B": 50, "C": 60, "D": 75, "E": 90}
    return mapping.get(sig, 50)


if __name__ == '__main__':
    run_backtest()
