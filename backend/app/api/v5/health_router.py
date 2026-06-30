"""
V5 Health Router - V5.0 健康检查路由
"""
from fastapi import APIRouter

from app.services.health_service import HealthService

router = APIRouter(tags=["v5-health"])


@router.get("/health")
async def v5_health():
    """V5.0 健康检查"""
    return HealthService().check()
