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
    APP_VERSION: str = "5.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    API_PREFIX: str = "/api/v1"
    API_V5_PREFIX: str = "/api/v5"
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

    # ============================
    # V5.0 新增配置项
    # ============================

    # --- V5.0 信号边界 (6个边界划分7级: S+/S/A/B/C/D/E) ---
    V5_SIGNAL_BOUNDARIES: List[int] = Field(default_factory=lambda: [12, 25, 38, 52, 65, 80])

    # --- V5.0 11因子配置 (名称/方向/权重/Sigmoid参数) ---
    V5_FACTOR_CONFIG: dict = Field(default_factory=lambda: {
        "VOL":  {"label": "波动率", "direction": "fear", "weight": 0.12, "sigmoid_c": 0.50, "sigmoid_k": 3.0, "source": "tushare"},
        "ADR":  {"label": "涨跌比", "direction": "greed", "weight": 0.12, "sigmoid_c": 0.50, "sigmoid_k": 2.5, "source": "tushare"},
        "ERP":  {"label": "股债性价比", "direction": "fear", "weight": 0.12, "sigmoid_c": 0.50, "sigmoid_k": 4.0, "source": "tushare"},
        "FLOW": {"label": "资金流", "direction": "greed", "weight": 0.10, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
        "ETF":  {"label": "ETF份额", "direction": "greed", "weight": 0.08, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
        "NHNL": {"label": "新高占比", "direction": "greed", "weight": 0.08, "sigmoid_c": 0.60, "sigmoid_k": 2.5, "source": "tushare"},
        "TURN": {"label": "换手率", "direction": "fear", "weight": 0.08, "sigmoid_c": 0.40, "sigmoid_k": 3.0, "source": "tushare"},
        "POS":  {"label": "基金仓位", "direction": "greed", "weight": 0.08, "sigmoid_c": 0.50, "sigmoid_k": 1.8, "source": "tushare"},
        "NBF":  {"label": "北向资金", "direction": "greed", "weight": 0.06, "sigmoid_c": 0.50, "sigmoid_k": 2.5, "source": "tushare"},
        "PCR":  {"label": "认沽认购比", "direction": "fear", "weight": 0.04, "sigmoid_c": 0.30, "sigmoid_k": 4.0, "source": "tushare"},
        "NEWF": {"label": "新发基金热度", "direction": "greed", "weight": 0.04, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
    })

    # --- V5.0 分位数标准化窗口 ---
    V5_QUANTILE_WINDOW_DAYS: int = 1260  # 5年 × 252交易日
    V5_QUANTILE_MIN_SAMPLES: int = 252   # 最少1年数据

    # --- V5.0 分歧度动态加权 ---
    V5_DIVERGENCE_PENALTY_MIN: float = 0.5   # 最大分歧时惩罚系数
    V5_DIVERGENCE_PENALTY_MAX: float = 1.0   # 无分歧时惩罚系数
    V5_DIVERGENCE_STD_THRESHOLD: float = 15.0  # 触发防线的factor_std阈值（Sigmoid得分0-100范围）

    # --- V5.0 防跳变规则 ---
    V5_ANTI_JUMP_SMALL_DIFF: int = 10   # 分数差<10 → 最多变1级
    V5_ANTI_JUMP_LARGE_DIFF: int = 10   # 分数差≥10 → 最多变2级
    V5_ANTI_JUMP_CONSECUTIVE_DAYS: int = 3  # 连续N天同向 → 额外1级

    # --- V5.0 仓位矩阵 (5行当前仓位 × 7列信号等级) ---
    # 存储数值化目标仓位百分比，与项目书3.6节对齐
    V5_POSITION_MATRIX: List[List[float]] = Field(default_factory=lambda: [
        # S+     S      A      B      C      D      E       ← 信号等级
        [0.30,  0.20,  0.10,  0.00,  0.00,  0.00,  0.00],  # empty (空仓0%)
        [0.50,  0.40,  0.30,  0.25,  0.10,  0.00,  0.00],  # light (轻仓25%)
        [0.70,  0.60,  0.50,  0.50,  0.40,  0.30,  0.20],  # mid   (半仓50%)
        [0.80,  0.75,  0.75,  0.75,  0.50,  0.40,  0.30],  # heavy (重仓75%)
        [1.00,  1.00,  1.00,  1.00,  0.60,  0.50,  0.40],  # full  (满仓100%)
    ])
    V5_POSITION_LEVELS: List[str] = Field(default_factory=lambda: ["empty", "light", "mid", "heavy", "full"])

    # --- V5.0 置信度修正系数 ---
    V5_CONFIDENCE_POSITION_ADJ: dict = Field(default_factory=lambda: {
        4: 1.0,   # 4星 → 100%
        3: 0.75,  # 3星 → 75%
        2: 0.50,  # 2星 → 50%
        1: 0.0,   # 1星 → 0% 不操作 (HOLD)
    })

    # --- V5.0 交易成本校验 ---
    V5_COST_THRESHOLD_PCT: float = 0.015  # 1.5% 低于此不操作
    V5_FREQUENCY_LIMIT_DAYS: int = 7      # 7天内同基金只能执行一次

    # --- V5.0 四道假信号防线 ---
    V5_DEFENSE_EXTREME_VOLATILITY: bool = True  # 防线1: 市场极端波动
    V5_DEFENSE_JUMP_GT_15: bool = True         # 防线2: 信号跳变>15分
    V5_DEFENSE_PRICE_DIVERGENCE: bool = True    # 防线3: 价格-情绪背离
    V5_DEFENSE_FACTOR_STD: bool = True         # 防线4: 因子分歧度>阈值

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
