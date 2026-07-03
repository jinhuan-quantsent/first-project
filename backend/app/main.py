"""
FastAPI 应用入口
基金情绪分析系统 V5.0
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db, close_db
from app.core.redis_client import init_redis, close_redis

import logging
import sys as _sys

# 确保 app 命名空间日志输出到 stderr (uvicorn 默认只配置 uvicorn namespace)
_app_log_handler = logging.StreamHandler(_sys.stderr)
_app_log_handler.setLevel(logging.INFO)
_app_log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
logging.getLogger('app').addHandler(_app_log_handler)
logging.getLogger('app').setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    # 启动
    await init_db()
    await init_redis()

    # 启动定时任务调度器（每日收盘后自动快照）
    from app.core.scheduler import init_scheduler
    scheduler = init_scheduler()

    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动成功")
    print(f"📋 CORS origins: {settings.effective_cors_origins}")
    yield
    # 关闭
    scheduler.shutdown(wait=False)
    await close_redis()
    await close_db()
    print("👋 应用已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="为个人基金投资者提供实时情绪指标的大盘择时与基金优选决策工具",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.effective_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局异常捕获"""
    return JSONResponse(
        status_code=500,
        content={
            "code": -1,
            "data": None,
            "message": f"服务器内部错误: {str(exc)}",
        },
    )


# ============================================================
# 注册路由 — V5.0 统一前缀 /api/v5
# ============================================================
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.v5 import router as v5_router
from app.api.fund import router as fund_router
from app.api.review_v5 import router as review_v5_router
from app.api.portfolio import router as portfolio_router
from app.api.watchlist import router as watchlist_router
from app.api.market import router as market_router
from app.api.admin import router as admin_router

# V5 核心路由（已自带 /api/v5 前缀）
app.include_router(health_router, prefix="", tags=["健康检查"])
app.include_router(auth_router, prefix="", tags=["认证"])
app.include_router(v5_router, prefix="", tags=["V5.0情绪引擎"])

# 基金查询（prefix="/api/v5/fund" 必须在 include_router 参数里传，否则FastAPI不生效）
app.include_router(fund_router, prefix="/api/v5/fund", tags=["基金查询"])

# 市场数据（推荐/热力图等，挂载到 /api/v5 下）
app.include_router(market_router, prefix="/api/v5", tags=["市场数据"])

# 持仓管理（已自带 /api/v5/portfolio 前缀）
app.include_router(portfolio_router, prefix="", tags=["持仓管理"])

# 自选基金（已自带 /api/v5/watchlist 前缀）
app.include_router(watchlist_router, prefix="", tags=["自选基金"])

# 回测引擎（保留原始前缀 /api/v5/backtest）
app.include_router(review_v5_router, prefix="", tags=["V5.0回测引擎"])

# Manage operations (manual backfill, etc.)
app.include_router(admin_router, prefix="", tags=["Manage"])


@app.get("/")
async def root() -> dict:
    """根路由"""
    return {
        "code": 0,
        "data": {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/api/v5/docs",
        },
        "message": "ok",
    }
