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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    # 启动
    await init_db()
    await init_redis()
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动成功")
    print(f"📋 CORS origins: {settings.effective_cors_origins}")
    yield
    # 关闭
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

# V5 核心路由（已自带 /api/v5 前缀）
app.include_router(health_router, prefix="", tags=["健康检查"])
app.include_router(auth_router, prefix="", tags=["认证"])
app.include_router(v5_router, prefix="", tags=["V5.0情绪引擎"])

# 基金查询（改为 /api/v5/fund/*）
fund_router.prefix = "/api/v5/fund"
app.include_router(fund_router, prefix="", tags=["基金查询"])

# 持仓管理（已自带 /api/v5/portfolio 前缀）
app.include_router(portfolio_router, prefix="", tags=["持仓管理"])

# 自选基金（已自带 /api/v5/watchlist 前缀）
app.include_router(watchlist_router, prefix="", tags=["自选基金"])

# 回测引擎（改为 /api/v5/review/*）
review_v5_router.prefix = "/api/v5/review"
app.include_router(review_v5_router, prefix="", tags=["V5.0回测引擎"])


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
