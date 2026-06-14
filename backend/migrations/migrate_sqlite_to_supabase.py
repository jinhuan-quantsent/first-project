"""
数据迁移脚本：SQLite → Supabase PostgreSQL
断点续传，COUNT + 抽样校验

用法：
  python -m migrations.migrate_sqlite_to_supabase

前提：
  1. .env 已配置 SUPABASE_URL, SUPABASE_DB_PASSWORD
  2. 本地 SQLite 文件存在且可读
"""
import asyncio
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402


# ============================================================
# 配置
# ============================================================
SQLITE_PATH = settings.SQLITE_PATH
BATCH_SIZE = 1000

# 需要迁移的表（从 SQLite 读取）
TABLES_TO_MIGRATE = [
    "factor_history",
]

# 合法列名字符：仅允许字母、数字、下划线
_SAFE_COL_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _validate_table_name(table_name: str) -> str:
    """白名单校验表名，仅允许 TABLES_TO_MIGRATE 中存在的值。

    表名/列名无法使用 SQL 参数化占位符（语法限制），
    因此采用白名单方式防范 SQL 注入，这是业界标准做法。
    """
    if table_name not in TABLES_TO_MIGRATE:
        raise ValueError(
            f"非法表名 '{table_name}'，不在白名单 TABLES_TO_MIGRATE 中。"
            f"允许的表: {TABLES_TO_MIGRATE}"
        )
    return table_name


def _sanitize_col_names(columns: list[str]) -> list[str]:
    """正则过滤列名，仅允许 [a-zA-Z0-9_] 字符。

    列名来自 cursor.description（SQLite 元数据），理论上可信但不应信任：
    如果迁移源被篡改，恶意列名可能注入 SQL。
    """
    safe: list[str] = []
    for col in columns:
        if not _SAFE_COL_PATTERN.match(col):
            raise ValueError(
                f"非法列名 '{col}'，仅允许字母、数字、下划线字符"
            )
        safe.append(col)
    return safe


# ============================================================
# 辅助函数
# ============================================================
async def get_pg_connection():
    """获取 asyncpg 连接"""
    import asyncpg

    url = settings.supabase_db_url
    # asyncpg 不支持 postgresql+asyncpg:// 前缀
    conn_url = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(conn_url)
    return conn


def get_sqlite_connection():
    """获取 SQLite 连接"""
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def backup_sqlite():
    """备份 SQLite 文件"""
    backup_path = SQLITE_PATH + ".bak"
    shutil.copy2(SQLITE_PATH, backup_path)
    print(f"✅ SQLite 备份完成: {backup_path}")
    return backup_path


async def ensure_migration_log(conn):
    """创建迁移日志表"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS _migration_log (
            table_name VARCHAR(50) PRIMARY KEY,
            total_count INTEGER NOT NULL DEFAULT 0,
            migrated_count INTEGER NOT NULL DEFAULT 0,
            last_migrated_id INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'pending',
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            error_message TEXT DEFAULT ''
        )
    """)
    await conn.execute("COMMIT")


async def get_migration_progress(conn, table_name: str):
    """读取迁移进度"""
    row = await conn.fetchrow(
        "SELECT * FROM _migration_log WHERE table_name = $1", table_name
    )
    if row:
        return dict(row)
    return None


async def update_migration_progress(conn, table_name: str, migrated_count: int, total_count: int, status: str = "in_progress"):
    await conn.execute(
        """
        INSERT INTO _migration_log (table_name, total_count, migrated_count, status, started_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (table_name) DO UPDATE SET
            migrated_count = EXCLUDED.migrated_count,
            total_count = EXCLUDED.total_count,
            status = EXCLUDED.status
        """,
        table_name, total_count, migrated_count, status,
    )
    await conn.execute("COMMIT")


async def migrate_table(pg_conn, table_name: str):
    """迁移单张表"""
    # 白名单校验表名（防 SQL 注入）
    table_name = _validate_table_name(table_name)

    print(f"\n{'='*60}")
    print(f"开始迁移表: {table_name}")
    print(f"{'='*60}")

    # 1. 读取 SQLite 数据
    sqlite_conn = get_sqlite_connection()
    try:
        sqlite_conn.row_factory = sqlite3.Row
        cursor = sqlite_conn.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
        total_count = cursor.fetchone()["cnt"]

        if total_count == 0:
            print(f"⚠️ 表 {table_name} 无数据，跳过")
            return True

        print(f"📊 SQLite 表 {table_name} 共 {total_count} 条记录")

        # 获取列名（正则过滤，防 SQL 注入）
        col_cursor = sqlite_conn.execute(f"SELECT * FROM {table_name} LIMIT 1")
        columns = _sanitize_col_names([desc[0] for desc in col_cursor.description])
        print(f"📋 列: {', '.join(columns)}")

        # 2. 读取 PG 迁移进度
        progress = await get_migration_progress(pg_conn, table_name)
        offset = 0
        if progress and progress.get("migrated_count", 0) > 0:
            offset = progress["migrated_count"]
            print(f"🔄 从断点续传: 已迁移 {offset}/{total_count}")

        if offset >= total_count:
            print(f"✅ 表 {table_name} 已完成迁移 ({total_count} 条)")
            return True

        # 3. 逐批迁移
        # col_names 已通过 _sanitize_col_names 过滤，安全拼接
        col_names = ", ".join(columns)
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))

        migrated = offset
        while offset < total_count:
            cursor = sqlite_conn.execute(
                f"SELECT {col_names} FROM {table_name} ORDER BY id LIMIT {BATCH_SIZE} OFFSET {offset}"
            )
            rows = cursor.fetchall()

            if not rows:
                break

            values_list = [tuple(row[col] for col in columns) for row in rows]

            await pg_conn.executemany(
                # col_names 已过滤，table_name 已白名单校验；值用 $1,$2,... 占位符，安全
                f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders}) "
                f"ON CONFLICT DO NOTHING",
                values_list,
            )
            await pg_conn.execute("COMMIT")

            offset += len(rows)
            migrated = offset
            print(f"  ✅ 已迁移 {migrated}/{total_count} ({migrated*100//total_count}%)")

            await update_migration_progress(pg_conn, table_name, migrated, total_count)

    finally:
        sqlite_conn.close()

    # 4. 标记完成
    await update_migration_progress(pg_conn, table_name, total_count, total_count, "completed")
    print(f"✅ 表 {table_name} 迁移完成: {total_count} 条")
    return True


async def verify_migration(pg_conn):
    """COUNT + 抽样校验"""
    print(f"\n{'='*60}")
    print("校验阶段")
    print(f"{'='*60}")

    sqlite_conn = get_sqlite_connection()
    try:
        all_pass = True
        for table_name in TABLES_TO_MIGRATE:
            # 白名单校验表名（防 SQL 注入）
            _validate_table_name(table_name)

            # SQLite COUNT
            sl_cursor = sqlite_conn.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
            sl_count = sl_cursor.fetchone()["cnt"]

            # PG COUNT
            pg_count = await pg_conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")

            match = "✅" if sl_count == pg_count else "❌"
            print(f"  {match} {table_name}: SQLite={sl_count}, PG={pg_count}")

            if sl_count != pg_count:
                all_pass = False
                continue

            # 抽样校验（取 10 条）
            if sl_count > 0:
                sample_cursor = sqlite_conn.execute(
                    f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT 10"
                )
                samples = sample_cursor.fetchall()
                columns = _sanitize_col_names([desc[0] for desc in sample_cursor.description])

                for sample in samples:
                    row_id = sample["id"]
                    pg_row = await pg_conn.fetchrow(
                        f"SELECT * FROM {table_name} WHERE id = $1", row_id
                    )
                    if pg_row is None:
                        print(f"    ❌ ID={row_id} 在 PG 中不存在")
                        all_pass = False
                        continue

                    for col in ["index_code", "factor_name", "trade_date", "raw_value"]:
                        if col in columns:
                            sl_val = sample[col]
                            pg_val = dict(pg_row).get(col)
                            if sl_val != pg_val:
                                print(f"    ❌ ID={row_id} {col} 不匹配: SQLite={sl_val}, PG={pg_val}")
                                all_pass = False

        return all_pass
    finally:
        sqlite_conn.close()


async def main():
    print("=" * 60)
    print("基金情绪分析系统 - 数据迁移工具")
    print(f"SQLite → Supabase PostgreSQL")
    print(f"时间: {datetime.now().isoformat()}")
    print("=" * 60)

    # 前置检查
    if not os.path.exists(SQLITE_PATH):
        print(f"❌ SQLite 文件不存在: {SQLITE_PATH}")
        sys.exit(1)

    backup_sqlite()

    # 连接 Supabase
    try:
        pg_conn = await get_pg_connection()
        print("✅ Supabase PG 连接成功")
    except Exception as e:
        print(f"❌ Supabase PG 连接失败: {e}")
        sys.exit(1)

    try:
        # 创建迁移日志表
        await ensure_migration_log(pg_conn)

        # 确保 PG 表存在
        for table_name in TABLES_TO_MIGRATE:
            if table_name == "factor_history":
                await pg_conn.execute("""
                    CREATE TABLE IF NOT EXISTS factor_history (
                        id SERIAL PRIMARY KEY,
                        index_code VARCHAR(20) NOT NULL,
                        factor_name VARCHAR(20) NOT NULL,
                        trade_date VARCHAR(10) NOT NULL,
                        raw_value DOUBLE PRECISION NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(index_code, factor_name, trade_date)
                    )
                """)
                await pg_conn.execute("COMMIT")

        # 迁移
        for table_name in TABLES_TO_MIGRATE:
            await migrate_table(pg_conn, table_name)

        # 校验
        all_pass = await verify_migration(pg_conn)

        if all_pass:
            print("\n" + "=" * 60)
            print("🎉 迁移完成，校验全部通过！")
            print("=" * 60)
            print("提示: 在 .env 中设置 USE_POSTGRES=true 以切换到 PG")
        else:
            print("\n⚠️ 校验发现差异，请检查")

    finally:
        await pg_conn.close()


if __name__ == "__main__":
    asyncio.run(main())
