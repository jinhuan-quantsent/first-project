"""
P2-4: CRUD 缓存失效测试

验证：
1. cache_invalidate_pattern 在内存模式下能删除匹配 key
2. CacheInvalidator 装饰器自动失效
3. 缓存失效失败不影响业务
4. 通配符 fnmatch 兼容
"""
import asyncio
import pytest

from app.core.redis_client import (
    MemoryCache,
    cache_set,
    cache_get,
    cache_invalidate_pattern,
    CacheInvalidator,
)


@pytest.fixture(autouse=True)
def reset_memory_cache():
    """每个测试前重置全局内存缓存"""
    import app.core.redis_client as redis_client
    redis_client._memory_cache = MemoryCache()
    redis_client._redis_client = None
    yield
    redis_client._memory_cache = None


class TestCacheInvalidatePattern:
    """cache_invalidate_pattern 单元测试"""

    @pytest.mark.asyncio
    async def test_invalidates_matching_keys(self):
        """失效所有匹配 pattern 的 key"""
        await cache_set("fsa:user:1", "data1")
        await cache_set("fsa:user:2", "data2")
        await cache_set("fsa:post:1", "post1")

        count = await cache_invalidate_pattern("fsa:user:*")
        assert count == 2

        assert await cache_get("fsa:user:1") is None
        assert await cache_get("fsa:user:2") is None
        assert await cache_get("fsa:post:1") == "post1"  # 未被失效

    @pytest.mark.asyncio
    async def test_no_match_returns_zero(self):
        """无匹配时返回 0"""
        await cache_set("foo:1", "x")
        count = await cache_invalidate_pattern("bar:*")
        assert count == 0
        assert await cache_get("foo:1") == "x"

    @pytest.mark.asyncio
    async def test_exact_match_works(self):
        """精确匹配（无 *）也能工作"""
        await cache_set("key1", "v1")
        await cache_set("key2", "v2")
        count = await cache_invalidate_pattern("key1")
        assert count == 1
        assert await cache_get("key1") is None
        assert await cache_get("key2") == "v2"

    @pytest.mark.asyncio
    async def test_wildcard_question_mark(self):
        """? 通配符（单个字符）"""
        await cache_set("fsa:a1", "x")
        await cache_set("fsa:a2", "y")
        await cache_set("fsa:a10", "z")
        count = await cache_invalidate_pattern("fsa:a?")
        assert count == 2  # a1, a2 匹配；a10 不匹配
        assert await cache_get("fsa:a10") == "z"


class TestCacheInvalidatorDecorator:
    """CacheInvalidator 装饰器测试"""

    @pytest.mark.asyncio
    async def test_decorator_invalidates_after_success(self):
        """装饰器在函数成功后失效"""
        @CacheInvalidator(["test:pattern:*"])
        async def update_something():
            return {"status": "ok"}

        await cache_set("test:pattern:1", "old")
        result = await update_something()
        assert result == {"status": "ok"}
        assert await cache_get("test:pattern:1") is None

    @pytest.mark.asyncio
    async def test_decorator_invalidates_multiple_patterns(self):
        """装饰器支持多 pattern"""
        @CacheInvalidator(["test:a:*", "test:b:*"])
        async def update_x():
            return "ok"

        await cache_set("test:a:1", "x")
        await cache_set("test:b:1", "y")
        await cache_set("test:c:1", "z")

        await update_x()

        assert await cache_get("test:a:1") is None
        assert await cache_get("test:b:1") is None
        assert await cache_get("test:c:1") == "z"  # 不在 pattern 中

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self):
        """装饰器保留函数元数据"""
        @CacheInvalidator(["x:*"])
        async def my_function():
            """My docstring"""
            return 42

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring"

    @pytest.mark.asyncio
    async def test_decorator_handles_failure_gracefully(self):
        """装饰器在缓存失效失败时不影响业务结果"""
        @CacheInvalidator(["x:*"])
        async def may_fail():
            return "result"

        # 模拟 cache_invalidate_pattern 抛错
        with pytest.MonkeyPatch.context() as mp:
            async def boom(pattern):
                raise Exception("redis down")
            mp.setattr("app.core.redis_client.cache_invalidate_pattern", boom)

            # 应该不抛错
            result = await may_fail()
            assert result == "result"

    @pytest.mark.asyncio
    async def test_decorator_returns_function_result(self):
        """装饰器正确返回原函数结果"""
        @CacheInvalidator(["x:*"])
        async def returns_dict():
            return {"code": 0, "data": "value"}

        result = await returns_dict()
        assert result == {"code": 0, "data": "value"}
