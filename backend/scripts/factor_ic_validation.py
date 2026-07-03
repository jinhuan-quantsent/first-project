#!/usr/bin/env python3
"""
板块因子 IC/IR 有效性验证脚本 (Step 1 重验版)
验证 7 个板块因子在板块维度是否有 alpha

Step 1 变更:
  MOM   - 板块动量: 20日 → 60日中期动量
  ADR   - 涨跌天数比 → 成交额加权涨跌比 (考虑涨跌幅度信息量)

因子清单:
  MOM   - 板块动量 (greed): 60日收益率
  VOL   - 板块波动率 (fear): 20日年化波动率
  RSI   - 板块RSI(14) (fear): 14日RSI
  NHNL  - 新高新低净占比 (greed): (20日新高数-20日新低数)/20
  ADR   - 成交额加权涨跌比 (greed): 20日上涨日成交额/(上涨+下跌日成交额)
  TURN  - 成交额相对强度 (greed): 当日成交额/20日均成交额
  DIV   - 跨板块分歧度 (fear): 各板块情绪分的标准差

IC: 每日截面rank相关系数 corr(factor_t, forward_return_t+5)
IR: 月度IC均值 / 月度IC标准差
"""

import sys
import warnings
import time
import numpy as np
import pandas as pd
import akshare as ak
from datetime import datetime

warnings.filterwarnings('ignore')

# ==================== 配置 ====================
LOOKBACK_DAYS = 500       # 约2年交易日
FORWARD_PERIOD = 5        # 5日前瞻收益
MOM_WINDOW = 60          # 改为60日中期动量 (Step 1 重验)
VOL_WINDOW = 20
RSI_WINDOW = 14
NHNL_WINDOW = 20
ADR_WINDOW = 20
TURN_WINDOW = 20

# 因子方向: greed=正IC有效, fear=负IC有效
FACTOR_DIRECTIONS = {
    'MOM': 'greed',
    'VOL': 'fear',
    'RSI': 'fear',
    'NHNL': 'greed',
    'ADR': 'greed',
    'TURN': 'greed',
    'DIV': 'fear',
}

# 无效因子替代建议
SUGGESTIONS = {
    'MOM': '考虑使用12月动量(252日)或中期动量(60日), A股动量效应在中长期更显著',
    'VOL': '考虑使用下行波动率或特质波动率, 而非总体波动率',
    'RSI': '考虑使用MACD或KDJ指标替代, 或调整RSI周期至21日',
    'NHNL': '考虑使用成分股新高新低数据(需个股数据), 或用板块强弱排名替代',
    'ADR': '考虑使用成交额加权涨跌比, 或OBV指标',
    'TURN': '考虑使用换手率替代成交额相对强度, 或调整窗口至60日',
    'DIV': '考虑使用行业资金流分歧度或涨跌幅离散度替代',
}


# ==================== 数据获取 ====================

def get_sector_list():
    """获取申万一级行业列表"""
    df = ak.sw_index_first_info()
    sectors = []
    for _, row in df.iterrows():
        code = str(row['行业代码']).replace('.SI', '')
        name = row['行业名称']
        sectors.append({'code': code, 'name': name})
    print(f"获取申万一级行业: {len(sectors)} 个")
    return sectors


def fetch_sector_hist(code, name):
    """获取单个板块历史数据"""
    try:
        df = ak.index_hist_sw(symbol=code)
        if df is None or df.empty:
            print(f"  [WARN] {code} {name}: 数据为空")
            return None
        # 重命名列
        df = df.rename(columns={
            '日期': 'date', '收盘': 'close', '开盘': 'open',
            '最高': 'high', '最低': 'low',
            '成交量': 'volume', '成交额': 'amount'
        })
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        # 只取最近 LOOKBACK_DAYS 天
        df = df.tail(LOOKBACK_DAYS).reset_index(drop=True)
        df['sector_code'] = code
        df['sector_name'] = name
        return df[['date', 'close', 'volume', 'amount', 'sector_code', 'sector_name']]
    except Exception as e:
        print(f"  [ERROR] {code} {name}: {e}")
        return None


# ==================== 因子计算 ====================

def calc_mom(close, window=60):
    """板块动量: 60日收益率 = (close[-1]/close[-60] - 1)"""
    return close.pct_change(window)


def calc_vol(close, window=20):
    """板块波动率: 20日年化波动率 = std(daily_returns) * sqrt(252)"""
    returns = close.pct_change()
    return returns.rolling(window).std() * np.sqrt(252)


def calc_rsi(close, window=14):
    """板块RSI(14): 标准RSI计算"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    # Wilder平滑法
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_nhnl(close, window=20):
    """
    新高新低净占比: (20日新高数 - 20日新低数) / 20
    适配板块指数: 当日close为rolling window最高记为新高,最低记为新低
    再取20日滚动求和做平滑
    """
    rolling_max = close.rolling(window).max()
    rolling_min = close.rolling(window).min()
    is_new_high = (close >= rolling_max).astype(float)
    is_new_low = (close <= rolling_min).astype(float)
    nhnl = (is_new_high.rolling(window).sum() - is_new_low.rolling(window).sum()) / window
    return nhnl


def calc_adr(close, amount, window=20):
    """
    成交额加权涨跌比 (Step 1 重验):
    20日内上涨日成交额总和 / (上涨日成交额总和 + 下跌日成交额总和)
    相比单纯涨跌天数比, 考虑了涨跌幅度的信息量
    """
    is_up = (close.diff() > 0).astype(float)
    is_down = (close.diff() < 0).astype(float)
    up_amount = (amount * is_up).rolling(window).sum()
    down_amount = (amount * is_down).rolling(window).sum()
    total_amount = up_amount + down_amount
    # 避免除零
    adr = up_amount / total_amount.replace(0, np.nan)
    return adr


def calc_turn(amount, window=20):
    """成交额相对强度: 当日成交额 / 20日均成交额"""
    avg_amount = amount.rolling(window).mean()
    return amount / avg_amount


def compute_factors(df):
    """计算单个板块的6个因子"""
    close = df['close']
    amount = df['amount']

    df = df.copy()
    df['MOM'] = calc_mom(close, MOM_WINDOW)
    df['VOL'] = calc_vol(close, VOL_WINDOW)
    df['RSI'] = calc_rsi(close, RSI_WINDOW)
    df['NHNL'] = calc_nhnl(close, NHNL_WINDOW)
    df['ADR'] = calc_adr(close, amount, ADR_WINDOW)
    df['TURN'] = calc_turn(amount, TURN_WINDOW)

    return df


# ==================== IC/IR 计算 ====================

def compute_forward_returns(panel, period=5):
    """计算前瞻收益: forward_return = close[t+period]/close[t] - 1"""
    result = panel.copy()
    result['forward_return'] = result.groupby('sector_code')['close'].transform(
        lambda x: x.shift(-period) / x - 1
    )
    return result


def compute_cross_sectional_ic(panel, factor_name):
    """
    计算横截面IC: 每日跨板块Spearman rank相关系数
    corr(factor_value_t, forward_return_t+5) across sectors
    返回每日IC series
    """
    valid = panel.dropna(subset=[factor_name, 'forward_return'])
    if len(valid) < 5:
        return pd.Series(dtype=float)

    def _daily_ic(g):
        if len(g) < 5:
            return np.nan
        return g[factor_name].rank().corr(g['forward_return'].rank())

    ic_series = valid.groupby('date').apply(_daily_ic)
    return ic_series.dropna()


def compute_div_factor(panel):
    """
    DIV因子: 跨板块分歧度
    1. 对每个因子做截面rank归一化到[0,1]
    2. 情绪分 = 6因子截面rank均值 (等权)
    3. DIV = 每日情绪分的截面标准差
    返回: div_series (每日一个值), panel_with_sentiment
    """
    factor_cols = ['MOM', 'VOL', 'RSI', 'NHNL', 'ADR', 'TURN']
    panel = panel.copy()
    for col in factor_cols:
        panel[f'{col}_rank'] = panel.groupby('date')[col].rank(pct=True)

    rank_cols = [f'{col}_rank' for col in factor_cols]
    panel['sentiment_score'] = panel[rank_cols].mean(axis=1)

    # DIV = 每日情绪分的截面标准差
    div_series = panel.groupby('date')['sentiment_score'].std()
    div_series.name = 'DIV'

    return div_series, panel


def compute_div_ic(panel, div_series):
    """
    DIV因子的IC计算 (时间序列IC):
    DIV是市场层面因子(每日一个值), 无法做截面IC
    方法: corr(DIV_t, market_avg_forward_return_t+5) 按月分组
    market_avg_forward_return = 所有板块前瞻收益的均值
    """
    # 计算每日市场平均前瞻收益
    daily_avg_fwd = panel.groupby('date')['forward_return'].mean()

    # 合并DIV和市场平均收益
    merged = pd.DataFrame({
        'DIV': div_series,
        'mkt_fwd_ret': daily_avg_fwd
    }).dropna()

    if len(merged) < 10:
        return pd.Series(dtype=float)

    # 按月分组计算时间序列IC
    merged['month'] = merged.index.to_period('M')
    monthly_ics = []
    for month, group in merged.groupby('month'):
        if len(group) < 5:
            continue
        ic = group['DIV'].rank().corr(group['mkt_fwd_ret'].rank())
        if not np.isnan(ic):
            monthly_ics.append(pd.Series([ic], index=[month.to_timestamp()]))

    if monthly_ics:
        return pd.concat(monthly_ics)
    return pd.Series(dtype=float)


def analyze_ic(ic_series, factor_name, direction='greed'):
    """
    分析IC序列, 计算IR和胜率
    IR = IC均值 / IC标准差
    胜率 = IC方向正确的月份占比
    """
    if len(ic_series) == 0:
        return {
            'factor': factor_name,
            'ic_mean': np.nan,
            'ic_std': np.nan,
            'ir': np.nan,
            'ic_win_rate': np.nan,
            'monthly_count': 0,
            'effectiveness': 'N/A (无数据)',
        }

    # ic_series 可能是日频或月频
    # 对于截面因子: ic_series是日频, 需要resample到月频
    # 对于DIV: ic_series已经是月频
    if factor_name != 'DIV':
        monthly_ic = ic_series.resample('ME').mean()
        monthly_ic = monthly_ic.dropna()
    else:
        monthly_ic = ic_series

    ic_mean = monthly_ic.mean()
    ic_std = monthly_ic.std()
    ir = ic_mean / ic_std if (ic_std is not None and ic_std > 0) else np.nan

    # 胜率: IC方向正确的月份占比
    if direction == 'greed':
        win_rate = (monthly_ic > 0).mean()
    else:  # fear
        win_rate = (monthly_ic < 0).mean()

    # 有效性判定 (检查方向)
    if pd.isna(ir):
        effectiveness = 'N/A'
    else:
        # 判断方向是否正确
        if direction == 'greed':
            direction_correct = ir > 0
        else:  # fear
            direction_correct = ir < 0

        if abs(ir) > 0.3:
            effectiveness = '有效' if direction_correct else '方向相反(需检查)'
        elif abs(ir) > 0.1:
            effectiveness = '弱有效' if direction_correct else '弱有效(方向相反)'
        else:
            effectiveness = '无效'

    return {
        'factor': factor_name,
        'ic_mean': ic_mean,
        'ic_std': ic_std,
        'ir': ir,
        'ic_win_rate': win_rate,
        'monthly_count': len(monthly_ic),
        'effectiveness': effectiveness,
    }


# ==================== 主流程 ====================

def main():
    start_time = time.time()

    print("=" * 70)
    print("板块因子 IC/IR 有效性验证 (Step 1 重验: MOM 60日 + ADR 加权版)")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 1. 获取板块列表
    sectors = get_sector_list()

    # 2. 拉取所有板块历史数据
    print(f"\n拉取 {len(sectors)} 个板块近 {LOOKBACK_DAYS} 天日线数据...")
    all_data = []
    success_count = 0
    for i, s in enumerate(sectors):
        print(f"  [{i + 1}/{len(sectors)}] {s['code']} {s['name']}...", end=' ', flush=True)
        df = fetch_sector_hist(s['code'], s['name'])
        if df is not None:
            all_data.append(df)
            success_count += 1
            print(f"OK ({len(df)} rows)")
        else:
            print("FAIL")

    print(f"\n成功获取: {success_count}/{len(sectors)} 个板块")

    if success_count < 10:
        print("[FATAL] 成功板块数过少, 无法进行有效验证")
        return

    # 3. 合并为panel数据
    panel = pd.concat(all_data, ignore_index=True)
    print(f"\nPanel数据: {len(panel)} rows, {panel['sector_code'].nunique()} sectors")
    print(f"日期范围: {panel['date'].min().date()} ~ {panel['date'].max().date()}")

    # 4. 计算每个板块的6个因子
    print("\n计算6个板块因子 (MOM/VOL/RSI/NHNL/ADR/TURN)...")
    factor_parts = []
    for code, group in panel.groupby('sector_code'):
        factor_parts.append(compute_factors(group))
    panel_with_factors = pd.concat(factor_parts, ignore_index=True)

    # 5. 计算前瞻收益
    print(f"计算 {FORWARD_PERIOD} 日前瞻收益...")
    panel_with_factors = compute_forward_returns(panel_with_factors, FORWARD_PERIOD)

    # 6. 计算DIV因子
    print("计算DIV因子(跨板块分歧度)...")
    div_series, panel_with_sentiment = compute_div_factor(panel_with_factors)
    print(f"  DIV序列长度: {len(div_series)}")

    # 7. 计算各因子的IC/IR
    print("\n" + "=" * 70)
    print("IC/IR 分析结果")
    print("=" * 70)

    results = []
    factor_cols = ['MOM', 'VOL', 'RSI', 'NHNL', 'ADR', 'TURN']

    for factor_name in factor_cols:
        print(f"  计算 {factor_name} IC...", end=' ', flush=True)
        ic_series = compute_cross_sectional_ic(panel_with_factors, factor_name)
        result = analyze_ic(ic_series, factor_name, FACTOR_DIRECTIONS[factor_name])
        results.append(result)
        print(f"IR={result['ir']:.4f}" if not pd.isna(result['ir']) else "IR=N/A")

    # DIV特殊处理
    print("  计算 DIV IC...", end=' ', flush=True)
    div_ic = compute_div_ic(panel_with_factors, div_series)
    div_result = analyze_ic(div_ic, 'DIV', FACTOR_DIRECTIONS['DIV'])
    results.append(div_result)
    print(f"IR={div_result['ir']:.4f}" if not pd.isna(div_result['ir']) else "IR=N/A")

    # 8. 输出结果表格
    print("\n" + "=" * 70)
    print(f"{'因子':<8} {'方向':<6} {'IC均值':>10} {'IC标准差':>10} {'IR':>8} {'胜率':>8} {'月数':>6} {'有效性':>16}")
    print("-" * 80)
    for r in results:
        ic_mean_str = f"{r['ic_mean']:.4f}" if not pd.isna(r['ic_mean']) else "N/A"
        ic_std_str = f"{r['ic_std']:.4f}" if not pd.isna(r['ic_std']) else "N/A"
        ir_str = f"{r['ir']:.4f}" if not pd.isna(r['ir']) else "N/A"
        wr_str = f"{r['ic_win_rate']:.2%}" if not pd.isna(r['ic_win_rate']) else "N/A"
        print(f"{r['factor']:<8} {FACTOR_DIRECTIONS[r['factor']]:<6} {ic_mean_str:>10} {ic_std_str:>10} {ir_str:>8} {wr_str:>8} {r['monthly_count']:>6} {r['effectiveness']:>16}")

    # 9. 详细分析
    print("\n" + "=" * 70)
    print("详细分析")
    print("=" * 70)
    for r in results:
        print(f"\n[{r['factor']}] 方向: {FACTOR_DIRECTIONS[r['factor']]}")
        print(f"  IC均值:   {r['ic_mean']:.4f}" if not pd.isna(r['ic_mean']) else "  IC均值:   N/A")
        print(f"  IC标准差: {r['ic_std']:.4f}" if not pd.isna(r['ic_std']) else "  IC标准差: N/A")
        print(f"  IR:       {r['ir']:.4f}" if not pd.isna(r['ir']) else "  IR:       N/A")
        print(f"  胜率:     {r['ic_win_rate']:.2%}" if not pd.isna(r['ic_win_rate']) else "  胜率:     N/A")
        print(f"  月数:     {r['monthly_count']}")
        print(f"  有效性:   {r['effectiveness']}")

    # 10. 整体结论
    print("\n" + "=" * 70)
    print("整体结论")
    print("=" * 70)
    effective = [r for r in results if r['effectiveness'] == '有效']
    weak = [r for r in results if r['effectiveness'] == '弱有效']
    weak_wrong_dir = [r for r in results if r['effectiveness'] == '弱有效(方向相反)']
    wrong_dir = [r for r in results if r['effectiveness'] == '方向相反(需检查)']
    invalid = [r for r in results if r['effectiveness'] == '无效']
    na = [r for r in results if r['effectiveness'].startswith('N/A')]

    print(f"有效因子          ({len(effective)}): {[r['factor'] for r in effective]}")
    print(f"弱有效因子        ({len(weak)}): {[r['factor'] for r in weak]}")
    print(f"弱有效(方向相反)  ({len(weak_wrong_dir)}): {[r['factor'] for r in weak_wrong_dir]}")
    print(f"方向相反(需检查)  ({len(wrong_dir)}): {[r['factor'] for r in wrong_dir]}")
    print(f"无效因子          ({len(invalid)}): {[r['factor'] for r in invalid]}")
    if na:
        print(f"无法判定          ({len(na)}): {[r['factor'] for r in na]}")

    # 替代建议: 无效 + 方向相反
    need_fix = invalid + wrong_dir + weak_wrong_dir
    if need_fix:
        print("\n[需调整因子及建议]")
        for r in need_fix:
            print(f"  {r['factor']} ({r['effectiveness']}): {SUGGESTIONS.get(r['factor'], '需要进一步研究替代方案')}")

    # 可落地性判定
    # 方向相反的因子可以通过翻转方向使用, 算入可用因子
    usable_count = len(effective) + len(weak) + len(weak_wrong_dir) + len(wrong_dir)
    correct_dir_count = len(effective) + len(weak)
    total_count = len(results)
    print(f"\n方案可落地性:")
    print(f"  方向正确且有效: {correct_dir_count}/{total_count}")
    print(f"  有alpha(含方向相反可翻转): {usable_count}/{total_count}")
    if correct_dir_count >= 5:
        print("  [PASS] 7因子方案整体可落地(方向正确)")
    elif usable_count >= 5:
        print("  [PASS] 因子方案可落地, 但需调整部分因子方向")
    elif usable_count >= 3:
        print("  [WARN] 部分因子需调整后方案可落地")
    else:
        print("  [FAIL] 因子方案需大幅调整")

    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f}s")

    # 保存结果
    result_df = pd.DataFrame(results)
    result_df.to_csv('/opt/fund-sentiment/v5-deploy/backend/scripts/factor_ic_results.csv', index=False)
    print(f"结果已保存: backend/scripts/factor_ic_results.csv")


if __name__ == '__main__':
    main()
