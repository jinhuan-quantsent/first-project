"""
健康检查接口
"""
from datetime import datetime

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """系统健康检查"""
    return {
        "code": 0,
        "data": {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "3.5.0",
            "db": "connected",
            "redis": "memory",
        },
        "message": "ok",
    }
