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
    APP_VERSION: str = "4.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # --- 数据库 ---
    USE_POSTGRES: bool = False
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/fund_sentiment"
    SQLITE_PATH: str = "./data/fund_sentiment.db"

    # --- Supabase ---
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_DB_PASSWORD: str = ""
    SUPABASE_JWT_SECRET: str = ""

    @property
    def supabase_url(self) -> str:
        """获取 Supabase 项目 URL"""
        return self.SUPABASE_URL

    @property
    def supabase_db_url(self) -> str:
        """构建 Supabase PostgreSQL 连接 URL（含密码）"""
        if self.SUPABASE_URL and self.SUPABASE_DB_PASSWORD:
            from urllib.parse import urlparse
            parsed = urlparse(self.SUPABASE_URL)
            db_user = "postgres"
            db_host = parsed.hostname or "localhost"
            db_port = parsed.port or 5432
            db_name = "postgres"
            return f"postgresql+asyncpg://{db_user}:{self.SUPABASE_DB_PASSWORD}@{db_host}:{db_port}/{db_name}"
        return self.DATABASE_URL

    @property
    def db_url(self) -> str:
        """根据环境自动选择数据库连接"""
        if self.USE_POSTGRES and self.supabase_db_url != self.DATABASE_URL:
            return self.supabase_db_url
        if self.USE_POSTGRES:
            return self.DATABASE_URL
        return f"sqlite+aiosqlite:///{self.SQLITE_PATH}"

    # --- Redis ---
    USE_REDIS: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"
    UPSTASH_REDIS_URL: str = ""
    UPSTASH_REDIS_TOKEN: str = ""

    @property
    def redis_url(self) -> str:
        """获取 Redis 连接地址"""
        if self.UPSTASH_REDIS_URL:
            return self.UPSTASH_REDIS_URL
        return self.REDIS_URL

    # --- 认证 ---
    AUTH_DISABLED: bool = False
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_SECONDS: int = 3600  # 1h
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
            "https://fsa.vercel.app",
            "https://fundsent.top",
        ]
    )

    @property
    def effective_cors_origins(self) -> List[str]:
        """
        获取生效的 CORS 源列表。

        规则：
        1. 始终包含 CORS_ORIGINS 中的手动配置（.env / 环境变量 / 默认值）
        2. 生产环境下，如果 SUPABASE_URL 非空，自动从 URL 中提取域名并加入白名单
        """
        origins = list(self.CORS_ORIGINS)

        if self.ENVIRONMENT == "production" and self.SUPABASE_URL:
            from urllib.parse import urlparse
            parsed = urlparse(self.SUPABASE_URL)
            hostname = parsed.hostname
            if hostname:
                # 加入 https://{hostname} 形式
                supabase_origin = f"https://{hostname}"
                if supabase_origin not in origins:
                    origins.append(supabase_origin)

        return origins

    # --- Vercel ---
    VERCEL_URL: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
