"""
Redis 缓存客户端
支持 Upstash Redis（生产环境）和内存缓存（开发模式兜底）
"""
import json
import time
from typing import Any, Optional

from app.core.config import settings


class MemoryCache:
    """内存缓存（开发模式兜底）"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}  # {key: (value, expire_at)}

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self._store:
            value, expire_at = self._store[key]
            if expire_at == 0 or time.time() < expire_at:
                return value
            del self._store[key]
        return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """设置缓存值"""
        expire_at = time.time() + ttl if ttl > 0 else 0
        self._store[key] = (value, expire_at)

    async def delete(self, key: str) -> None:
        """删除缓存"""
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        if key in self._store:
            _, expire_at = self._store[key]
            if expire_at == 0 or time.time() < expire_at:
                return True
            del self._store[key]
        return False


# 全局 Redis 客户端
_redis_client: Any | None = None
_memory_cache: MemoryCache | None = None


async def init_redis() -> None:
    """初始化 Redis 连接"""
    global _redis_client, _memory_cache

    if settings.USE_REDIS:
        try:
            import redis.asyncio as aioredis

            redis_kwargs: dict[str, Any] = {
                "decode_responses": True,
                "socket_connect_timeout": 5,
            }
            # Upstash 需要密码认证
            if settings.UPSTASH_REDIS_TOKEN:
                redis_kwargs["password"] = settings.UPSTASH_REDIS_TOKEN

            _redis_client = aioredis.from_url(
                settings.redis_url,
                **redis_kwargs,
            )
            await _redis_client.ping()
            print("✅ Redis 连接成功")
        except Exception as e:
            print(f"⚠️ Redis 连接失败，使用内存缓存: {e}")
            _redis_client = None
            _memory_cache = MemoryCache()
    else:
        _memory_cache = MemoryCache()
        print("✅ 使用内存缓存（开发模式）")


async def close_redis() -> None:
    """关闭 Redis 连接"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        print("🔌 Redis 连接已关闭")


async def cache_get(key: str) -> Optional[Any]:
    """获取缓存值"""
    if _redis_client:
        raw = await _redis_client.get(key)
        if raw:
            return json.loads(raw)
        return None
    if _memory_cache:
        return await _memory_cache.get(key)
    return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """设置缓存值"""
    if _redis_client:
        await _redis_client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    elif _memory_cache:
        await _memory_cache.set(key, value, ttl)


async def cache_delete(key: str) -> None:
    """删除缓存"""
    if _redis_client:
        await _redis_client.delete(key)
    elif _memory_cache:
        await _memory_cache.delete(key)


async def cache_exists(key: str) -> bool:
    """检查键是否存在"""
    if _redis_client:
        return bool(await _redis_client.exists(key))
    if _memory_cache:
        return await _memory_cache.exists(key)
    return False
