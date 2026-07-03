"""
快速回填7因子(VOL/ADR/NHNL/TURN/ERP/FLOW/NBF)+CLOSE
使用直接批量INSERT IGNORE，每批500条，显式commit
"""
import asyncio
import sys
import os
import argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('PYTHONPATH', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import tushare as ts
from sqlalchemy import text
from app.core.config import settings
from app.core.database import init_db, get_session_factory, close_db

API_CALL_INTERVAL = 0.3
BATCH_SIZE = 500

INDEX_CODES = ['000001.SH', '000300.SH', '399001.SZ', '399006.SZ']


async def fast_backfill(index_codes, lookback_days):
    await init_db()
    sf = get_session_factory()
    pro = ts.pro_api(settings.TUSHARE_TOKEN)

    total_inserted = 0
    end_date = date.today().isoformat().replace('-', '')
    start_date = (date.today() - timedelta(days=lookback_days + 100)).isoformat().replace('-', '')

    for index_code in index_codes:
        print(f"\n{'='*60}")
        print(f"🔄 回填指数: {index_code}")
        print(f"{'='*60}")

        # 1. 获取指数日线
        print("📊 获取指数日线数据...")
        df = pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
        if df is None or df.empty:
            print(f"⚠️ index_daily 返回空: {index_code}")
            continue
        df = df.sort_values('trade_date').reset_index(drop=True)
        closes = df['close'].values.astype(float)
        trade_dates = df['trade_date'].values
        print(f"✅ 获取 {len(closes)} 天日线数据")

        # 2. 获取指数基本面（换手率、PE）
        print("📊 获取指数基本面数据...")
        await asyncio.sleep(API_CALL_INTERVAL)
        df_basic = None
        try:
            df_basic = pro.index_dailybasic(ts_code=index_code, start_date=start_date, end_date=end_date)
        except Exception as e:
            print(f"⚠️ index_dailybasic 失败: {e}")

        turnover_map = {}
        pe_map = {}
        if df_basic is not None and not df_basic.empty:
            for _, row in df_basic.iterrows():
                td_raw = str(row.get('trade_date', ''))
                td = f"{td_raw[:4]}-{td_raw[4:6]}-{td_raw[6:8]}" if len(td_raw) == 8 else td_raw
                turnover_map[td] = float(row.get('turnover_rate', 0))
                pe_val = row.get('pe')
                pe_map[td] = float(pe_val) if pe_val else 0
            print(f"✅ 获取 {len(df_basic)} 天基本面数据")

        # 3. 获取融资融券
        print("📊 获取融资融券数据...")
        await asyncio.sleep(API_CALL_INTERVAL)
        df_margin = None
        try:
            df_margin = pro.margin(start_date=start_date, end_date=end_date)
        except Exception:
            pass

        margin_map = {}
        if df_margin is not None and not df_margin.empty:
            for _, row in df_margin.iterrows():
                td_raw = str(row.get('trade_date', ''))
                td = f"{td_raw[:4]}-{td_raw[4:6]}-{td_raw[6:8]}" if len(td_raw) == 8 else td_raw
                margin_map[td] = float(row.get('rzye', 0))
            print(f"✅ 获取 {len(df_margin)} 天融资融券数据")

        # 4. 获取北向资金
        print("📊 获取北向资金数据...")
        await asyncio.sleep(API_CALL_INTERVAL)
        df_flow = None
        try:
            df_flow = pro.moneyflow_hsgt(start_date=start_date, end_date=end_date)
        except Exception:
            pass

        flow_map = {}
        if df_flow is not None and not df_flow.empty:
            for _, row in df_flow.iterrows():
                td_raw = str(row.get('trade_date', ''))
                td = f"{td_raw[:4]}-{td_raw[4:6]}-{td_raw[6:8]}" if len(td_raw) == 8 else td_raw
                flow_map[td] = float(row.get('north_money', 0))
            print(f"✅ 获取 {len(df_flow)} 天北向资金数据")

        # 5. 逐日计算因子
        print("📊 计算因子值...")
        rows = []

        for i in range(len(closes)):
            td_raw = str(trade_dates[i])
            td = f"{td_raw[:4]}-{td_raw[4:6]}-{td_raw[6:8]}" if len(td_raw) == 8 else td_raw

            # CLOSE: 始终存储
            rows.append((index_code, 'CLOSE', td, round(float(closes[i]), 4)))

            if i < 60:
                continue

            window = closes[max(0, i - 60): i + 1]

            # VOL: 年化波动率
            returns = np.diff(window) / window[:-1]
            volatility = round(float(np.std(returns) * np.sqrt(252) * 100), 4)
            rows.append((index_code, 'VOL', td, volatility))

            # ADR: 涨跌比(20日)
            if i >= 21:
                recent = closes[i - 20: i + 1]
                recent_ret = np.diff(recent) / recent[:-1]
                adv = max(float(np.sum(recent_ret > 0)), 1.0)
                dec = max(float(np.sum(recent_ret <= 0)), 1.0)
                adr = round(adv / dec, 4)
            else:
                adr = 1.0
            rows.append((index_code, 'ADR', td, adr))

            # NHNL: 新高占比
            high_60 = float(np.max(window))
            new_high_ratio = round((float(closes[i]) / high_60) * 100, 2)
            rows.append((index_code, 'NHNL', td, new_high_ratio))

            # TURN: 换手率
            turnover = turnover_map.get(td, 0.0)
            rows.append((index_code, 'TURN', td, round(turnover, 4)))

            # ERP: 股债性价比
            pe = pe_map.get(td, 0.0)
            if pe > 0:
                earnings_yield = 100.0 / pe
                bond_yield = 2.8
                erp = round(earnings_yield - bond_yield, 4)
            else:
                erp = 0.0
            rows.append((index_code, 'ERP', td, erp))

            # FLOW: 北向资金净流入
            north_flow = flow_map.get(td, 0.0)
            rows.append((index_code, 'FLOW', td, round(north_flow, 4)))

            # NBF: 融资余额(万→亿)
            margin_bal = margin_map.get(td, 0.0) / 10000.0
            rows.append((index_code, 'NBF', td, round(margin_bal, 4)))

        print(f"✅ 计算 {len(rows)} 条因子记录")

        # 6. 批量INSERT IGNORE (每批500条)
        print("📊 批量写入数据库...")
        inserted = 0
        async with sf() as session:
            for batch_start in range(0, len(rows), BATCH_SIZE):
                batch = rows[batch_start: batch_start + BATCH_SIZE]
                # 构建多行INSERT IGNORE
                value_parts = []
                for r in batch:
                    # 使用参数化避免SQL注入
                    value_parts.append(
                        f"('{r[0]}', '{r[1]}', '{r[2]}', {r[3]}, NOW())"
                    )
                values_sql = ', '.join(value_parts)
                sql = text(
                    "INSERT IGNORE INTO factor_history "
                    "(index_code, factor_name, trade_date, raw_value, created_at) "
                    f"VALUES {values_sql}"
                )
                result = await session.execute(sql)
                inserted += result.rowcount
            await session.commit()

        print(f"✅ {index_code} 回填完成: 新增 {inserted} 条 (总计 {len(rows)} 条)")
        total_inserted += inserted

    await close_db()
    print(f"\n{'='*60}")
    print(f"🎉 全部回填完成! 共新增 {total_inserted} 条记录")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='快速回填7因子+CLOSE')
    parser.add_argument('--index-code', type=str, default=None, help='指数代码(如000001.SH)')
    parser.add_argument('--lookback-days', type=int, default=1260, help='回填天数(默认1260=5年)')
    args = parser.parse_args()

    codes = [args.index_code] if args.index_code else INDEX_CODES
    asyncio.run(fast_backfill(codes, args.lookback_days))


if __name__ == '__main__':
    main()
