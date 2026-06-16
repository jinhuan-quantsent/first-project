"""
因子历史数据回填脚本 — V5.0

用法:
    cd backend
    python -m scripts.backfill_factor_history [--index-code SH000300] [--lookback-days 1260] [--factors ETF,POS,PCR,NEWF] [--all]

功能:
    1. 回填缺失的4个因子（ETF/POS/PCR/NEWF）的历史数据
    2. 也支持回填全部11因子+COMPOSITE+CLOSE
    3. 自动限流，避免Tushare API被ban

注意事项:
    - Tushare 2000积分下:
      - fund_daily: OK (120积分)
      - fund_nav: OK (120积分)
      - fund_basic: OK (120积分)
      - opt_daily: 可能受限 (需2000+积分，限流更严格)
    - 回填5年数据约需10-30分钟，取决于API响应速度
    - 脚本支持断点续填（已存在的记录会被自动跳过）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# 确保 app 包可导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import tushare as ts

from app.core.config import settings
from app.core.database import init_db, close_db, get_session
from app.engine.factor_history import FactorHistoryStore, V5_FACTOR_META, _normalize_code


# 限流控制：Tushare API 调用间隔（秒）
API_CALL_INTERVAL = 0.3  # 每次API调用间隔0.3秒，避免触发限流


async def backfill_etf(
    store: FactorHistoryStore,
    session,
    tushare_pro,
    index_code: str,
    lookback_days: int = 1260,
) -> int:
    """
    回填 ETF 份额变化因子历史数据
    数据源: Tushare fund_daily (510300.SH, 510050.SH)
    计算方式: 近2日 volume变化率 × 价格变化率 → 份额变化率(%)
    """
    end_date = date.today().isoformat().replace("-", "")
    start_date = (date.today() - timedelta(days=lookback_days + 100)).isoformat().replace("-", "")
    ts_code = _normalize_code(index_code)

    etf_codes = ["510300.SH", "510050.SH"]
    records: list[tuple[str, str, str, float]] = []

    for etf_code in etf_codes:
        try:
            print(f"  📊 ETF: 获取 {etf_code} 日线数据...")
            df = tushare_pro.fund_daily(
                ts_code=etf_code,
                start_date=start_date,
                end_date=end_date,
            )
            time.sleep(API_CALL_INTERVAL)

            if df is None or df.empty or len(df) < 2:
                print(f"  ⚠️ {etf_code} 数据不足，跳过")
                continue

            df = df.sort_values("trade_date").reset_index(drop=True)
            # Tushare fund_daily 返回列名是 'vol'，不是 'volume'
            vol_col = "vol" if "vol" in df.columns else "volume"
            vols = df[vol_col].values.astype(float)
            closes = df["close"].values.astype(float)
            pre_closes = df["pre_close"].values.astype(float) if "pre_close" in df.columns else closes
            trade_dates = df["trade_date"].values

            for i in range(1, len(df)):
                vol_today = float(vols[i])
                vol_prev = float(vols[i - 1])
                close = float(closes[i])
                pre_close = float(pre_closes[i])

                if vol_prev > 0 and pre_close > 0:
                    vol_change_rate = vol_today / vol_prev - 1.0
                    price_change_rate = close / pre_close - 1.0
                    change_pct = round((vol_change_rate * price_change_rate) * 100, 4)
                else:
                    change_pct = 0.0

                td = str(trade_dates[i])
                records.append((ts_code, "ETF", td, change_pct))

            print(f"  ✅ {etf_code}: {len(df)} 条ETF因子记录")

        except Exception as e:
            print(f"  ⚠️ {etf_code} 获取失败: {e}")
            time.sleep(1)

    # 多个ETF取平均
    if not records:
        return 0

    # 按 (index_code, trade_date) 分组取平均
    from collections import defaultdict
    grouped: dict[tuple, list[float]] = defaultdict(list)
    for rec in records:
        key = (rec[0], rec[2])  # (ts_code, trade_date)
        grouped[key].append(rec[3])

    avg_records = [
        (key[0], "ETF", key[1], round(sum(vals) / len(vals), 4))
        for key, vals in grouped.items()
    ]

    count = await store.insert_batch(session, avg_records)
    print(f"  ✅ ETF 回填完成: {count} 条平均记录")
    return count


async def backfill_pos(
    store: FactorHistoryStore,
    session,
    tushare_pro,
    index_code: str,
    lookback_days: int = 1260,
) -> int:
    """
    回填 POS 基金仓位估算因子历史数据
    数据源: Tushare fund_nav (110011.OF, 161725.OF) + index_daily
    计算方式: 基金净值变化与沪深300涨跌做回归 → beta ≈ 股票仓位(%)
    """
    end_date = date.today().isoformat().replace("-", "")
    start_date = (date.today() - timedelta(days=lookback_days + 100)).isoformat().replace("-", "")
    ts_code = _normalize_code(index_code)

    # 获取沪深300指数数据
    print(f"  📊 POS: 获取沪深300指数数据...")
    try:
        idx_df = tushare_pro.index_daily(
            ts_code="000300.SH",
            start_date=start_date,
            end_date=end_date,
        )
        time.sleep(API_CALL_INTERVAL)
    except Exception as e:
        print(f"  ⚠️ 获取沪深300数据失败: {e}")
        return 0

    if idx_df is None or idx_df.empty or len(idx_df) < 20:
        print(f"  ⚠️ 沪深300数据不足")
        return 0

    idx_df = idx_df.sort_values("trade_date").reset_index(drop=True)
    idx_returns_map: dict[str, float] = {}
    for i in range(1, len(idx_df)):
        prev_close = float(idx_df.iloc[i - 1]["close"])
        if prev_close > 0:
            td = str(idx_df.iloc[i]["trade_date"])
            idx_returns_map[td] = (float(idx_df.iloc[i]["close"]) - prev_close) / prev_close

    fund_codes = ["110011.OF", "161725.OF"]
    all_pos_records: dict[str, float] = {}  # {trade_date: position_pct}

    for fund_code in fund_codes:
        try:
            print(f"  📊 POS: 获取 {fund_code} 净值数据...")
            nav_df = tushare_pro.fund_nav(
                ts_code=fund_code,
                start_date=start_date,
                end_date=end_date,
            )
            time.sleep(API_CALL_INTERVAL)

            if nav_df is None or nav_df.empty or len(nav_df) < 20:
                print(f"  ⚠️ {fund_code} 净值数据不足")
                continue

            nav_df = nav_df.sort_values("nav_date").reset_index(drop=True)

            # 计算基金日收益率
            fund_returns_map: dict[str, float] = {}
            for i in range(1, len(nav_df)):
                prev_nav = float(nav_df.iloc[i - 1]["unit_nav"])
                if prev_nav > 0:
                    nav_date = str(nav_df.iloc[i]["nav_date"])
                    fund_returns_map[nav_date] = (float(nav_df.iloc[i]["unit_nav"]) - prev_nav) / prev_nav

            # 滚动窗口回归估算仓位（60日窗口）
            common_dates = sorted(set(fund_returns_map.keys()) & set(idx_returns_map.keys()))
            if len(common_dates) < 20:
                continue

            window_size = 60
            pos_estimates: dict[str, float] = {}

            for j in range(window_size, len(common_dates)):
                window_dates = common_dates[j - window_size:j]
                fr = [fund_returns_map[d] for d in window_dates]
                ir = [idx_returns_map[d] for d in window_dates]

                n = len(fr)
                if n < 10:
                    continue

                # OLS: beta = Cov(fund, index) / Var(index)
                mean_fr = sum(fr) / n
                mean_ir = sum(ir) / n
                cov = sum((fr[k] - mean_fr) * (ir[k] - mean_ir) for k in range(n)) / n
                var = sum((ir[k] - mean_ir) ** 2 for k in range(n)) / n

                if var > 1e-12:
                    beta = cov / var
                    beta = max(0.0, min(1.0, beta))
                    pos_pct = round(beta * 100, 2)
                    pos_pct = max(10.0, min(99.0, pos_pct))
                    # 使用窗口末尾日期
                    td = common_dates[j]
                    pos_estimates[td] = pos_pct

            # 合并多个基金估算结果（取平均）
            for td, pos in pos_estimates.items():
                if td in all_pos_records:
                    all_pos_records[td] = (all_pos_records[td] + pos) / 2
                else:
                    all_pos_records[td] = pos

            print(f"  ✅ {fund_code}: {len(pos_estimates)} 个仓位估算点")

        except Exception as e:
            print(f"  ⚠️ {fund_code} 获取失败: {e}")
            time.sleep(1)

    if not all_pos_records:
        return 0

    records = [(ts_code, "POS", td, pos) for td, pos in sorted(all_pos_records.items())]
    count = await store.insert_batch(session, records)
    print(f"  ✅ POS 回填完成: {count} 条记录")
    return count


async def backfill_pcr(
    store: FactorHistoryStore,
    session,
    tushare_pro,
    index_code: str,
    lookback_days: int = 1260,
) -> int:
    """
    回填 PCR 认沽认购比因子历史数据
    数据源: Tushare opt_daily
    计算方式: 认沽成交量 / 认购成交量

    ⚠️ 注意: opt_daily 对积分要求高(2000+)，限流严格
    回填5年需~1260次API调用，建议分批执行
    """
    ts_code = _normalize_code(index_code)
    records: list[tuple[str, str, str, float]] = []

    # 逐日查询期权数据（opt_daily 不支持大范围查询）
    end = date.today()
    start = end - timedelta(days=lookback_days + 100)
    current = start

    total_days = (end - start).days
    processed = 0
    success = 0
    failed = 0

    print(f"  📊 PCR: 开始逐日查询 ({start} ~ {end})...")

    while current <= end:
        td_str = current.strftime("%Y%m%d")
        processed += 1

        if processed % 50 == 0:
            print(f"  📊 PCR 进度: {processed}/{total_days} 天 (成功:{success} 失败:{failed})")

        try:
            df = tushare_pro.opt_daily(trade_date=td_str)
            time.sleep(API_CALL_INTERVAL)

            if df is None or df.empty:
                current += timedelta(days=1)
                continue

            # 识别认沽/认购
            put_mask = None
            call_mask = None

            if "option_type" in df.columns:
                put_mask = df["option_type"].isin(["认沽", "put", "P"])
                call_mask = df["option_type"].isin(["认购", "call", "C"])
            elif "contract_type" in df.columns:
                put_mask = df["contract_type"].isin(["认沽", "put", "P"])
                call_mask = df["contract_type"].isin(["认购", "call", "C"])

            if put_mask is not None and call_mask is not None:
                put_vol = float(df.loc[put_mask, "volume"].sum())
                call_vol = float(df.loc[call_mask, "volume"].sum())
                if call_vol > 0:
                    pcr = put_vol / call_vol
                    pcr = max(0.1, min(5.0, pcr))
                    records.append((ts_code, "PCR", td_str, round(pcr, 4)))
                    success += 1

        except Exception as e:
            failed += 1
            if "limit" in str(e).lower() or "429" in str(e):
                print(f"  ⚠️ PCR: 限流，等待60秒... ({e})")
                time.sleep(60)
            elif failed <= 3:
                print(f"  ⚠️ PCR {td_str}: {e}")
            time.sleep(1)

        current += timedelta(days=1)

    if not records:
        print(f"  ⚠️ PCR: 未获取到任何数据")
        return 0

    count = await store.insert_batch(session, records)
    print(f"  ✅ PCR 回填完成: {count} 条记录 (成功:{success} 失败:{failed})")
    return count


async def backfill_newf(
    store: FactorHistoryStore,
    session,
    tushare_pro,
    index_code: str,
    lookback_days: int = 1260,
) -> int:
    """
    回填 NEWF 新发基金热度因子历史数据
    数据源: Tushare fund_basic
    计算方式: 统计近30日新成立基金总份额(亿份)

    策略: 获取全量fund_basic，按found_date滑动窗口计算
    """
    ts_code = _normalize_code(index_code)
    records: list[tuple[str, str, str, float]] = []

    for mkt in ["O", "E"]:
        try:
            print(f"  📊 NEWF: 获取 {mkt} 市场基金基础数据...")
            df = tushare_pro.fund_basic(market=mkt)
            time.sleep(API_CALL_INTERVAL)

            if df is None or df.empty:
                continue

            # 找到日期列
            date_col = "found_date" if "found_date" in df.columns else "list_date"
            if date_col not in df.columns:
                continue

            # 过滤有效日期
            df_valid = df[df[date_col].notna()].copy()
            if df_valid.empty:
                continue

            dates_sorted = sorted(df_valid[date_col].unique())

            # 获取起止范围内的日期
            start_date_str = (date.today() - timedelta(days=lookback_days + 100)).strftime("%Y%m%d")
            end_date_str = date.today().strftime("%Y%m%d")
            target_dates = [d for d in dates_sorted if start_date_str <= str(d) <= end_date_str]

            # 对每个交易日计算近30日新发基金热度
            for td in target_dates:
                td_str = str(td)
                # 近30日窗口
                cutoff_str = str(int(td_str) - 10000)  # 近似30天前的日期（简化）
                # 更精确：用timedelta
                try:
                    td_date = date(int(td_str[:4]), int(td_str[4:6]), int(td_str[6:8]))
                except ValueError:
                    continue
                cutoff_date = td_date - timedelta(days=30)
                cutoff_str2 = cutoff_date.strftime("%Y%m%d")

                recent = df_valid[
                    (df_valid[date_col] >= cutoff_str2) & (df_valid[date_col] <= td_str)
                ]

                total_count = len(recent)
                if total_count == 0:
                    continue

                if "fund_shares" in recent.columns:
                    total_shares = float(recent["fund_shares"].sum())
                    # fund_shares 单位通常为万份，转为亿份
                    heat_value = round(total_shares / 10000, 2)
                else:
                    # 用基金数量近似估算（每只基金约5亿份经验值）
                    heat_value = round(total_count * 5.0, 2)

                records.append((ts_code, "NEWF", td_str, heat_value))

            print(f"  ✅ {mkt} 市场: {len(target_dates)} 个日期点")

        except Exception as e:
            print(f"  ⚠️ fund_basic({mkt}) 获取失败: {e}")
            time.sleep(1)

    if not records:
        return 0

    # 去重：同一 (ts_code, trade_date) 可能有 O 和 E 两个市场的数据，取平均
    from collections import defaultdict
    grouped: dict[tuple, list[float]] = defaultdict(list)
    for rec in records:
        key = (rec[0], rec[2])
        grouped[key].append(rec[3])

    avg_records = [
        (key[0], "NEWF", key[1], round(sum(vals) / len(vals), 4))
        for key, vals in grouped.items()
    ]

    count = await store.insert_batch(session, avg_records)
    print(f"  ✅ NEWF 回填完成: {count} 条记录")
    return count


async def run_backfill(
    index_codes: list[str],
    factors: list[str],
    lookback_days: int = 1260,
) -> None:
    """执行回填"""
    # 初始化数据库
    await init_db()
    print("✅ 数据库初始化完成")

    # 初始化 Tushare
    if not settings.TUSHARE_TOKEN:
        print("❌ TUSHARE_TOKEN 未配置，无法回填")
        return

    pro = ts.pro_api(settings.TUSHARE_TOKEN)

    # 测试连接
    try:
        pro.trade_cal(exchange="SSE", start_date="20260101", end_date="20260105")
        print("✅ Tushare 连接正常")
    except Exception as e:
        print(f"❌ Tushare 连接失败: {e}")
        return

    store = FactorHistoryStore()

    # 支持的回填因子
    BACKFILL_FUNCS = {
        "ETF": backfill_etf,
        "POS": backfill_pos,
        "PCR": backfill_pcr,
        "NEWF": backfill_newf,
    }

    # 原有7因子通过 backfill_from_tushare 回填
    ORIGINAL_FACTORS = {"VOL", "ADR", "NHNL", "TURN", "ERP", "FLOW", "NBF"}

    # 使用 get_session 获取数据库会话
    session_gen = get_session()
    session = await session_gen.__anext__()

    try:
        for index_code in index_codes:
            print(f"\n{'='*60}")
            print(f"🔄 开始回填指数: {index_code}")
            print(f"{'='*60}")

            # 1. 先回填原有7因子（如果需要）
            if any(f in factors for f in ORIGINAL_FACTORS):
                print(f"\n📊 回填原有7因子 (VOL/ADR/NHNL/TURN/ERP/FLOW/NBF) + CLOSE...")
                try:
                    count = await store.backfill_from_tushare(
                        session, index_code, pro, lookback_days=lookback_days,
                    )
                    print(f"✅ 原有7因子回填: {count} 条")
                except Exception as e:
                    print(f"⚠️ 原有7因子回填失败: {e}")

            # 2. 回填新增4因子
            for factor_name in factors:
                if factor_name in ORIGINAL_FACTORS:
                    continue  # 已由 backfill_from_tushare 处理

                func = BACKFILL_FUNCS.get(factor_name)
                if func is None:
                    print(f"⚠️ 未知因子: {factor_name}，跳过")
                    continue

                print(f"\n📊 回填因子: {factor_name}...")
                try:
                    count = await func(store, session, pro, index_code, lookback_days)
                    print(f"✅ {factor_name} 回填: {count} 条")
                except Exception as e:
                    print(f"⚠️ {factor_name} 回填失败: {e}")
                    import traceback
                    traceback.print_exc()
    finally:
        await session_gen.aclose()
        await close_db()

    print(f"\n{'='*60}")
    print("🎉 回填流程完成！")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="因子历史数据回填脚本 V5.0")
    parser.add_argument(
        "--index-code",
        type=str,
        default=None,
        help="指数代码（如 SH000300），不指定则回填全部4个指数",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=1260,
        help="回填天数（默认1260，即5年×252交易日）",
    )
    parser.add_argument(
        "--factors",
        type=str,
        default="ETF,POS,NEWF",
        help="要回填的因子（逗号分隔），默认 ETF,POS,NEWF（跳过PCR因其积分要求高）",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="回填全部11因子+CLOSE",
    )
    parser.add_argument(
        "--include-pcr",
        action="store_true",
        help="包含PCR因子回填（注意：需要2000+积分，且耗时很长）",
    )

    args = parser.parse_args()

    # 确定指数列表
    if args.index_code:
        index_codes = [args.index_code]
    else:
        index_codes = ["SH000001", "SH000300", "SZ399001", "SZ399006"]

    # 确定因子列表
    if args.all:
        factors = ["VOL", "ADR", "NHNL", "TURN", "ERP", "FLOW", "NBF",
                    "ETF", "POS", "PCR", "NEWF"]
    else:
        factors = [f.strip().upper() for f in args.factors.split(",")]
        if args.include_pcr and "PCR" not in factors:
            factors.append("PCR")

    print(f"📋 回填配置:")
    print(f"  指数: {index_codes}")
    print(f"  因子: {factors}")
    print(f"  回填天数: {args.lookback_days}")
    print()

    asyncio.run(run_backfill(index_codes, factors, args.lookback_days))


if __name__ == "__main__":
    main()
