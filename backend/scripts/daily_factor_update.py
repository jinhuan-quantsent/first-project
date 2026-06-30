#!/usr/bin/env python3
"""
每日板块因子增量更新脚本 (一期+二期统一)

功能:
  1. 拉取最近60天价格数据 (一期: 申万一级31个 / 二期: 17个主题指数)
  2. 计算 VOL/RSI/NHNL/TURN 四个因子
  3. 计算 DIV 跨板块分歧度 (一期和二期分别计算)
  4. 增量写入 factor_history (INSERT IGNORE, 只补缺失日期)
  5. 刷新相关 Redis 缓存

运行方式:
  cd /opt/fund-sentiment/v5-deploy/backend
  source venv/bin/activate
  python3 scripts/daily_factor_update.py

crontab:
  10 16 * * 1-5 ... python3 scripts/daily_factor_update.py >> /var/log/fund-sentiment/daily_factor.log 2>&1
"""

import sys
import os
import time
import warnings
import numpy as np
import pandas as pd
import akshare as ak

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings('ignore')

# ==================== 配置 ====================
LOOKBACK_DAYS = 60  # 拉取最近60天数据 (足够20日滚动窗口)
BATCH_SIZE = 200

# 因子参数
VOL_WINDOW = 20
RSI_WINDOW = 14
NHNL_WINDOW = 20
TURN_WINDOW = 20

# DB配置 (同步pymysql, 与sector_factor_backfill一致)
DB_CONFIG = {
    'host': 'rm-bp1iqpeh04issog45uo.mysql.rds.aliyuncs.com',
    'port': 3306,
    'user': 'Jin0220',
    'password': 'Jinhuan0220',
    'db': 'fund_sentiment',
    'charset': 'utf8mb4',
}

# 因子方向
FACTOR_DIRECTIONS = {
    'VOL': 'greed',
    'RSI': 'greed',
    'NHNL': 'greed',
    'TURN': 'fear',
}

SECTOR_FACTORS = ['VOL', 'RSI', 'NHNL', 'TURN']

# 二期主题指数映射
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

# 需要刷新的 Redis 缓存 key pattern
REDIS_FLUSH_PATTERNS = [
    'v5:sector:sentiment',
    'v5:sector:radar',
    'v5:pos_rating:all',
    'v5:pos_rating:*',
    'v5:pos_rating_funds:*',
    'v5:recommendations:all',
    'v5:watchlist:*',
    'v5:sectors:*',
]


# ==================== 数据获取 ====================

def get_sw_sector_list():
    """获取申万一级行业列表"""
    df = ak.sw_index_first_info()
    sectors = []
    for _, row in df.iterrows():
        code = str(row['行业代码']).replace('.SI', '')
        name = row['行业名称']
        sectors.append({'code': code, 'name': name})
    return sectors


def fetch_sw_prices(code):
    """获取申万行业指数最近N天数据"""
    try:
        df = ak.index_hist_sw(symbol=code)
        if df is None or df.empty:
            return []
        df = df.rename(columns={
            '日期': 'date', '收盘': 'close',
            '成交量': 'volume', '成交额': 'amount'
        })
        df['date'] = df['date'].astype(str)
        df = df.sort_values('date').tail(LOOKBACK_DAYS)
        return [{'date': r['date'], 'close': float(r['close']),
                 'amount': float(r.get('amount', 0))} for _, r in df.iterrows()]
    except Exception as e:
        print(f'  [ERR] SW {code}: {e}')
        return []


def fetch_theme_prices(code):
    """获取主题指数最近N天数据 (AKShare index_zh_a_hist)"""
    from datetime import date, timedelta
    end = date.today().strftime('%Y%m%d')
    start = (date.today() - timedelta(days=LOOKBACK_DAYS + 30)).strftime('%Y%m%d')
    try:
        df = ak.index_zh_a_hist(symbol=code, period='daily',
                                start_date=start, end_date=end)
        if df is None or df.empty:
            return []
        prices = []
        for _, row in df.iterrows():
            prices.append({
                'date': str(row['日期']),
                'close': float(row['收盘']),
                'amount': float(row.get('成交额', 0)),
            })
        return prices[-LOOKBACK_DAYS:]
    except Exception as e:
        print(f'  [ERR] Theme {code}: {e}')
        return []


# ==================== 因子计算 ====================

def _compute_factor_df(prices):
    """用 pandas 计算完整因子序列, 与 sector_factor_backfill.py 逻辑一致"""
    df = pd.DataFrame(prices)
    df['close'] = df['close'].astype(float)
    df['amount'] = df['amount'].astype(float)
    df = df.sort_values('date').reset_index(drop=True)

    # VOL: 20日年化波动率
    returns = df['close'].pct_change()
    df['VOL'] = returns.rolling(VOL_WINDOW).std() * np.sqrt(252)

    # RSI: 14日RSI (Wilder平滑法)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / RSI_WINDOW, min_periods=RSI_WINDOW, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / RSI_WINDOW, min_periods=RSI_WINDOW, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100.0 - (100.0 / (1.0 + rs))

    # NHNL: 20日新高新低净占比
    rolling_max = df['close'].rolling(NHNL_WINDOW).max()
    rolling_min = df['close'].rolling(NHNL_WINDOW).min()
    is_new_high = (df['close'] >= rolling_max).astype(float)
    is_new_low = (df['close'] <= rolling_min).astype(float)
    df['NHNL'] = (is_new_high.rolling(NHNL_WINDOW).sum() - is_new_low.rolling(NHNL_WINDOW).sum()) / NHNL_WINDOW

    # TURN: 成交额相对强度
    avg_amount = df['amount'].rolling(TURN_WINDOW).mean()
    df['TURN'] = df['amount'] / avg_amount

    return df


def compute_factors(prices):
    """返回最新一天的因子值"""
    if len(prices) < 40:  # NHNL需要2*window
        return None
    df = _compute_factor_df(prices)
    last = df.iloc[-1]
    result = {'date': str(last['date'])}
    for fn in SECTOR_FACTORS:
        val = last[fn]
        if pd.notna(val) and np.isfinite(val):
            result[fn] = float(val)
    return result


def compute_factors_full(prices):
    """返回所有日期的因子值 (用于DIV计算)"""
    if len(prices) < 40:
        return []
    df = _compute_factor_df(prices)
    ts = []
    for _, row in df.iterrows():
        item = {'date': str(row['date'])}
        for fn in SECTOR_FACTORS:
            val = row[fn]
            if pd.notna(val) and np.isfinite(val):
                item[fn] = float(val)
        ts.append(item)
    return ts


def calc_preliminary_score(factors):
    """计算初步情绪分 (用于DIV)"""
    vol = factors.get('VOL', 0.2)
    rsi = factors.get('RSI', 50)
    nhnl = factors.get('NHNL', 0)
    turn = factors.get('TURN', 1.0)

    vol_s = max(0, min(100, (vol - 0.1) / 0.3 * 100))
    nhnl_s = 50 + nhnl * 50
    turn_s = max(0, min(100, (turn - 0.5) / 1.5 * 100))

    return vol_s * 0.25 + rsi * 0.15 + nhnl_s * 0.20 + turn_s * 0.28


def compute_div(all_factors_by_date):
    """
    计算DIV: 每日跨板块情绪分标准差
    all_factors_by_date: {date: {code: factors_dict}}
    返回: {date: div_value}
    """
    div_by_date = {}
    for d, code_factors in all_factors_by_date.items():
        scores = []
        for code, factors in code_factors.items():
            if factors:
                scores.append(calc_preliminary_score(factors))
        if len(scores) >= 3:
            div_by_date[d] = float(np.std(scores))
    return div_by_date


# ==================== 数据库操作 ====================

def get_db():
    import pymysql
    return pymysql.connect(**DB_CONFIG)


def get_existing_dates(conn, index_codes):
    """查询已有最新日期"""
    cursor = conn.cursor()
    codes_str = "','".join(index_codes)
    cursor.execute(
        f"SELECT index_code, MAX(trade_date) FROM factor_history "
        f"WHERE index_code IN ('{codes_str}') GROUP BY index_code"
    )
    result = {}
    for row in cursor.fetchall():
        result[row[0]] = str(row[1]) if row[1] else None
    cursor.close()
    return result


def batch_insert(conn, records):
    """批量插入因子记录 (INSERT IGNORE)"""
    if not records:
        return 0
    cursor = conn.cursor()
    total = 0
    sql = ("INSERT IGNORE INTO factor_history "
           "(factor_name, index_code, trade_date, raw_value, quantile_percentile) "
           "VALUES (%s, %s, %s, %s, 50)")
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i+BATCH_SIZE]
        cursor.executemany(sql, batch)
        total += cursor.rowcount
        conn.commit()
    cursor.close()
    return total


def flush_redis():
    """刷新相关 Redis 缓存"""
    import subprocess
    flushed = 0
    for pattern in REDIS_FLUSH_PATTERNS:
        try:
            result = subprocess.run(
                ['redis-cli', 'KEYS', pattern],
                capture_output=True, text=True, timeout=5
            )
            keys = [k.strip() for k in result.stdout.strip().split('\n') if k.strip()]
            for key in keys:
                subprocess.run(['redis-cli', 'DEL', key], capture_output=True, timeout=5)
                flushed += 1
        except Exception as e:
            print(f'  [WARN] Redis flush {pattern}: {e}')
    return flushed


# ==================== 主流程 ====================

def main():
    start_time = time.time()
    from datetime import datetime
    print('=' * 70)
    print(f'每日板块因子增量更新 ({datetime.now().strftime("%Y-%m-%d %H:%M:%S")})')
    print('=' * 70)

    conn = get_db()

    # ========== 一期: 申万一级行业 ==========
    print('\n## 一期: 申万一级行业指数')
    try:
        sw_sectors = get_sw_sector_list()
        print(f'  板块数: {len(sw_sectors)}')
    except Exception as e:
        print(f'  [FATAL] 获取板块列表失败: {e}')
        sw_sectors = []

    sw_all_ts = {}  # {code: [factors_dict, ...]}
    sw_latest = {}  # {code: latest_factors_dict}
    sw_codes = []

    for i, s in enumerate(sw_sectors):
        code = s['code']
        name = s['name']
        print(f'  [{i+1}/{len(sw_sectors)}] {code} {name}...', end=' ', flush=True)
        prices = fetch_sw_prices(code)
        if not prices:
            print('FAIL (无数据)')
            continue
        sw_codes.append(code)
        ts = compute_factors_full(prices)
        sw_all_ts[code] = ts
        latest = compute_factors(prices)
        if latest:
            sw_latest[code] = latest
        print(f'OK ({len(prices)}d, latest={latest.get("date", "?") if latest else "?"})')
        time.sleep(0.3)  # 避免AKShare频率限制

    # 一期 DIV
    print('\n  计算一期 DIV...')
    sw_by_date = {}
    for code, ts in sw_all_ts.items():
        for item in ts:
            d = item['date']
            if d not in sw_by_date:
                sw_by_date[d] = {}
            sw_by_date[d][code] = item
    sw_div = compute_div(sw_by_date)
    print(f'  DIV: {len(sw_div)} 天, latest={list(sw_div.keys())[-1] if sw_div else "?"}')

    # 一期 DB写入
    sw_records = []
    for code, latest in sw_latest.items():
        td = latest.get('date')
        if not td:
            continue
        for fn in SECTOR_FACTORS:
            val = latest.get(fn)
            if val is not None and np.isfinite(val):
                sw_records.append((fn, code, td, float(val)))
    # DIV记录 (写入SW_L1_DIV占位码)
    if sw_div:
        latest_div_date = max(sw_div.keys())
        sw_records.append(('DIV', 'SW_L1_DIV', latest_div_date, sw_div[latest_div_date]))
    print(f'  一期待写入: {len(sw_records)} 条')
    sw_inserted = batch_insert(conn, sw_records)
    print(f'  一期写入: {sw_inserted} 条 (INSERT IGNORE)')

    # ========== 二期: 主题指数 ==========
    print('\n## 二期: 主题指数')
    theme_all_ts = {}
    theme_latest = {}
    theme_codes = list(TRACK_INDICES.keys())

    for i, (code, name) in enumerate(TRACK_INDICES.items()):
        print(f'  [{i+1}/{len(TRACK_INDICES)}] {code} {name}...', end=' ', flush=True)
        prices = fetch_theme_prices(code)
        if not prices:
            print('FAIL (无数据)')
            continue
        ts = compute_factors_full(prices)
        theme_all_ts[code] = ts
        latest = compute_factors(prices)
        if latest:
            theme_latest[code] = latest
        print(f'OK ({len(prices)}d, latest={latest.get("date", "?") if latest else "?"})')
        time.sleep(0.3)

    # 二期 DIV
    print('\n  计算二期 DIV...')
    theme_by_date = {}
    for code, ts in theme_all_ts.items():
        for item in ts:
            d = item['date']
            if d not in theme_by_date:
                theme_by_date[d] = {}
            theme_by_date[d][code] = item
    theme_div = compute_div(theme_by_date)
    print(f'  DIV: {len(theme_div)} 天, latest={list(theme_div.keys())[-1] if theme_div else "?"}')

    # 二期 DB写入
    theme_records = []
    for code, latest in theme_latest.items():
        td = latest.get('date')
        if not td:
            continue
        for fn in SECTOR_FACTORS:
            val = latest.get(fn)
            if val is not None and np.isfinite(val):
                theme_records.append((fn, code, td, float(val)))
    # DIV写入每个主题指数 (二期每个track都存DIV, 与level2_backfill一致)
    if theme_div:
        latest_div_date = max(theme_div.keys())
        latest_div_val = theme_div[latest_div_date]
        for code in theme_latest:
            theme_records.append(('DIV', code, latest_div_date, latest_div_val))
    print(f'  二期待写入: {len(theme_records)} 条')
    theme_inserted = batch_insert(conn, theme_records)
    print(f'  二期写入: {theme_inserted} 条 (INSERT IGNORE)')

    conn.close()

    # ========== 刷新Redis缓存 ==========
    print('\n## 刷新 Redis 缓存')
    flushed = flush_redis()
    print(f'  清除 {flushed} 个缓存key')

    # ========== 汇总 ==========
    elapsed = time.time() - start_time
    print('\n' + '=' * 70)
    print(f'每日因子更新完成 | 耗时: {elapsed:.1f}s')
    print(f'  一期: {len(sw_latest)}/{len(sw_sectors)} 板块, 写入 {sw_inserted} 条')
    print(f'  二期: {len(theme_latest)}/{len(TRACK_INDICES)} 指数, 写入 {theme_inserted} 条')
    print(f'  Redis: 清除 {flushed} 个key')
    print('=' * 70)


if __name__ == '__main__':
    main()
