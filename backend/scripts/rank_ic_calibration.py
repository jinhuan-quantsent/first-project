#!/usr/bin/env python3
"""
二期主题指数 Rank IC 权重校准评估

对比一期(申万一级)和二期(主题指数)的因子Rank IC,
评估二期是否需要独立权重校准。

Rank IC = Spearman秩相关(因子值, 未来1日收益)
IR = mean(IC) / std(IC)
"""
import sys
sys.path.insert(0, '/opt/fund-sentiment/v5-deploy/backend')

import asyncio
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import text
from app.core.database import init_db, close_db, get_session_factory

# 因子方向: greed=高值看多, fear=高值看空
FACTOR_DIRECTIONS = {
    'VOL': 'greed',
    'RSI': 'greed',
    'NHNL': 'greed',
    'TURN': 'fear',
}

# 当前权重 (一期=二期)
CURRENT_WEIGHTS = {
    'TURN': 0.28,
    'VOL': 0.25,
    'NHNL': 0.20,
    'RSI': 0.15,
    'DIV': 0.12,
}

# 一期板块代码 (31个申万一级)
SW_CODES = [f'801{i:03d}' for i in [10,30,40,50,80,110,120,130,140,150,160,170,180,200,
    210,230,710,720,730,740,750,760,770,780,790,880,890,950,960,970,980]]

# 二期主题指数代码
THEME_CODES = [
    '000814','000849','000813','000152','399394','931494','931160',
    '930653','931152','930903','000995','399358','931151',
    '000136','931877','931079','931039',
]


async def load_factor_data(session, index_codes, factor_name):
    """从factor_history加载因子数据"""
    codes_str = "','".join(index_codes)
    sql = text(f"""
        SELECT index_code, trade_date, raw_value
        FROM factor_history
        WHERE index_code IN ('{codes_str}')
          AND factor_name = :fn
        ORDER BY index_code, trade_date
    """)
    result = await session.execute(sql, {'fn': factor_name})
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=['index_code', 'trade_date', 'raw_value'])
    df['trade_date'] = df['trade_date'].astype(str)
    df['raw_value'] = pd.to_numeric(df['raw_value'], errors='coerce')
    return df


async def load_div_data(session, index_codes):
    """加载DIV数据"""
    codes_str = "','".join(index_codes)
    sql = text(f"""
        SELECT index_code, trade_date, raw_value
        FROM factor_history
        WHERE index_code IN ('{codes_str}')
          AND factor_name = 'DIV'
        ORDER BY index_code, trade_date
    """)
    result = await session.execute(sql)
    rows = result.fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=['index_code', 'trade_date', 'raw_value'])
    df['trade_date'] = df['trade_date'].astype(str)
    df['raw_value'] = pd.to_numeric(df['raw_value'], errors='coerce')
    return df


def compute_rank_ic(factor_df, returns_df, factor_name):
    """
    计算Rank IC: 每日截面Spearman秩相关(因子值, 未来1日收益)
    factor_df: index_code, trade_date, raw_value
    returns_df: index_code, trade_date, forward_return
    """
    # 合并
    merged = pd.merge(
        factor_df[['index_code', 'trade_date', 'raw_value']],
        returns_df[['index_code', 'trade_date', 'forward_return']],
        on=['index_code', 'trade_date'],
        how='inner'
    )
    merged = merged.dropna()

    if len(merged) < 100:
        return [], 0, 0

    # 按日期分组计算截面Rank IC
    ic_series = []
    for date, group in merged.groupby('trade_date'):
        if len(group) < 5:  # 至少5个标的才有意义
            continue
        ic, _ = stats.spearmanr(group['raw_value'], group['forward_return'])
        if not np.isnan(ic):
            ic_series.append((date, ic))

    if not ic_series:
        return [], 0, 0

    ics = np.array([x[1] for x in ic_series])
    mean_ic = np.mean(ics)
    std_ic = np.std(ics)
    ir = mean_ic / std_ic if std_ic > 0 else 0

    return ic_series, mean_ic, ir


async def fetch_forward_returns(session, index_codes):
    """从factor_history获取收盘价并计算前向收益"""
    # 因子表里没有收盘价, 我们用AKShare获取
    import akshare as ak

    all_returns = []
    for code in index_codes:
        try:
            if code.startswith('801'):
                # 一期: 申万行业指数
                df = ak.index_hist_sw(symbol=code)
                if df is None or df.empty:
                    continue
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
                df['date'] = df['date'].astype(str)
                df = df.sort_values('date')
            else:
                # 二期: 主题指数
                from datetime import date, timedelta
                end = date.today().strftime('%Y%m%d')
                start = (date.today() - timedelta(days=720)).strftime('%Y%m%d')
                df = ak.index_zh_a_hist(symbol=code, period='daily',
                                        start_date=start, end_date=end)
                if df is None or df.empty:
                    continue
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
                df['date'] = df['date'].astype(str)
                df = df.sort_values('date')

            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            df['forward_return'] = df['close'].shift(-1) / df['close'] - 1
            df['index_code'] = code
            all_returns.append(df[['index_code', 'date', 'forward_return']].rename(columns={'date': 'trade_date'}))
        except Exception as e:
            print(f'  ERR {code}: {e}')

    if not all_returns:
        return pd.DataFrame()
    return pd.concat(all_returns, ignore_index=True)


async def main():
    await init_db()
    sf = get_session_factory()

    print('=' * 70)
    print('Rank IC 权重校准评估 (一期 vs 二期)')
    print('=' * 70)

    async with sf() as session:
        # 1. 获取前向收益
        print('\n## 1. 获取前向收益数据')
        print('  一期 (31个申万一级)...')
        sw_returns = await fetch_forward_returns(session, SW_CODES)
        print(f'  一期: {len(sw_returns)} 条, {sw_returns["index_code"].nunique() if len(sw_returns)>0 else 0} 个指数')

        print('  二期 (17个主题指数)...')
        theme_returns = await fetch_forward_returns(session, THEME_CODES)
        print(f'  二期: {len(theme_returns)} 条, {theme_returns["index_code"].nunique() if len(theme_returns)>0 else 0} 个指数')

        # 2. 计算各因子Rank IC
        print('\n## 2. 因子 Rank IC 对比')
        print(f'{"因子":<8} {"一期IC":>10} {"一期IR":>10} {"二期IC":>10} {"二期IR":>10} {"方向":>6} {"差异":>10}')
        print('-' * 70)

        results = {}
        for factor_name in ['VOL', 'RSI', 'NHNL', 'TURN', 'DIV']:
            # 一期
            if factor_name == 'DIV':
                sw_factor_df = await load_div_data(session, ['SW_L1_DIV'])
                # DIV是市场级, 对所有板块相同, 无法做截面IC
                # 改为时间序列IC: DIV vs 平均收益
                if len(sw_factor_df) > 0 and len(sw_returns) > 0:
                    avg_ret = sw_returns.groupby('trade_date')['forward_return'].mean().reset_index()
                    merged = pd.merge(sw_factor_df[['trade_date','raw_value']],
                                    avg_ret[['trade_date','forward_return']],
                                    on='trade_date', how='inner').dropna()
                    if len(merged) > 30:
                        ic, _ = stats.spearmanr(merged['raw_value'], merged['forward_return'])
                        sw_ic, sw_ir = ic, 0
                    else:
                        sw_ic, sw_ir = 0, 0
                else:
                    sw_ic, sw_ir = 0, 0
            else:
                sw_factor_df = await load_factor_data(session, SW_CODES, factor_name)
                _, sw_ic, sw_ir = compute_rank_ic(sw_factor_df, sw_returns, factor_name)

            # 二期
            if factor_name == 'DIV':
                theme_factor_df = await load_div_data(session, THEME_CODES)
                if len(theme_factor_df) > 0 and len(theme_returns) > 0:
                    avg_ret = theme_returns.groupby('trade_date')['forward_return'].mean().reset_index()
                    merged = pd.merge(theme_factor_df[['trade_date','raw_value']],
                                    avg_ret[['trade_date','forward_return']],
                                    on='trade_date', how='inner').dropna()
                    if len(merged) > 30:
                        ic, _ = stats.spearmanr(merged['raw_value'], merged['forward_return'])
                        theme_ic, theme_ir = ic, 0
                    else:
                        theme_ic, theme_ir = 0, 0
                else:
                    theme_ic, theme_ir = 0, 0
            else:
                theme_factor_df = await load_factor_data(session, THEME_CODES, factor_name)
                _, theme_ic, theme_ir = compute_rank_ic(theme_factor_df, theme_returns, factor_name)

            direction = FACTOR_DIRECTIONS.get(factor_name, '?')
            diff = theme_ic - sw_ic if factor_name != 'DIV' else 0
            print(f'{factor_name:<8} {sw_ic:>10.4f} {sw_ir:>10.4f} {theme_ic:>10.4f} {theme_ir:>10.4f} {direction:>6} {diff:>+10.4f}')

            results[factor_name] = {
                'sw_ic': sw_ic, 'sw_ir': sw_ir,
                'theme_ic': theme_ic, 'theme_ir': theme_ir,
                'direction': direction,
            }

        # 3. 权重校准建议
        print('\n## 3. 权重校准建议')
        print(f'  当前权重: {CURRENT_WEIGHTS}')

        # 基于IR的权重建议 (abs(IR)归一化)
        abs_irs = {f: abs(results[f]['theme_ir']) for f in ['VOL','RSI','NHNL','TURN']}
        total_ir = sum(abs_irs.values())
        if total_ir > 0:
            suggested_weights = {f: abs_irs[f] / total_ir for f in abs_irs}
            # DIV保持固定权重
            div_w = 0.12
            remaining = 1 - div_w
            for f in suggested_weights:
                suggested_weights[f] = suggested_weights[f] * remaining
            suggested_weights['DIV'] = div_w

            print(f'\n  基于二期IR的权重建议:')
            print(f'  {"因子":<8} {"当前权重":>10} {"建议权重":>10} {"变化":>10}')
            print('  ' + '-' * 40)
            for f in ['TURN','VOL','NHNL','RSI','DIV']:
                curr = CURRENT_WEIGHTS[f]
                sugg = suggested_weights.get(f, 0)
                change = sugg - curr
                print(f'  {f:<8} {curr:>10.2%} {sugg:>10.2%} {change:>+10.2%}')

            # 判断是否需要校准
            max_change = max(abs(suggested_weights[f] - CURRENT_WEIGHTS[f]) for f in CURRENT_WEIGHTS)
            if max_change > 0.08:
                print(f'\n  ⚠️ 最大权重变化 {max_change:.1%} > 8%, 建议校准')
            else:
                print(f'\n  ✅ 最大权重变化 {max_change:.1%} ≤ 8%, 无需校准')
        else:
            print('  ⚠️ 所有因子IR为0, 无法计算建议权重')

    await close_db()

    print('\n' + '=' * 70)
    print('评估完成')
    print('=' * 70)


if __name__ == '__main__':
    asyncio.run(main())
