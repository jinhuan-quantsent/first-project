"""
P4-1: Supabase Postgres 真实集成测试

背景：阶段 1-3 所有测试在 SQLite 上通过，但生产用 Supabase Postgres。
本测试在 Supabase 远程 Postgres 上验证 SQL 兼容性 + 事务隔离 + 性能特征。

策略：使用专用 test schema 隔离测试数据，避免污染生产表。
- 每个测试用独立 schema (test_xxx_随机)
- 测试结束 DROP SCHEMA 清理
- USE_POSTGRES=true 时执行
- USE_POSTGRES=false 时自动 skip（CI 兼容）

运行方式：
    # 真实 Supabase 集成测试
    USE_POSTGRES=true pytest tests/test_p4_1_postgres_integration.py -v

    # 跳过（CI 默认）
    pytest tests/  # 自动 skip
"""
import os
import uuid
import asyncio
import time
from datetime import date
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


# ============================================================
# 1. 配置与连接
# ============================================================

def _postgres_url() -> str:
    """构造 Supabase Postgres 异步连接 URL

    优先级：
    1. DATABASE_URL（直接 Postgres 完整 URL）
    2. SUPABASE_DB_HOST + SUPABASE_DB_PASSWORD（推荐：pooler 主机）
    3. SUPABASE_URL + SUPABASE_DB_PASSWORD（自动推断直连域名 db.<ref>.supabase.co）

    **Supavisor 关键参数**：
    - 直连模式（db.<ref>.supabase.co）：无需特殊参数
    - 池化模式（pooler host）：需要 prepared_statement_cache_size=0
    """
    # 1) 优先用完整 DATABASE_URL
    db_url = os.getenv("DATABASE_URL", "")
    if db_url and "asyncpg" in db_url:
        return _append_pooler_params(db_url)
    if db_url and db_url.startswith("postgresql://"):
        return _append_pooler_params(db_url.replace("postgresql://", "postgresql+asyncpg://", 1))

    # 2) 推荐：显式 DB host
    db_host = os.getenv("SUPABASE_DB_HOST", "")
    db_port = os.getenv("SUPABASE_DB_PORT", "5432")
    db_password = os.getenv("SUPABASE_DB_PASSWORD", "")

    if not db_host:
        # 3) 兜底：从 SUPABASE_URL 推断 project ref，用直连域名
        supabase_url = os.getenv("SUPABASE_URL", "")
        if supabase_url:
            from urllib.parse import urlparse
            parsed = urlparse(supabase_url)
            project_ref = parsed.hostname.split(".")[0] if parsed.hostname else ""
            if project_ref:
                db_host = f"db.{project_ref}.supabase.co"  # 直连域名

    if db_host and db_password:
        from urllib.parse import quote
        encoded_pwd = quote(db_password, safe="")
        url = f"postgresql+asyncpg://postgres:{encoded_pwd}@{db_host}:{db_port}/postgres"
        return _append_pooler_params(url)

    return ""


def _append_pooler_params(url: str) -> str:
    """为 Supavisor 池化 URL 添加必要参数

    - prepared_statement_cache_size=0：禁用 prepared statement 缓存
    - 直连 URL（db.<ref>.supabase.co）无需此参数
    """
    if "pooler" in url and "prepared_statement_cache_size" not in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}prepared_statement_cache_size=0"
    return url


def _is_postgres_enabled() -> bool:
    """是否启用 Postgres 测试（默认关闭，避免 CI 强依赖网络）"""
    return (
        os.getenv("USE_POSTGRES", "false").lower() == "true"
        and bool(_postgres_url())
    )


# Skip 所有测试（如未启用 Postgres）
pytestmark = [
    pytest.mark.skipif(
        not _is_postgres_enabled(),
        reason="USE_POSTGRES not enabled (set USE_POSTGRES=true to run real Supabase tests)",
    ),
    # pytest-asyncio 1.4+ strict mode 需要显式标记
    pytest.mark.asyncio,
]


# ============================================================
# 2. 隔离测试 Schema Fixture
# ============================================================

@pytest_asyncio.fixture
async def pg_schema() -> AsyncGenerator[str, None]:
    """
    为每个测试创建独立 Postgres schema，测试结束自动清理
    schema 命名：test_<uuid8> 避免冲突
    """
    schema_name = f"test_{uuid.uuid4().hex[:8]}"
    engine = create_async_engine(_postgres_url(), echo=False)

    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))

    try:
        yield schema_name
    finally:
        async with engine.begin() as conn:
            # 强制清理（即使有残留对象）
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await engine.dispose()


@pytest_asyncio.fixture
async def pg_engine():
    """Supabase Postgres 异步引擎（仅连接，不创建 schema）"""
    engine = create_async_engine(_postgres_url(), echo=False, pool_size=2)
    try:
        yield engine
    finally:
        await engine.dispose()


# ============================================================
# 3. 基础连接测试
# ============================================================

class TestPostgresConnection:
    """验证 Supabase Postgres 连接 + 版本 + schema 列表"""

    async def test_connect_and_version(self, pg_engine):
        """测试 1：能连上 Supabase 且拿到版本号"""
        async with pg_engine.connect() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            assert version is not None
            assert "PostgreSQL" in version
            # Supabase 当前用 PostgreSQL 15+
            assert any(v in version for v in ["PostgreSQL 15", "PostgreSQL 16", "PostgreSQL 17"]), \
                f"Unexpected version: {version}"

    async def test_server_time(self, pg_engine):
        """测试 2：服务器时间（验证非缓存连接）"""
        async with pg_engine.connect() as conn:
            result = await conn.execute(text("SELECT NOW()"))
            server_time = result.scalar()
            assert server_time is not None
            # 与本地时间差距 < 60s
            import datetime
            local_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            diff = abs((server_time.replace(tzinfo=None) - local_time).total_seconds())
            assert diff < 60, f"Server time diff too large: {diff}s"

    async def test_user_permissions(self, pg_engine):
        """测试 3：当前用户有 CREATE / DROP / INSERT 权限"""
        async with pg_engine.connect() as conn:
            # 测试事务内权限（不会真正提交）
            async with conn.begin():
                await conn.execute(text("CREATE TEMP TABLE _perm_test (id INT)"))
                await conn.execute(text("INSERT INTO _perm_test VALUES (1)"))
                await conn.execute(text("SELECT COUNT(*) FROM _perm_test"))
                await conn.execute(text("DROP TABLE _perm_test"))
            # 不抛错 = 权限足够


# ============================================================
# 4. JSONB 字段测试（核心功能）
# ============================================================

class TestPostgresJSONB:
    """验证 JSONB 字段读写（14 因子 scores 存储）"""

    async def test_jsonb_insert_and_query(self, pg_schema):
        """测试 4：JSONB 字段插入 + 查询"""
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'''
                    CREATE TABLE "{pg_schema}".factor_scores (
                        id SERIAL PRIMARY KEY,
                        fund_code TEXT NOT NULL,
                        trade_date DATE NOT NULL,
                        scores JSONB NOT NULL,
                        total_score NUMERIC(5, 2)
                    )
                '''))

                # 插入 14 因子 JSONB 数据
                scores_json = '{"limit_up": 0.75, "north_flow": 0.62, "rsi": 0.45}'
                await conn.execute(
                    text(f'''
                        INSERT INTO "{pg_schema}".factor_scores
                        (fund_code, trade_date, scores, total_score)
                        VALUES (:code, :date, CAST(:scores AS JSONB), :total)
                    '''),
                    {"code": "000001", "date": date(2026, 6, 17), "scores": scores_json, "total": 0.61},
                )

                # 查询 + 提取 JSONB 字段
                result = await conn.execute(
                    text(f'SELECT scores, total_score FROM "{pg_schema}".factor_scores WHERE fund_code = :code'),
                    {"code": "000001"},
                )
                row = result.fetchone()
                assert row is not None
                scores = row[0]
                total = row[1]

                # JSONB 字段可以直接当字典访问
                assert scores["limit_up"] == 0.75
                assert scores["north_flow"] == 0.62
                assert float(total) == 0.61
        finally:
            await engine.dispose()

    async def test_jsonb_contains_operator(self, pg_schema):
        """测试 5：JSONB @> 包含操作符（GIN 索引友好）"""
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'''
                    CREATE TABLE "{pg_schema}".events (
                        id SERIAL PRIMARY KEY,
                        event_type TEXT,
                        payload JSONB
                    )
                '''))
                # 插入多条
                await conn.execute(text(f'''
                    INSERT INTO "{pg_schema}".events (event_type, payload) VALUES
                    ('buy', '{{"ticker": "AAPL", "qty": 100}}'),
                    ('sell', '{{"ticker": "TSLA", "qty": 50}}'),
                    ('buy', '{{"ticker": "AAPL", "qty": 200}}')
                '''))

                # 用 @> 查询 ticker = AAPL 的所有 buy 事件
                result = await conn.execute(text(f'''
                    SELECT COUNT(*) FROM "{pg_schema}".events
                    WHERE event_type = 'buy'
                      AND payload @> '{{"ticker": "AAPL"}}'
                '''))
                count = result.scalar()
                assert count == 2, f"Expected 2 AAPL buy events, got {count}"
        finally:
            await engine.dispose()


# ============================================================
# 5. 批量插入性能测试（pg_insert 关键路径）
# ============================================================

class TestPostgresBatchInsert:
    """验证 pg_insert 性能（阶段 1 关键路径）"""

    async def test_batch_insert_100_rows(self, pg_schema):
        """测试 6：100 行批量插入 < 1s（pg_insert 性能基线）"""
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'''
                    CREATE TABLE "{pg_schema}".daily_snapshots (
                        id SERIAL PRIMARY KEY,
                        fund_code TEXT NOT NULL,
                        trade_date DATE NOT NULL,
                        nav NUMERIC(10, 4),
                        score NUMERIC(5, 2)
                    )
                '''))

                # 构造 100 行数据
                rows = [
                    {"code": f"0000{i:02d}", "date": date(2026, 6, 17), "nav": 1.2345, "score": 0.65}
                    for i in range(100)
                ]

                # 测时
                start = time.perf_counter()
                await conn.execute(
                    text(f'''
                        INSERT INTO "{pg_schema}".daily_snapshots
                        (fund_code, trade_date, nav, score)
                        VALUES (:code, :date, :nav, :score)
                    '''),
                    rows,
                )
                elapsed = time.perf_counter() - start

                # 验证行数
                count = await conn.execute(text(f'SELECT COUNT(*) FROM "{pg_schema}".daily_snapshots'))
                assert count.scalar() == 100

                # 性能断言：100 行 < 1s（含网络往返）
                assert elapsed < 1.0, f"100-row insert took {elapsed:.3f}s (> 1s)"
                print(f"\n[Perf] 100 rows insert: {elapsed*1000:.1f}ms")
        finally:
            await engine.dispose()

    async def test_upsert_conflict(self, pg_schema):
        """测试 7：INSERT ... ON CONFLICT DO UPDATE（UPSERT）"""
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'''
                    CREATE TABLE "{pg_schema}".snapshots (
                        fund_code TEXT NOT NULL,
                        trade_date DATE NOT NULL,
                        score NUMERIC(5, 2),
                        PRIMARY KEY (fund_code, trade_date)
                    )
                '''))

                # 第一次插入
                await conn.execute(
                    text(f'''
                        INSERT INTO "{pg_schema}".snapshots (fund_code, trade_date, score)
                        VALUES (:code, :date, :score)
                        ON CONFLICT (fund_code, trade_date) DO UPDATE SET score = EXCLUDED.score
                    '''),
                    {"code": "000001", "date": date(2026, 6, 17), "score": 0.50},
                )

                # 第二次（应该 UPDATE）
                await conn.execute(
                    text(f'''
                        INSERT INTO "{pg_schema}".snapshots (fund_code, trade_date, score)
                        VALUES (:code, :date, :score)
                        ON CONFLICT (fund_code, trade_date) DO UPDATE SET score = EXCLUDED.score
                    '''),
                    {"code": "000001", "date": date(2026, 6, 17), "score": 0.75},
                )

                # 验证 score 是 0.75（被更新）
                result = await conn.execute(
                    text(f'SELECT score FROM "{pg_schema}".snapshots WHERE fund_code = :code'),
                    {"code": "000001"},
                )
                assert float(result.scalar()) == 0.75
        finally:
            await engine.dispose()


# ============================================================
# 6. 异步事务测试
# ============================================================

class TestPostgresAsyncTransaction:
    """验证 async session + 事务回滚"""

    async def test_transaction_rollback(self, pg_schema):
        """测试 8：异常时自动回滚"""
        engine = create_async_engine(_postgres_url(), echo=False)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE TABLE "{pg_schema}".tx_test (id INT PRIMARY KEY, name TEXT)'))

            async with factory() as session:  # type: AsyncSession
                try:
                    await session.execute(
                        text(f'INSERT INTO "{pg_schema}".tx_test (id, name) VALUES (:id, :name)'),
                        {"id": 1, "name": "Alice"},
                    )
                    # 故意抛错
                    raise ValueError("simulated error")
                    await session.commit()
                except ValueError:
                    await session.rollback()

            # 验证：回滚后无数据
            async with engine.connect() as conn:
                result = await conn.execute(text(f'SELECT COUNT(*) FROM "{pg_schema}".tx_test'))
                assert result.scalar() == 0, "Rollback failed: data still present"
        finally:
            await engine.dispose()

    async def test_concurrent_transactions_isolated(self, pg_schema):
        """测试 9：并发事务隔离（READ COMMITTED）"""
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE TABLE "{pg_schema}".counter (id INT PRIMARY KEY, value INT)'))
                await conn.execute(text(f"INSERT INTO \"{pg_schema}\".counter VALUES (1, 0)"))

            async def increment(worker_id: int):
                # 每个 worker 一个独立连接
                local_engine = create_async_engine(_postgres_url(), echo=False)
                try:
                    async with local_engine.begin() as conn:
                        # 模拟 2 个并发 UPDATE（PostgreSQL 行级锁）
                        await conn.execute(
                            text(f'UPDATE "{pg_schema}".counter SET value = value + 1 WHERE id = 1'),
                        )
                finally:
                    await local_engine.dispose()

            # 并发跑 10 个 increment
            await asyncio.gather(*[increment(i) for i in range(10)])

            # 验证：value 应 = 10
            async with engine.connect() as conn:
                result = await conn.execute(text(f'SELECT value FROM "{pg_schema}".counter WHERE id = 1'))
                final = result.scalar()
                assert final == 10, f"Expected 10, got {final}"
        finally:
            await engine.dispose()


# ============================================================
# 7. 与 ORM 模型兼容性测试
# ============================================================

class TestPostgresORMCompat:
    """验证 SQLAlchemy ORM 模型在 Postgres 上工作（与 SQLite 行为差异检测）"""

    async def test_numeric_type(self, pg_schema):
        """测试 10：NUMERIC 类型精度（金融金额必须精确）

        NUMERIC(20, 8) = 最多 20 位数字，其中 8 位小数 → 整数部分最多 12 位
        """
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'''
                    CREATE TABLE "{pg_schema}".finance (
                        id SERIAL PRIMARY KEY,
                        amount NUMERIC(20, 8) NOT NULL
                    )
                '''))

                # 测试 NUMERIC 精度（不丢精度）- 数值控制在 12 位整数 + 8 位小数以内
                test_amounts = [
                    "123456789012.12345678",  # 12 位整数 + 8 位小数
                    "999999999999.99999999", # NUMERIC(20,8) 上限
                ]
                for amt in test_amounts:
                    await conn.execute(
                        text(f'INSERT INTO "{pg_schema}".finance (amount) VALUES (:amt)'),
                        {"amt": Decimal(amt)},
                    )

                # 额外测试：极小正小数（0.00000001）— 用 to_char 强制 8 位小数格式
                await conn.execute(
                    text(f'INSERT INTO "{pg_schema}".finance (amount) VALUES (0.00000001)'),
                )

                result = await conn.execute(text(f'SELECT amount FROM "{pg_schema}".finance ORDER BY id'))
                amounts = [row[0] for row in result.fetchall()]

                # 验证精度保留（Decimal 类型直接比较）
                assert amounts[0] == Decimal("123456789012.12345678")
                assert amounts[1] == Decimal("999999999999.99999999")
                # 极小正小数：精度不丢，符号正确
                assert amounts[2] == Decimal("0.00000001")
                assert amounts[2] > 0  # 不能为 0
        finally:
            await engine.dispose()

    async def test_text_vs_varchar(self, pg_schema):
        """测试 11：TEXT 字段长度（无长度限制 vs SQLite）"""
        engine = create_async_engine(_postgres_url(), echo=False)
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f'CREATE TABLE "{pg_schema}".long_text (id SERIAL PRIMARY KEY, content TEXT)'))

                # 超长文本（1MB）
                long_content = "x" * 1_000_000
                await conn.execute(
                    text(f'INSERT INTO "{pg_schema}".long_text (content) VALUES (:c)'),
                    {"c": long_content},
                )

                result = await conn.execute(text(f'SELECT LENGTH(content) FROM "{pg_schema}".long_text'))
                length = result.scalar()
                assert length == 1_000_000, f"Expected 1000000, got {length}"
        finally:
            await engine.dispose()


# ============================================================
# 8. 总结
# ============================================================

class TestPostgresSummary:
    """测试 12-13：综合健康度 + 配置验证"""

    async def test_database_settings(self, pg_engine):
        """测试 12：数据库关键配置（如 max_connections）"""
        async with pg_engine.connect() as conn:
            result = await conn.execute(text("SHOW max_connections"))
            max_conn = result.scalar()
            # Supabase free tier 至少 60 连接
            assert int(max_conn) >= 60, f"max_connections too low: {max_conn}"

    async def test_extension_pg_stat_statements(self, pg_engine):
        """测试 13：pg_stat_statements 扩展（性能分析）"""
        async with pg_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'")
            )
            # Supabase 默认启用；如未启用，跳过不报错
            has_ext = result.scalar() is not None
            if not has_ext:
                pytest.skip("pg_stat_statements not enabled (optional extension)")


# ============================================================
# 测试运行提示
# ============================================================

"""
运行方法：

# 1. 设置环境变量（在 .env 或 shell 中）
export USE_POSTGRES=true
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_DB_PASSWORD=your-strong-password

# 2. 运行测试
cd first-project/backend
pytest tests/test_p4_1_postgres_integration.py -v -s

# 3. 预期输出
# - 13 tests collected
# - 全部 PASSED
# - 性能数据：100 rows insert < 1s

# 4. 默认 CI 行为
# USE_POSTGRES 未设置时：13 tests SKIPPED（不污染主测试套件）
"""
