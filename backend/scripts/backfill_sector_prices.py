#!/usr/bin/env python3
"""
T5: 申万一级行业指数日线数据回填脚本

使用 AKShare 的 index_hist_sw() 拉取 31 个申万一级行业指数日线数据，
写入 sector_price 表。支持重复运行（INSERT ... ON DUPLICATE KEY UPDATE）。

用法:
    cd /opt/fund-sentiment/v5-deploy
    backend/venv/bin/python backend/scripts/backfill_sector_prices.py

    # 仅回填最近 N 天
    backend/venv/bin/python backend/scripts/backfill_sector_prices.py --days 30

    # 指定单个板块
    backend/venv/bin/python backend/scripts/backfill_sector_prices.py --sector 801050
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

import akshare as ak
import pandas as pd
from sqlalchemy import create_engine, text

# ============================================================
# 配置
# ============================================================

# 阿里云 RDS MySQL 连接
DB_URL = (
    "mysql+pymysql://Jin0220:Jinhuan0220@"
    "rm-bp1iqpeh04issog45uo.mysql.rds.aliyuncs.com:3306/"
    "fund_sentiment?charset=utf8mb4"
)

# 31 个申万一级行业（代码, 名称）
SW_L1_SECTORS = [
    ("801010", "农林牧渔"),
    ("801030", "基础化工"),
    ("801040", "钢铁"),
    ("801050", "有色金属"),
    ("801080", "电子"),
    ("801110", "家用电器"),
    ("801120", "食品饮料"),
    ("801130", "纺织服饰"),
    ("801140", "轻工制造"),
    ("801150", "医药生物"),
    ("801160", "公用事业"),
    ("801170", "交通运输"),
    ("801180", "房地产"),
    ("801200", "商贸零售"),
    ("801210", "社会服务"),
    ("801230", "综合"),
    ("801710", "建筑材料"),
    ("801720", "建筑装饰"),
    ("801730", "电力设备"),
    ("801740", "国防军工"),
    ("801750", "计算机"),
    ("801760", "传媒"),
    ("801770", "通信"),
    ("801780", "银行"),
    ("801790", "非银金融"),
    ("801880", "汽车"),
    ("801890", "机械设备"),
    ("801950", "煤炭"),
    ("801960", "石油石化"),
    ("801970", "环保"),
    ("801980", "美容护理"),
]

# 每个请求间隔（秒），避免 AKShare 限流
REQUEST_INTERVAL = 1.0


def fetch_sector_daily(sector_code: str) -> pd.DataFrame:
    """用 AKShare 拉取申万一级行业指数日线数据。

    index_hist_sw 返回全历史数据，列名为中文：
      代码, 日期, 收盘, 开盘, 最高, 最低, 成交量, 成交额
    """
    df = ak.index_hist_sw(symbol=sector_code, period="day")
    if df is None or df.empty:
        return pd.DataFrame()

    # 重命名列
    col_map = {
        "日期": "trade_date",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
    }
    df = df.rename(columns=col_map)

    # 转换日期
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    # 计算涨跌幅
    df = df.sort_values("trade_date").reset_index(drop=True)
    df["pct_change"] = df["close"].pct_change() * 100
    df["pct_change"] = df["pct_change"].round(4)

    # 第一条 pct_change 为 NaN，设为 0
    df["pct_change"] = df["pct_change"].fillna(0)

    return df[["trade_date", "open", "high", "low", "close", "volume", "amount", "pct_change"]]


def insert_to_db(engine, df: pd.DataFrame, sector_code: str, sector_name: str) -> int:
    """将日线数据插入 sector_price 表，返回插入/更新行数。"""
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "sector_code": sector_code,
            "sector_name": sector_name,
            "trade_date": row["trade_date"],
            "open": float(row["open"]) if pd.notna(row["open"]) else None,
            "high": float(row["high"]) if pd.notna(row["high"]) else None,
            "low": float(row["low"]) if pd.notna(row["low"]) else None,
            "close": float(row["close"]) if pd.notna(row["close"]) else None,
            "volume": int(row["volume"]) if pd.notna(row["volume"]) else None,
            "amount": float(row["amount"]) if pd.notna(row["amount"]) else None,
            "pct_change": float(row["pct_change"]) if pd.notna(row["pct_change"]) else None,
        })

    sql = text("""
        INSERT INTO sector_price
            (sector_code, sector_name, trade_date, open, high, low, close, volume, amount, pct_change)
        VALUES
            (:sector_code, :sector_name, :trade_date, :open, :high, :low, :close, :volume, :amount, :pct_change)
        ON DUPLICATE KEY UPDATE
            sector_name = VALUES(sector_name),
            open = VALUES(open),
            high = VALUES(high),
            low = VALUES(low),
            close = VALUES(close),
            volume = VALUES(volume),
            amount = VALUES(amount),
            pct_change = VALUES(pct_change)
    """)

    with engine.begin() as conn:
        conn.execute(sql, rows)

    return len(rows)


def backfill(
    engine,
    sectors: list[tuple[str, str]],
    days: int | None = None,
) -> dict:
    """批量回填板块日线数据。

    Args:
        engine: SQLAlchemy engine
        sectors: [(code, name), ...]
        days: 只回填最近 N 天，None 表示全量

    Returns:
        统计字典
    """
    total = len(sectors)
    success = 0
    failed = 0
    total_rows = 0
    errors = []

    cutoff_date = None
    if days:
        cutoff_date = date.today() - timedelta(days=days)

    for i, (code, name) in enumerate(sectors, 1):
        print(f"[{i}/{total}] 拉取 {code} {name} ...", end=" ", flush=True)
        try:
            df = fetch_sector_daily(code)

            if df.empty:
                print("无数据")
                failed += 1
                errors.append(f"{code} {name}: 无数据")
                continue

            # 按日期过滤
            if cutoff_date:
                df = df[df["trade_date"] >= cutoff_date]

            if df.empty:
                print(f"过滤后无数据 (cutoff={cutoff_date})")
                failed += 1
                continue

            rows = insert_to_db(engine, df, code, name)
            total_rows += rows
            success += 1
            date_range = f"{df['trade_date'].min()} ~ {df['trade_date'].max()}"
            print(f"写入 {rows} 条 ({date_range})")

        except Exception as e:
            print(f"失败: {e}")
            failed += 1
            errors.append(f"{code} {name}: {e}")

        # 请求间隔
        if i < total:
            time.sleep(REQUEST_INTERVAL)

    stats = {
        "total": total,
        "success": success,
        "failed": failed,
        "total_rows": total_rows,
        "errors": errors,
    }
    return stats


def main():
    parser = argparse.ArgumentParser(description="回填申万一级行业指数日线数据")
    parser.add_argument("--days", type=int, default=None, help="只回填最近 N 天")
    parser.add_argument("--sector", type=str, default=None, help="只回填指定板块代码")
    args = parser.parse_args()

    # 选择板块
    sectors = SW_L1_SECTORS
    if args.sector:
        sectors = [(c, n) for c, n in SW_L1_SECTORS if c == args.sector]
        if not sectors:
            print(f"未找到板块代码: {args.sector}")
            sys.exit(1)

    print(f"=== 申万一级行业日线数据回填 ===")
    print(f"板块数量: {len(sectors)}")
    print(f"回填范围: {'最近 ' + str(args.days) + ' 天' if args.days else '全量'}")
    print()

    engine = create_engine(DB_URL, pool_pre_ping=True)

    stats = backfill(engine, sectors, days=args.days)

    print()
    print(f"=== 回填完成 ===")
    print(f"成功: {stats['success']}/{stats['total']}")
    print(f"失败: {stats['failed']}")
    print(f"总写入行数: {stats['total_rows']}")
    if stats["errors"]:
        print(f"错误详情:")
        for err in stats["errors"]:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
