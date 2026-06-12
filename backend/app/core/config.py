"""
应用配置管理
从 .env 文件和环境变量读取配置
支持 Supabase PostgreSQL 和 SQLite 双模式
"""
from typing import List

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""

    # --- 应用 ---
    APP_NAME: str = "基金情绪分析系统"
    APP_VERSION: str = "3.5.0"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # --- 数据库 ---
    USE_POSTGRES: bool = False
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/fund_sentiment"
    SQLITE_PATH: str = "./data/fund_sentiment.db"

    @property
    def db_url(self) -> str:
        """根据环境自动选择数据库连接"""
        if self.USE_POSTGRES:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"

    # --- Redis ---
    USE_REDIS: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    UPSTASH_REDIS_URL: str = ""

    @property
    def redis_url(self) -> str:
        """获取 Redis 连接地址"""
        if self.UPSTASH_REDIS_URL:
            return self.UPSTASH_REDIS_URL
        return self.REDIS_URL

    # --- 数据源 ---
    TUSHARE_TOKEN: str = ""
    USE_AKSHARE: bool = True
    DATA_CACHE_TTL: int = 300  # 秒

    # --- Celery ---
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- CORS ---
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # --- Vercel ---
    VERCEL_URL: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
