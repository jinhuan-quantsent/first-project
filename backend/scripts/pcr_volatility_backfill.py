"""
PCR 认沽认购比因子 — 波动率近似法回填
由于 Tushare opt_daily 需要 2000+积分，东方财富 push2 在 ECS 不可用，
用波动率近似法从已有 VOL 数据回填 PCR 历史数据。

公式: PCR ≈ 0.6 + (VOL - 20) * 0.02
其中 VOL 是年化波动率(%)

用法: cd backend && python scripts/pcr_volatility_backfill.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, timedelta
from sqlalchemy import select, func as sa_func
from app.core.config import settings
from app.core.database import init_db, close_db, get_session_factory
from app.models.factor_history import FactorHistory
from app.engine.factor_history import FactorHistoryStore, _normalize_code

MAIN_INDEXES = ["SH000001", "SH000300", "SZ399001", "SZ399006"]
LOOKBACK_DAYS = 1260  # 5年


async def backfill_pcr_from_vol():
    """从已有 VOL 数据计算 PCR 近似值并写入 factor_history"""
    await init_db()
    print("✅ 数据库初始化完成")

    session_factory = get_session_factory()
    store = FactorHistoryStore()

    total_inserted = 0

    for index_code in MAIN_INDEXES:
        ts_code = _normalize_code(index_code)
        cutoff_date = date.today() - timedelta(days=LOOKBACK_DAYS)
        cutoff = cutoff_date.strftime("%Y-%m-%d")

        async with session_factory() as session:
            # 1. 获取该指数的所有 VOL 历史数据
            stmt = (
                select(FactorHistory.trade_date, FactorHistory.raw_value)
                .where(
                    FactorHistory.index_code == ts_code,
                    FactorHistory.factor_name == "VOL",
                    FactorHistory.trade_date >= cutoff,
                )
                .order_by(FactorHistory.trade_date.asc())
            )
            result = await session.execute(stmt)
            vol_data = [(str(row[0]), float(row[1])) for row in result.all()]

            if not vol_data:
                print(f"⚠️ {index_code}: 无 VOL 数据，跳过")
                continue

            # 2. 检查已有哪些 PCR 数据（避免重复）
            existing_stmt = (
                select(FactorHistory.trade_date)
                .where(
                    FactorHistory.index_code == ts_code,
                    FactorHistory.factor_name == "PCR",
                )
            )
            existing_result = await session.execute(existing_stmt)
            existing_dates = set(str(row[0]) for row in existing_result.all())

            # 3. 计算 PCR 近似值
            records = []
            for td, vol_value in vol_data:
                if td in existing_dates:
                    continue  # 跳过已有数据的日期

                # PCR ≈ 0.6 + (VOL - 20) * 0.02
                # VOL 是年化波动率(%), 通常范围 10-40
                pcr = 0.6 + (vol_value - 20.0) * 0.02
                pcr = max(0.1, min(5.0, pcr))  # 合理范围约束
                records.append((ts_code, "PCR", td, round(pcr, 4)))

            if not records:
                print(f"✅ {index_code}: PCR 数据已存在，无需回填")
                continue

            # 4. 批量插入
            count = await store.insert_batch(session, records)
            # ⚠️ insert_batch 只创建 SAVEPOINT，必须显式 commit 才能写入数据库
            await session.commit()
            total_inserted += count
            print(f"✅ {index_code}: 回填 {count} 条 PCR 记录 (VOL数据: {len(vol_data)}条)")

    await close_db()
    print(f"\n🎉 PCR 波动率近似回填完成！总计插入 {total_inserted} 条记录")


if __name__ == "__main__":
    asyncio.run(backfill_pcr_from_vol())
