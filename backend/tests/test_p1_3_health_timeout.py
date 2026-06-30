"""
P1-3 复检：health 端点 PG 超时保护
验证 SQLite 模式下 health 正常返回、超时保护、延迟指标

注意：直接测试 health_check 函数，避免导入 app.main 带来的依赖链问题
"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import pytest
import pytest_asyncio


class TestHealthSQLiteMode:
    """SQLite 模式下 health 端点正常返回"""

    @pytest.mark.asyncio
    async def test_health_returns_ok_in_sqlite_mode(self):
        """SQLite 模式下 health 端点正常返回"""
        # 直接 import health_check，不通过 app.main
        from app.api.health import health_check

        with patch("app.api.health.settings") as mock_settings:
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = False
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            result = await health_check()
            assert result["code"] == 0
            data = result["data"]
            assert data["db"] == "sqlite"
            assert data["redis"] == "disabled"
            assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_has_db_field(self):
        """返回结果包含 db 字段"""
        from app.api.health import health_check

        with patch("app.api.health.settings") as mock_settings:
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = False
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            result = await health_check()
            assert "db" in result["data"]

    @pytest.mark.asyncio
    async def test_health_has_version_and_timestamp(self):
        """返回结果包含 version 和 timestamp"""
        from app.api.health import health_check

        with patch("app.api.health.settings") as mock_settings:
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = False
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            result = await health_check()
            data = result["data"]
            assert "version" in data
            assert "timestamp" in data
            assert data["version"] == "4.0.0"


class TestHealthPGTimeout:
    """PG 超时保护测试"""

    @pytest.mark.asyncio
    async def test_pg_timeout_returns_postgres_timeout(self):
        """PG 检查超时时返回 postgres_timeout"""
        async def slow_ping(engine):
            await asyncio.sleep(10)  # 超过 5s 超时

        with patch("app.api.health.settings") as mock_settings, \
             patch("app.api.health._run_pg_ping", side_effect=slow_ping), \
             patch("app.core.database._engine", MagicMock()):
            mock_settings.USE_POSTGRES = True
            mock_settings.USE_REDIS = False
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            from app.api.health import health_check
            result = await health_check()
            assert result["data"]["db"] == "postgres_timeout"

    @pytest.mark.asyncio
    async def test_redis_timeout_returns_redis_timeout(self):
        """Redis 检查超时时返回 redis_timeout"""
        async def slow_ping():
            await asyncio.sleep(10)  # 超过 3s 超时

        mock_redis = AsyncMock()
        mock_redis.ping = slow_ping

        with patch("app.api.health.settings") as mock_settings, \
             patch("app.core.redis_client._redis_client", mock_redis):
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = True
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            from app.api.health import health_check
            result = await health_check()
            assert result["data"]["redis"] == "redis_timeout"

    @pytest.mark.asyncio
    async def test_overall_timeout_returns_unhealthy(self):
        """整体超时时返回 unhealthy"""
        # 通过 mock asyncio.wait_for 让外层 10s 整体超时触发
        original_wait_for = asyncio.wait_for
        call_count = 0

        async def mock_wait_for(coro, timeout=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一个 wait_for 是外层的 10s 整体超时
                raise asyncio.TimeoutError()
            return await original_wait_for(coro, timeout=timeout)

        with patch("asyncio.wait_for", side_effect=mock_wait_for), \
             patch("app.api.health.settings") as mock_settings:
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = False
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            from app.api.health import health_check
            result = await health_check()
            assert result["data"]["status"] == "unhealthy"


class TestHealthRedisDisabled:
    """Redis 禁用状态检查"""

    @pytest.mark.asyncio
    async def test_redis_disabled_when_use_redis_false(self):
        """USE_REDIS=False 时 redis 返回 disabled"""
        from app.api.health import health_check

        with patch("app.api.health.settings") as mock_settings:
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = False
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            result = await health_check()
            assert result["data"]["redis"] == "disabled"

    @pytest.mark.asyncio
    async def test_redis_error_when_client_none_but_use_redis_true(self):
        """USE_REDIS=True 但 _redis_client 为 None 时返回 redis_error"""
        from app.api.health import health_check

        with patch("app.api.health.settings") as mock_settings, \
             patch("app.core.redis_client._redis_client", None):
            mock_settings.USE_POSTGRES = False
            mock_settings.USE_REDIS = True
            mock_settings.APP_VERSION = "4.0.0"
            mock_settings.AUTH_DISABLED = False

            result = await health_check()
            assert result["data"]["redis"] == "redis_error"
