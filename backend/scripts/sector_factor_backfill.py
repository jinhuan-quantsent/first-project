#!/usr/bin/env python3
"""
板块因子数据回填脚本 (Step 1 - 任务B)
将 31 个申万一级行业的因子数据回填到 factor_history 表

因子清单 (Step 1 确认后):
  VOL   - 20日年化波动率 (方向: greed)
  RSI   - 14日RSI (方向: greed)
  NHNL  - 20日新高新低净占比 (方向: greed)
  TURN  - 成交额相对强度 (方向: fear)
  DIV   - 跨板块分歧度 (市场级, 最后计算)

跳过的因子 (Step 1 重验未通过):
  MOM   - 60日动量 IR=0.0526 < 0.1 无效
  ADR   - 成交额加权涨跌比 IR=0.0392 < 0.1 无效
"""

import sys
import os
import time
import warnings
import numpy as np
import pandas as pd
import pymysql
import akshare as ak
from datetime import datetime

warnings.filterwarnings('ignore')

# ==================== 配置 ====================
LOOKBACK_DAYS = 500       # 约2年交易日

# 因子参数
VOL_WINDOW = 20
RSI_WINDOW = 14
NHNL_WINDOW = 20
TURN_WINDOW = 20

# 数据库配置
DB_CONFIG = {
    'host': 'rm-bp1iqpeh04issog45uo.mysql.rds.aliyuncs.com',
    'port': 3306,
    'user': 'Jin0220',
    'password': 'Jinhuan0220',
    'db': 'fund_sentiment',
    'charset': 'utf8mb4',
}

# 因子方向 (用于DIV情绪分计算)
# greed: 高值 = 高情绪 (直接用rank)
# fear:  高值 = 低情绪 (用1-rank)
FACTOR_DIRECTIONS = {
    'VOL': 'greed',
    'RSI': 'greed',
    'NHNL': 'greed',
    'TURN': 'fear',
}

# 市场级DIV的index_code
DIV_INDEX_CODE = 'SW_L1_DIV'

# 回填的因子列表 (不含DIV, DIV单独处理)
SECTOR_FACTORS = ['VOL', 'RSI', 'NHNL', 'TURN']

BATCH_SIZE = 500  # executemany批量大小


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
        df = df.rename(columns={
            '日期': 'date', '收盘': 'close', '开盘': 'open',
            '最高': 'high', '最低': 'low',
            '成交量': 'volume', '成交额': 'amount'
        })
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        df = df.tail(LOOKBACK_DAYS).reset_index(drop=True)
        df['sector_code'] = code
        df['sector_name'] = name
        return df[['date', 'close', 'volume', 'amount', 'sector_code', 'sector_name']]
    except Exception as e:
        print(f"  [ERROR] {code} {name}: {e}")
        return None


# ==================== 因子计算 ====================

def calc_vol(close, window=20):
    """20日年化波动率 = std(daily_returns) * sqrt(252)"""
    returns = close.pct_change()
    return returns.rolling(window).std() * np.sqrt(252)


def calc_rsi(close, window=14):
    """14日RSI (Wilder平滑法)"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_nhnl(close, window=20):
    """20日新高新低净占比"""
    rolling_max = close.rolling(window).max()
    rolling_min = close.rolling(window).min()
    is_new_high = (close >= rolling_max).astype(float)
    is_new_low = (close <= rolling_min).astype(float)
    nhnl = (is_new_high.rolling(window).sum() - is_new_low.rolling(window).sum()) / window
    return nhnl


def calc_turn(amount, window=20):
    """成交额相对强度: 当日成交额 / 20日均成交额"""
    avg_amount = amount.rolling(window).mean()
    return amount / avg_amount


def compute_factors(df):
    """计算单个板块的4个因子"""
    close = df['close']
    amount = df['amount']

    df = df.copy()
    df['VOL'] = calc_vol(close, VOL_WINDOW)
    df['RSI'] = calc_rsi(close, RSI_WINDOW)
    df['NHNL'] = calc_nhnl(close, NHNL_WINDOW)
    df['TURN'] = calc_turn(amount, TURN_WINDOW)

    return df


def compute_div_factor(panel):
    """
    DIV因子: 跨板块分歧度
    1. 对每个因子做截面rank归一化到[0,1]
    2. 根据方向调整: greed直接用rank, fear用1-rank
    3. 情绪分 = 各因子调整后rank的等权平均
    4. DIV = 每日情绪分的截面标准差
    返回: div_df (date, div_value)
    """
    panel = panel.copy()

    # 截面rank归一化
    for col in SECTOR_FACTORS:
        panel[f'{col}_rank'] = panel.groupby('date')[col].rank(pct=True)
        # fear方向翻转
        if FACTOR_DIRECTIONS[col] == 'fear':
            panel[f'{col}_rank'] = 1.0 - panel[f'{col}_rank']

    rank_cols = [f'{col}_rank' for col in SECTOR_FACTORS]
    panel['sentiment_score'] = panel[rank_cols].mean(axis=1)

    # DIV = 每日情绪分的截面标准差
    div_series = panel.groupby('date')['sentiment_score'].std()
    div_df = div_series.reset_index()
    div_df.columns = ['date', 'div_value']
    div_df = div_df.dropna(subset=['div_value'])

    return div_df


# ==================== 数据库操作 ====================

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


def batch_insert_factors(conn, records):
    """
    批量插入因子记录
    使用 INSERT ... ON DUPLICATE KEY UPDATE 避免重复
    """
    sql = """
        INSERT INTO factor_history (index_code, factor_name, trade_date, raw_value)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE raw_value = VALUES(raw_value)
    """
    cursor = conn.cursor()
    total_inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        cursor.executemany(sql, batch)
        total_inserted += cursor.rowcount
        conn.commit()
    cursor.close()
    return total_inserted


# ==================== 主流程 ====================

def main():
    start_time = time.time()

    print("=" * 70)
    print("板块因子数据回填 (Step 1 - 任务B)")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"回填因子: {SECTOR_FACTORS} + DIV (共{len(SECTOR_FACTORS)+1}个)")
    print(f"跳过因子: MOM (IR=0.0526 无效), ADR (IR=0.0392 无效)")
    print("=" * 70)

    # 1. 获取板块列表
    sectors = get_sector_list()

    # 2. 拉取所有板块历史数据并计算因子
    print(f"\n拉取 {len(sectors)} 个板块近 {LOOKBACK_DAYS} 天数据并计算因子...")
    all_factors = []       # DB写入记录
    all_data = []          # 保留panel数据用于DIV计算
    failed_sectors = []
    success_count = 0

    for i, s in enumerate(sectors):
        print(f"  [{i + 1}/{len(sectors)}] {s['code']} {s['name']}...", end=' ', flush=True)
        df = fetch_sector_hist(s['code'], s['name'])
        if df is None:
            failed_sectors.append(s)
            print("FAIL (数据拉取失败)")
            continue

        # 计算因子
        df = compute_factors(df)
        all_data.append(df)  # 保留用于DIV计算

        # 转换为记录列表
        for _, row in df.iterrows():
            trade_date = row['date'].strftime('%Y-%m-%d')
            for factor_name in SECTOR_FACTORS:
                val = row[factor_name]
                if pd.notna(val) and np.isfinite(val):
                    all_factors.append((s['code'], factor_name, trade_date, float(val)))

        success_count += 1
        print(f"OK ({len(df)} rows, {len(df) * len(SECTOR_FACTORS)} records)")

    print(f"\n成功: {success_count}/{len(sectors)} 个板块")
    if failed_sectors:
        print(f"失败: {len(failed_sectors)} 个: {[(s['code'], s['name']) for s in failed_sectors]}")

    if success_count < 10:
        print("[FATAL] 成功板块数过少, 终止回填")
        return

    # 3. 合并panel数据计算DIV因子
    print("\n计算DIV因子(跨板块分歧度)...")
    panel = pd.concat(all_data, ignore_index=True)
    print(f"  Panel: {len(panel)} rows, {panel['sector_code'].nunique()} sectors")
    print(f"  日期范围: {panel['date'].min().date()} ~ {panel['date'].max().date()}")

    # 计算DIV
    div_df = compute_div_factor(panel)
    print(f"  DIV序列: {len(div_df)} 天")

    # DIV记录
    div_records = []
    for _, row in div_df.iterrows():
        trade_date = row['date'].strftime('%Y-%m-%d')
        div_records.append((DIV_INDEX_CODE, 'DIV', trade_date, float(row['div_value'])))

    # 4. 写入数据库
    print(f"\n写入数据库...")
    print(f"  板块因子记录: {len(all_factors)} 条")
    print(f"  DIV记录: {len(div_records)} 条")
    print(f"  总计: {len(all_factors) + len(div_records)} 条")

    conn = get_db_connection()
    try:
        # 写入板块因子
        print("\n  写入板块因子 (VOL/RSI/NHNL/TURN)...")
        inserted = batch_insert_factors(conn, all_factors)
        print(f"  完成: {inserted} rows affected (含upsert)")

        # 写入DIV
        print(f"  写入DIV因子 ({len(div_records)} 条)...")
        inserted_div = batch_insert_factors(conn, div_records)
        print(f"  完成: {inserted_div} rows affected (含upsert)")

    finally:
        conn.close()

    # 5. 数据完整性检查
    print("\n" + "=" * 70)
    print("数据完整性检查")
    print("=" * 70)

    conn = get_db_connection()
    cursor = conn.cursor()

    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM factor_history WHERE index_code LIKE '801%%' OR index_code = %s", (DIV_INDEX_CODE,))
    total_sector_records = cursor.fetchone()[0]
    print(f"板块因子总记录数: {total_sector_records}")

    # 按因子统计
    print(f"\n{'因子':<8} {'板块数':>6} {'记录数':>8} {'最早日期':>14} {'最晚日期':>14} {'缺失天数':>8}")
    print("-" * 70)

    for factor_name in SECTOR_FACTORS + ['DIV']:
        if factor_name == 'DIV':
            cursor.execute("""
                SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
                FROM factor_history
                WHERE index_code = %s AND factor_name = %s
            """, (DIV_INDEX_CODE, factor_name))
            row = cursor.fetchone()
            record_count = row[0]
            min_date = row[1]
            max_date = row[2]
            sector_count = 1  # DIV是市场级
        else:
            cursor.execute("""
                SELECT COUNT(DISTINCT index_code), COUNT(*), MIN(trade_date), MAX(trade_date)
                FROM factor_history
                WHERE index_code LIKE '801%%' AND factor_name = %s
            """, (factor_name,))
            row = cursor.fetchone()
            sector_count = row[0]
            record_count = row[1]
            min_date = row[2]
            max_date = row[3]

        # 计算缺失天数 (期望记录数 vs 实际)
        if factor_name == 'DIV':
            expected = success_count * 0  # 不适用
            missing = 0
        else:
            # 期望 = 板块数 × 交易日数 (粗略估算)
            cursor.execute("""
                SELECT COUNT(DISTINCT trade_date) FROM factor_history
                WHERE index_code LIKE '801%%' AND factor_name = %s
            """, (factor_name,))
            trading_days = cursor.fetchone()[0]
            expected = sector_count * trading_days
            missing = expected - record_count

        print(f"{factor_name:<8} {sector_count:>6} {record_count:>8} {str(min_date):>14} {str(max_date):>14} {missing:>8}")

    # 按板块统计 (抽样5个)
    print(f"\n板块抽样统计 (前5个):")
    print(f"{'板块代码':<12} {'板块名称':<10} {'VOL':>6} {'RSI':>6} {'NHNL':>6} {'TURN':>6}")
    print("-" * 55)

    # 获取前5个板块代码
    cursor.execute("SELECT DISTINCT index_code FROM factor_history WHERE index_code LIKE '801%%' ORDER BY index_code LIMIT 5")
    sample_codes = [row[0] for row in cursor.fetchall()]

    for code in sample_codes:
        counts = {}
        for factor_name in SECTOR_FACTORS:
            cursor.execute("""
                SELECT COUNT(*) FROM factor_history
                WHERE index_code = %s AND factor_name = %s
            """, (code, factor_name))
            counts[factor_name] = cursor.fetchone()[0]

        # 获取板块名称
        sector_name = next((s['name'] for s in sectors if s['code'] == code), '?')
        print(f"{code:<12} {sector_name:<10} {counts['VOL']:>6} {counts['RSI']:>6} {counts['NHNL']:>6} {counts['TURN']:>6}")

    # DIV记录检查
    cursor.execute("SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM factor_history WHERE index_code = %s AND factor_name = 'DIV'", (DIV_INDEX_CODE,))
    div_info = cursor.fetchone()
    print(f"\nDIV记录: {div_info[0]} 条, 日期范围: {div_info[1]} ~ {div_info[2]}")

    cursor.close()
    conn.close()

    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.1f}s")
    print(f"回填完成: {success_count} 板块 × {len(SECTOR_FACTORS)} 因子 + DIV = {len(all_factors) + len(div_records)} 条记录")


if __name__ == '__main__':
    main()
