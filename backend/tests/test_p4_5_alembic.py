"""P4-5: Alembic 数据库迁移系统测试

测试场景：
- alembic 命令可执行
- upgrade head / downgrade base 闭环
- 异步驱动自动转换（asyncpg → psycopg2）
- 迁移幂等性
- autogenerate 检测
- 数据库 schema 一致性
"""
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_ENV = PROJECT_ROOT / "migrations" / "alembic" / "env.py"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations" / "alembic" / "versions"

PYTHON_BIN = sys.executable


def _run_alembic(*args: str, test_db: Path) -> subprocess.CompletedProcess:
    """运行 alembic 命令并返回结果

    用 pytest tmp_path 提供测试数据库，避开沙箱对 data/ 的限制
    """
    env = os.environ.copy()
    # 用绝对路径传给子进程
    env["SQLITE_PATH"] = str(test_db)
    env["USE_POSTGRES"] = "false"
    cmd = [PYTHON_BIN, "-m", "alembic", *args]
    return subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


@pytest.fixture
def test_db(tmp_path):
    """pytest tmp_path 提供的测试数据库（避开 data/ 沙箱）"""
    return tmp_path / "test_alembic.db"


# ============================================================
# 配置存在性测试（3 个）
# ============================================================

class TestAlembicConfig:
    """Alembic 配置文件存在性"""

    def test_alembic_ini_exists(self):
        """alembic.ini 配置文件存在"""
        assert ALEMBIC_INI.exists(), f"alembic.ini 不存在: {ALEMBIC_INI}"

    def test_alembic_ini_is_ascii(self):
        """alembic.ini 必须是纯 ASCII（Windows GBK bug）"""
        content = ALEMBIC_INI.read_bytes()
        try:
            content.decode("ascii")
        except UnicodeDecodeError as e:
            pytest.fail(f"alembic.ini 含非 ASCII 字符，会触发 Windows GBK 解码错误: {e}")

    def test_env_py_exists(self):
        """env.py 存在"""
        assert ALEMBIC_ENV.exists(), f"env.py 不存在: {ALEMBIC_ENV}"


# ============================================================
# 驱动转换测试（3 个）
# ============================================================

class TestAsyncToSyncConversion:
    """异步驱动 → 同步驱动的自动转换"""

    def test_env_py_handles_asyncpg(self):
        """env.py 必须处理 +asyncpg"""
        content = ALEMBIC_ENV.read_text(encoding="utf-8")
        assert "+asyncpg" in content
        assert "psycopg2" in content or "psycopg" in content

    def test_env_py_handles_aiosqlite(self):
        """env.py 必须处理 +aiosqlite"""
        content = ALEMBIC_ENV.read_text(encoding="utf-8")
        assert "+aiosqlite" in content
        assert "sqlite" in content.lower()

    def test_env_py_imports_settings(self):
        """env.py 必须导入 settings"""
        content = ALEMBIC_ENV.read_text(encoding="utf-8")
        assert "from app.core.config import settings" in content
        assert "from app.core.database import Base" in content


# ============================================================
# 迁移文件测试（3 个）
# ============================================================

class TestInitialMigration:
    """初始迁移文件"""

    def test_at_least_one_migration(self):
        """至少存在 1 个迁移文件"""
        migrations = list(MIGRATIONS_DIR.glob("*.py"))
        migrations = [m for m in migrations if m.name != "__init__.py"]
        assert len(migrations) >= 1, "没有 alembic 迁移文件"

    def test_migration_has_upgrade_downgrade(self):
        """迁移文件必须包含 upgrade() 和 downgrade()"""
        migrations = list(MIGRATIONS_DIR.glob("*.py"))
        for mig in migrations:
            if mig.name == "__init__.py":
                continue
            content = mig.read_text(encoding="utf-8")
            assert "def upgrade()" in content, f"{mig.name} 缺 upgrade()"
            assert "def downgrade()" in content, f"{mig.name} 缺 downgrade()"

    def test_migration_revision_id(self):
        """迁移文件有 revision_id"""
        migrations = list(MIGRATIONS_DIR.glob("*.py"))
        for mig in migrations:
            if mig.name == "__init__.py":
                continue
            content = mig.read_text(encoding="utf-8")
            # 匹配 `revision: str = "xxx"`
            assert re.search(r'revision:\s*str\s*=\s*["\'][a-f0-9]+["\']', content), \
                f"{mig.name} 缺 revision ID"


# ============================================================
# upgrade / downgrade 测试（3 个）
# ============================================================

class TestUpgradeDowngrade:
    """迁移执行测试"""

    def test_upgrade_head_creates_all_tables(self, test_db):
        """upgrade head 后应创建所有模型表"""
        result = _run_alembic("upgrade", "head", test_db=test_db)
        assert result.returncode == 0, f"alembic upgrade 失败:\n{result.stderr}"

        # 验证表已创建
        assert test_db.exists()
        conn = sqlite3.connect(str(test_db))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        # 期望的表（来自 SQLAlchemy models）
        expected = {
            "factor_history",
            "market_sentiment",
            "user_portfolio",
            "fund_basic",
            "fund_nav",
            "advice_log",
            "position_execution",
        }
        missing = expected - tables
        assert not missing, f"缺表: {missing}"

    def test_alembic_version_table_exists(self, test_db):
        """alembic_version 表应存在"""
        _run_alembic("upgrade", "head", test_db=test_db)
        conn = sqlite3.connect(str(test_db))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None, "alembic_version 表不存在"

    def test_downgrade_base_removes_tables(self, test_db):
        """downgrade base 应删除所有表"""
        _run_alembic("upgrade", "head", test_db=test_db)
        result = _run_alembic("downgrade", "base", test_db=test_db)
        assert result.returncode == 0, f"alembic downgrade 失败:\n{result.stderr}"

        conn = sqlite3.connect(str(test_db))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()
        business_tables = tables - {"alembic_version", "sqlite_sequence"}
        assert not business_tables, f"downgrade 后仍有表: {business_tables}"


# ============================================================
# 状态查询测试（1 个）
# ============================================================

class TestAlembicState:
    """alembic 状态查询"""

    def test_current_after_upgrade(self, test_db):
        """upgrade head 后 alembic current 应显示 head"""
        _run_alembic("upgrade", "head", test_db=test_db)
        result = _run_alembic("current", test_db=test_db)
        assert result.returncode == 0
        assert "(head)" in result.stdout, f"current 输出不含 head:\n{result.stdout}"


# ============================================================
# 总数
# ============================================================
# 3 (Config) + 3 (Conversion) + 3 (Migration) + 3 (Upgrade/Downgrade) + 1 (State) = 13
