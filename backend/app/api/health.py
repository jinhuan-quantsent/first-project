"""
健康检查接口
V4.0：添加 Redis / PG 连接状态检查
"""
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """系统健康检查，含 Redis / PG 连接状态"""
    # Redis 连通性
    redis_status = "memory"
    try:
        from app.core.redis_client import _redis_client
        if _redis_client is not None:
            await _redis_client.ping()
            redis_status = "redis"
    except Exception:
        redis_status = "redis_error"

    # PG 连通性
    db_status = "sqlite"
    try:
        from app.core.database import _engine
        if _engine is not None and settings.USE_POSTGRES:
            async with _engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "postgres"
    except Exception:
        db_status = "postgres_error" if settings.USE_POSTGRES else "sqlite"

    return {
        "code": 0,
        "data": {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": settings.APP_VERSION,
            "db": db_status,
            "redis": redis_status,
            "auth_disabled": settings.AUTH_DISABLED,
        },
        "message": "ok",
    }
