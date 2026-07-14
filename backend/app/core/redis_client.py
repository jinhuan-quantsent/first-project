"""
Redis 缓存客户端
支持 Upstash Redis（生产环境）和内存缓存（开发模式兜底）

Namespace 设计: v5: = 情绪引擎/板块/自选等核心接口; fsa: = 持仓/组合等用户级接口（独立命名便于按业务域批量清理/监控）
"""
import json
import logging
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class SafeJSONEncoder(json.JSONEncoder):
    """Redis 缓存专用 JSON 编码器，显式处理非 JSON 原生类型。

    替代 default=str 的静默转换，确保类型转换可预测、可追踪：
    - datetime/date/time → ISO 格式字符串（可被 fromisoformat 反序列化）
    - Decimal → float（保持数值语义，避免 str(Decimal) 带来的字符串比较陷阱）
    - numpy 类型 → 原生 Python 类型（来自 pandas df.to_dict('records')）
    - UUID → 字符串
    - bytes → base64 字符串
    - set/frozenset → list
    - 未知类型 → 记录 WARNING 日志后 fallback 到 str()（不中断生产，但暴露问题）
    """

    def default(self, obj: Any) -> Any:
        # --- datetime 家族 ---
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, dtime):
            return obj.isoformat()

        # --- Decimal → float ---
        if isinstance(obj, Decimal):
            return float(obj)

        # --- UUID → str ---
        if isinstance(obj, UUID):
            return str(obj)

        # --- bytes → base64 ---
        if isinstance(obj, (bytes, bytearray)):
            import base64
            return base64.b64encode(obj).decode("ascii")

        # --- set → list ---
        if isinstance(obj, (set, frozenset)):
            return list(obj)

        # --- numpy 类型（延迟导入，避免硬依赖） ---
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.datetime64):
                item = obj.item()
                return item.isoformat() if hasattr(item, "isoformat") else str(item)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass

        # --- 未知类型：记录 WARNING 后 fallback 到 str() ---
        # 不 raise TypeError，避免中断生产；但日志会暴露问题，便于排查
        logger.warning(
            "SafeJSONEncoder: 未知类型 %s.%s 将被 str() 转换，可能导致 round-trip 类型丢失",
            type(obj).__module__, type(obj).__name__,
        )
        return str(obj)


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
    """获取缓存值（带延迟初始化：若缓存未初始化则自动创建 MemoryCache）"""
    global _memory_cache
    if _redis_client:
        raw = await _redis_client.get(key)
        if raw:
            return json.loads(raw)
        return None
    if _memory_cache is None:
        _memory_cache = MemoryCache()
    return await _memory_cache.get(key)


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """设置缓存值（带延迟初始化：若缓存未初始化则自动创建 MemoryCache）"""
    global _memory_cache
    if _redis_client:
        await _redis_client.set(key, json.dumps(value, ensure_ascii=False, cls=SafeJSONEncoder), ex=ttl)
    else:
        if _memory_cache is None:
            _memory_cache = MemoryCache()
        await _memory_cache.set(key, value, ttl)


async def cache_delete(key: str) -> None:
    """删除缓存（带延迟初始化：若缓存未初始化则自动创建 MemoryCache）"""
    global _memory_cache
    if _redis_client:
        await _redis_client.delete(key)
    else:
        if _memory_cache is None:
            _memory_cache = MemoryCache()
        await _memory_cache.delete(key)


async def cache_exists(key: str) -> bool:
    """检查键是否存在（带延迟初始化：若缓存未初始化则自动创建 MemoryCache）"""
    global _memory_cache
    if _redis_client:
        return bool(await _redis_client.exists(key))
    if _memory_cache is None:
        _memory_cache = MemoryCache()
    return await _memory_cache.exists(key)


# ============================================================
# 数据版本号管理（缓存自动刷新机制）
# ============================================================

DATA_VERSION_KEY = "fund_sentiment:data_version"

# 模块→需要失效的v5:* key模式映射
MODULE_CACHE_PATTERNS = {
    "signal_board": ["v5:sentiment:*", "v5:multi_index:*", "v5:signal_lights:*",
                     "v5:market_snapshot", "v5:factor_radar:*", "v5:divergence_alert"],
    "holdings": ["v5:pos_rating:*", "v5:sector:radar"],
    "watchlist": ["v5:watchlist:*"],
    "sector": ["v5:sector:sentiment", "v5:sector:radar", "v5:sectors:*", "v5:sector_detail:*"],
    "ai_analysis": ["v5:review:*"],
}


async def update_data_version(module: str) -> None:
    """更新模块的数据版本号（当前时间戳）"""
    if not _redis_client:
        return
    from datetime import datetime
    timestamp = datetime.now().isoformat(timespec="seconds")
    await _redis_client.hset(DATA_VERSION_KEY, module, timestamp)


async def get_data_version(modules: list[str] | None = None) -> dict:
    """获取模块的数据版本号。modules=None时返回全部"""
    if not _redis_client:
        return {}
    if modules:
        pipe = _redis_client.pipeline()
        for m in modules:
            pipe.hget(DATA_VERSION_KEY, m)
        results = await pipe.execute()
        return {m: v if v else None for m, v in zip(modules, results)}
    else:
        raw = await _redis_client.hgetall(DATA_VERSION_KEY)
        return {k: v for k, v in raw.items()}


async def invalidate_module_cache(module: str) -> None:
    """失效模块对应的v5:*缓存key"""
    if not _redis_client:
        return
    patterns = MODULE_CACHE_PATTERNS.get(module, [])
    for pattern in patterns:
        keys = await _redis_client.keys(pattern)
        if keys:
            await _redis_client.delete(*keys)
