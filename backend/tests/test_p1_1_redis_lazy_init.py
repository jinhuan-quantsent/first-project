"""
P1-1 复检：Redis 客户端延迟初始化
验证 cache_get/cache_set/cache_delete/cache_exists 在 _memory_cache 为 None 时自动创建 MemoryCache
"""
import pytest
import pytest_asyncio

from app.core.redis_client import (
    MemoryCache,
    cache_get,
    cache_set,
    cache_delete,
    cache_exists,
    init_redis,
    _memory_cache,
    _redis_client,
)


@pytest.fixture(autouse=True)
def reset_global_state():
    """每个测试前后重置全局状态"""
    import app.core.redis_client as mod
    mod._memory_cache = None
    mod._redis_client = None
    yield
    mod._memory_cache = None
    mod._redis_client = None


class TestLazyInit:
    """延迟初始化测试"""

    @pytest.mark.asyncio
    async def test_cache_get_creates_memory_cache(self):
        """cache_get 在 _memory_cache 为 None 时自动创建 MemoryCache"""
        import app.core.redis_client as mod
        assert mod._memory_cache is None

        result = await cache_get("test_key")
        assert result is None  # 空缓存返回 None
        assert mod._memory_cache is not None
        assert isinstance(mod._memory_cache, MemoryCache)

    @pytest.mark.asyncio
    async def test_cache_set_creates_memory_cache(self):
        """cache_set 在 _memory_cache 为 None 时自动创建 MemoryCache"""
        import app.core.redis_client as mod
        assert mod._memory_cache is None

        await cache_set("test_key", "test_value", ttl=60)
        assert mod._memory_cache is not None
        assert isinstance(mod._memory_cache, MemoryCache)

    @pytest.mark.asyncio
    async def test_cache_delete_creates_memory_cache(self):
        """cache_delete 在 _memory_cache 为 None 时自动创建 MemoryCache"""
        import app.core.redis_client as mod
        assert mod._memory_cache is None

        await cache_delete("test_key")
        assert mod._memory_cache is not None
        assert isinstance(mod._memory_cache, MemoryCache)

    @pytest.mark.asyncio
    async def test_cache_exists_creates_memory_cache(self):
        """cache_exists 在 _memory_cache 为 None 时自动创建 MemoryCache"""
        import app.core.redis_client as mod
        assert mod._memory_cache is None

        result = await cache_exists("test_key")
        assert result is False  # 空缓存返回 False
        assert mod._memory_cache is not None
        assert isinstance(mod._memory_cache, MemoryCache)

    @pytest.mark.asyncio
    async def test_set_then_get(self):
        """初始化后 cache_get 能获取 cache_set 写入的值"""
        await cache_set("my_key", {"data": 42}, ttl=60)
        result = await cache_get("my_key")
        assert result == {"data": 42}

    @pytest.mark.asyncio
    async def test_set_then_exists(self):
        """cache_set 后 cache_exists 返回 True"""
        await cache_set("exists_key", "value", ttl=60)
        assert await cache_exists("exists_key") is True
        assert await cache_exists("nonexistent_key") is False

    @pytest.mark.asyncio
    async def test_set_then_delete(self):
        """cache_set 后 cache_delete 能删除"""
        await cache_set("del_key", "value", ttl=60)
        assert await cache_exists("del_key") is True
        await cache_delete("del_key")
        assert await cache_exists("del_key") is False


class TestInitRedisNoRedis:
    """USE_REDIS=False 时的行为"""

    @pytest.mark.asyncio
    async def test_init_redis_no_connection_when_disabled(self):
        """USE_REDIS=False 时 init_redis 不尝试连接 Redis，直接创建 MemoryCache"""
        import app.core.redis_client as mod
        from unittest.mock import patch

        with patch.object(mod.settings, "USE_REDIS", False):
            await init_redis()
            assert mod._redis_client is None
            assert mod._memory_cache is not None
            assert isinstance(mod._memory_cache, MemoryCache)

    @pytest.mark.asyncio
    async def test_init_redis_creates_memory_cache_when_disabled(self):
        """USE_REDIS=False 时 init_redis 创建 MemoryCache"""
        import app.core.redis_client as mod
        from unittest.mock import patch

        with patch.object(mod.settings, "USE_REDIS", False):
            await init_redis()
            # 可以正常使用缓存操作
            await cache_set("key", "val", ttl=10)
            assert await cache_get("key") == "val"
