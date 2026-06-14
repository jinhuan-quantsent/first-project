"""
健康检查接口
V4.0：添加 Redis / PG 连接状态检查，含超时保护和延迟指标
"""
import asyncio
import time
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """系统健康检查，含 Redis / PG 连接状态（带超时保护）"""

    async def _check_health() -> dict:
        redis_status = "disabled"
        redis_latency_ms: float | None = None
        db_status = "sqlite"
        db_latency_ms: float | None = None

        # Redis 连通性
        if settings.USE_REDIS:
            try:
                from app.core.redis_client import _redis_client

                if _redis_client is not None:
                    t0 = time.monotonic()
                    await asyncio.wait_for(_redis_client.ping(), timeout=3.0)
                    redis_latency_ms = round((time.monotonic() - t0) * 1000, 1)
                    redis_status = "redis"
                else:
                    # USE_REDIS=True 但 _redis_client 为 None → 连接失败降级到内存缓存
                    redis_status = "redis_error"
            except asyncio.TimeoutError:
                redis_status = "redis_timeout"
            except Exception:
                redis_status = "redis_error"
        else:
            redis_status = "disabled"

        # PG 连通性
        try:
            from app.core.database import _engine

            if _engine is not None and settings.USE_POSTGRES:
                t0 = time.monotonic()
                await asyncio.wait_for(
                    _run_pg_ping(_engine),
                    timeout=5.0,
                )
                db_latency_ms = round((time.monotonic() - t0) * 1000, 1)
                db_status = "postgres"
        except asyncio.TimeoutError:
            db_status = "postgres_timeout"
        except Exception:
            db_status = "postgres_error" if settings.USE_POSTGRES else "sqlite"

        result: dict = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": settings.APP_VERSION,
            "db": db_status,
            "redis": redis_status,
            "auth_disabled": settings.AUTH_DISABLED,
        }
        if db_latency_ms is not None:
            result["db_latency_ms"] = db_latency_ms
        if redis_latency_ms is not None:
            result["redis_latency_ms"] = redis_latency_ms
        return result

    try:
        data = await asyncio.wait_for(_check_health(), timeout=10.0)
    except asyncio.TimeoutError:
        data = {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "version": settings.APP_VERSION,
            "db": "timeout",
            "redis": "timeout",
            "auth_disabled": settings.AUTH_DISABLED,
        }

    return {
        "code": 0,
        "data": data,
        "message": "ok",
    }


async def _run_pg_ping(engine: object) -> None:
    """执行 PG SELECT 1 探测"""
    async with engine.connect() as conn:  # type: ignore[union-attr]
        await conn.execute(text("SELECT 1"))
