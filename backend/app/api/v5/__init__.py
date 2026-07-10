"""
V5 Routers Package Init - 阶段 2 拆分后的统一入口

对外保持 `app.api.v5.router` 接口不变（向后兼容）
"""
import logging

from fastapi import APIRouter

from app.api.v5.sentiment_router import router as sentiment_router
from app.api.v5.position_router import router as position_router
from app.api.v5.factor_data_router import router as factor_data_router
from app.api.v5.health_router import router as health_router
from app.api.v5.sector_router import router as sector_router
from app.api.v5.snapshot_router import router as snapshot_router
from app.api.v5.analysis_router import router as analysis_router

logger = logging.getLogger(__name__)

# 主路由：保持原 prefix "/api/v5"（向后兼容）
router = APIRouter(prefix="/api/v5")
router.include_router(sentiment_router)
router.include_router(position_router)
router.include_router(factor_data_router)
router.include_router(health_router)
router.include_router(sector_router)
router.include_router(snapshot_router)
router.include_router(analysis_router)


__all__ = [
    "router",
    "sentiment_router",
    "position_router",
    "factor_data_router",
    "health_router",
    "sector_router",
]
