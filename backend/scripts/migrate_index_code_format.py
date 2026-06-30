"""
迁移 market_sentiment.index_code 从 Display 格式(SH000300) 到 Tushare 格式(000300.SH)

执行方式：scp 到服务器后 python3 执行

格式映射：
- SH000001 → 000001.SH
- SH000300 → 000300.SH
- SH000016 → 000016.SH
- SZ399001 → 399001.SZ
- SZ399006 → 399006.SZ
"""
import asyncio
import os


DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres.mqictsnguvmxsbwmartd:518011037aA%21@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
)

# Display → Tushare 格式映射
CODE_MAPPING = {
    "SH000001": "000001.SH",
    "SH000300": "000300.SH",
    "SH000016": "000016.SH",
    "SZ399001": "399001.SZ",
    "SZ399006": "399006.SZ",
}


async def migrate():
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy import text

    engine = create_async_engine(DB_URL, echo=False)

    async with engine.begin() as conn:
        # 1. 先检查当前数据格式
        result = await conn.execute(
            text("SELECT DISTINCT index_code FROM market_sentiment ORDER BY index_code")
        )
        existing_codes = [row[0] for row in result.fetchall()]
        print(f"当前 market_sentiment 中的 index_code: {existing_codes}")

        # 2. 统计需要迁移的行数
        total_to_migrate = 0
        for display_code, tushare_code in CODE_MAPPING.items():
            count_result = await conn.execute(
                text("SELECT COUNT(*) FROM market_sentiment WHERE index_code = :display_code"),
                {"display_code": display_code}
            )
            count = count_result.scalar()
            total_to_migrate += count
            print(f"  {display_code} → {tushare_code}: {count} 行")

        if total_to_migrate == 0:
            print("⚠️ 没有需要迁移的数据（可能已经迁移过了）")
            # 检查是否已经是 Tushare 格式
            for tushare_code in CODE_MAPPING.values():
                count_result = await conn.execute(
                    text("SELECT COUNT(*) FROM market_sentiment WHERE index_code = :tushare_code"),
                    {"tushare_code": tushare_code}
                )
                count = count_result.scalar()
                if count > 0:
                    print(f"  ✅ {tushare_code}: 已有 {count} 行（Tushare格式）")
            return

        print(f"\n🔄 开始迁移 {total_to_migrate} 行...")

        # 3. 逐个迁移（避免锁表时间过长）
        migrated = 0
        for display_code, tushare_code in CODE_MAPPING.items():
            result = await conn.execute(
                text("""
                    UPDATE market_sentiment
                    SET index_code = :tushare_code
                    WHERE index_code = :display_code
                """),
                {"tushare_code": tushare_code, "display_code": display_code}
            )
            rows = result.rowcount
            migrated += rows
            print(f"  ✅ {display_code} → {tushare_code}: {rows} 行已迁移")

        print(f"\n🎉 迁移完成！共迁移 {migrated} 行")

        # 4. 验证
        result = await conn.execute(
            text("SELECT DISTINCT index_code FROM market_sentiment ORDER BY index_code")
        )
        new_codes = [row[0] for row in result.fetchall()]
        print(f"迁移后 market_sentiment 中的 index_code: {new_codes}")

        # 5. 检查是否还有 Display 格式的残留
        for display_code in CODE_MAPPING:
            count_result = await conn.execute(
                text("SELECT COUNT(*) FROM market_sentiment WHERE index_code = :display_code"),
                {"display_code": display_code}
            )
            count = count_result.scalar()
            if count > 0:
                print(f"  ⚠️ 仍有 {count} 行 Display 格式: {display_code}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
