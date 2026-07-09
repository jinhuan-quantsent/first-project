"""
应用配置管理
从 .env 文件和环境变量读取配置
支持 Supabase PostgreSQL 和 SQLite 双模式
"""
import json as _json
from pathlib import Path as _Path
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
    SKIP_DB_CREATE: bool = False    # 跳过自动建表（MySQL 已手工建表时设为 True）
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
        if self.USE_POSTGRES:
            if self.supabase_db_url != self.DATABASE_URL:
                return self.supabase_db_url
            return self.DATABASE_URL
        # 非 PostgreSQL 模式：直接使用 DATABASE_URL（支持 MySQL / SQLite / 其他）
        return self.DATABASE_URL

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
    # ⚠️ 以下参数为前后端共享，修改时需同步更新前端 paramsMapper.ts：
    #   - V5_FACTOR_CONFIG (权重 + sigmoid_k)
    #   - V5_SIGNAL_BOUNDARIES
    #   - V5_QUANTILE_WINDOW_DAYS

    # --- V5.0 信号边界 (6个边界划分7级: S+/S/A/B/C/D/E) ---
    V5_SIGNAL_BOUNDARIES: List[int] = Field(default_factory=lambda: [12, 25, 38, 52, 65, 80])

    # --- V5.0 14因子配置 (名称/方向/权重/Sigmoid参数) ---
    V5_FACTOR_CONFIG: dict = Field(default_factory=lambda: {
        "VOL":  {"label": "波动率", "direction": "fear", "weight": 0.11, "sigmoid_c": 0.50, "sigmoid_k": 3.0, "source": "tushare"},
        "ADR":  {"label": "涨跌比", "direction": "greed", "weight": 0.11, "sigmoid_c": 0.50, "sigmoid_k": 2.5, "source": "tushare"},
        "ERP":  {"label": "股债性价比", "direction": "fear", "weight": 0.11, "sigmoid_c": 0.50, "sigmoid_k": 4.0, "source": "tushare"},
        "FLOW": {"label": "资金流", "direction": "greed", "weight": 0.09, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
        "ETF":  {"label": "ETF份额", "direction": "greed", "weight": 0.07, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
        "NHNL": {"label": "新高占比", "direction": "greed", "weight": 0.07, "sigmoid_c": 0.60, "sigmoid_k": 2.5, "source": "tushare"},
        "TURN": {"label": "换手率", "direction": "fear", "weight": 0.07, "sigmoid_c": 0.40, "sigmoid_k": 3.0, "source": "tushare"},
        "POS":  {"label": "基金仓位", "direction": "greed", "weight": 0.07, "sigmoid_c": 0.50, "sigmoid_k": 1.8, "source": "tushare"},
        "NBF":  {"label": "北向资金", "direction": "greed", "weight": 0.06, "sigmoid_c": 0.50, "sigmoid_k": 2.5, "source": "tushare"},
        "PCR":  {"label": "认沽认购比", "direction": "fear", "weight": 0.02, "sigmoid_c": 0.30, "sigmoid_k": 4.0, "source": "tushare"},
        "NEWF": {"label": "新发基金热度", "direction": "greed", "weight": 0.04, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
        "MARGIN": {"label": "融资融券", "direction": "greed", "weight": 0.04, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "tushare"},
        "RSI": {"label": "RSI指标", "direction": "fear", "weight": 0.03, "sigmoid_c": 0.50, "sigmoid_k": 2.5, "source": "tushare"},
        "INDUSTRY_DIVERGENCE": {"label": "行业分歧度", "direction": "fear", "weight": 0.03, "sigmoid_c": 0.50, "sigmoid_k": 2.0, "source": "sector"},
    })



    # --- V5.0 板块因子配置 (独立于 V5_FACTOR_CONFIG, 5因子方案) ---
    # IC/IR 验证后定稿: TURN/VOL/NHNL/RSI 有效, MOM/ADR 剔除
    # direction: greed=高值利多, fear=高值利空
    # reverse: True=信号需翻转 (fear方向因子在Sigmoid后做100-score)
    V5_SECTOR_FACTOR_CONFIG: dict = Field(default_factory=lambda: {
        "TURN": {"weight": 0.28, "direction": "fear",  "sigmoid_c": 0.50, "sigmoid_k": 2.0, "reverse": True},
        "VOL":  {"weight": 0.25, "direction": "greed", "sigmoid_c": 0.50, "sigmoid_k": 3.0, "reverse": False},
        "NHNL": {"weight": 0.20, "direction": "greed", "sigmoid_c": 0.60, "sigmoid_k": 2.5, "reverse": False},
        "RSI":  {"weight": 0.15, "direction": "greed", "sigmoid_c": 0.50, "sigmoid_k": 2.5, "reverse": False},
        "DIV":  {"weight": 0.12, "direction": "fear",  "sigmoid_c": 0.50, "sigmoid_k": 2.0, "reverse": True},
    })
    # --- V5.0 分位数标准化窗口 ---
    V5_QUANTILE_WINDOW_DAYS: int = 1260  # 5年 × 252交易日
    V5_QUANTILE_MIN_SAMPLES: int = 252   # 最少1年数据

    # --- V5.0 分歧度动态加权 ---
    V5_DIVERGENCE_PENALTY_MIN: float = 0.85   # 最大分歧时惩罚系数
    V5_DIVERGENCE_PENALTY_MAX: float = 1.0   # 无分歧时惩罚系数
    V5_DIVERGENCE_STD_THRESHOLD: float = 30.0  # 触发防线的factor_std阈值（Sigmoid得分0-100范围）

    # --- V5.0 板块引擎独立信号边界 ---
    # 5因子加权平均自然范围[25,72]比14因子[8,85]窄，用独立边界避免极端信号永远不触发
    # 训练期P3/P8/P20/P80/P90/P95分位数校准: S+<36, S<40, A<45, B<55, C<58, D<62, E>=62
    V5_SECTOR_SIGNAL_THRESHOLDS: List[float] = Field(default_factory=lambda: [36, 40, 45, 55, 58, 62])

    # ── 建仓评级开关 ──
    ENABLE_BUILD_RATING: bool = True  # False时隐藏所有评级字段

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

    # --- V5.1 仓位分母配置 ---
    V5_POSITION_DENOMINATOR: str = 'total_assets'  # 分母类型: 'total_assets'(总资产=市值+现金) 或 'market_value'(旧=仅市值)

    # --- V5.1 组合约束配置 ---
    V5_TOTAL_POSITION_CAP: float = 0.80     # 总仓位上限 (Sigma target_pct <= 80%, 留20%现金缓冲)
    V5_SECTOR_POSITION_CAP: float = 0.25    # 板块仓位上限 (同板块Sigma target_pct <= 25%)
    V5_SINGLE_FUND_CAP: float = 0.30        # 单基金上限 (target_pct <= 30%, 防集中度)
    V5_CASH_BUFFER_RATIO: float = 0.20      # 现金缓冲比例 (总资产 x 20%作为最低现金持有)
    ENABLE_PORTFOLIO_CONSTRAINTS: bool = True  # 组合约束开关 (关闭后跳过裁剪, 回到纯矩阵查表)

    # --- V5.0 四道假信号防线 ---
    V5_DEFENSE_EXTREME_VOLATILITY: bool = True  # 防线1: 市场极端波动
    V5_DEFENSE_JUMP_GT_15: bool = True         # 防线2: 信号跳变>15分
    V5_DEFENSE_PRICE_DIVERGENCE: bool = True    # 防线3: 价格-情绪背离
    V5_DEFENSE_FACTOR_STD: bool = True         # 防线4: 因子分歧度>阈值

    # ============================================================
    # 方案B: 板块过滤器 + 趋势卫士
    # ============================================================
    # --- 板块过滤器开关 ---
    ENABLE_SECTOR_FILTER: bool = True  # 板块过滤器（建仓拦截）

    # --- 趋势卫士开关 ---
    ENABLE_TREND_GUARD: bool = True   # 趋势卫士（持仓文案引导）

    # --- 板块过滤器阈值 (可选，默认使用硬编码值) ---
    SECTOR_FILTER_UP_DAYS_RATIO_THRESHOLD: float = 0.50   # 20日上涨占比阈值 (50%)
    SECTOR_FILTER_RELATIVE_STRENGTH_THRESHOLD: float = -0.03  # 60日相对强弱阈值 (-3%)
    SECTOR_FILTER_MA20_POSITION_THRESHOLD: float = 0.0      # MA20趋势位置阈值 (价格>MA20)

    # --- 趋势卫士参数 (可选，默认使用硬编码值) ---
    TREND_GUARD_MA20_PERIOD: int = 20           # MA20计算周期
    TREND_GUARD_MACD_FAST: int = 12           # MACD快线周期
    TREND_GUARD_MACD_SLOW: int = 26           # MACD慢线周期
    TREND_GUARD_MACD_SIGNAL: int = 9          # MACD信号线周期
    TREND_GUARD_OSCILLATION_DAYS: int = 20   # 震荡判断周期
    TREND_GUARD_OSCILLATION_CROSS_THRESHOLD: int = 3  # 震荡判断穿越次数阈值
    TREND_GUARD_OSCILLATION_AMPLITUDE_THRESHOLD: float = 0.05  # 震荡判断振幅阈值 (5%)

    # ============================================================
    # 盘中预演配置 (Intraday Preview)
    # ============================================================
    # 全局开关（与Redis开关 intraday_preview:global_switch 双保险）
    ENABLE_INTRADAY_PREVIEW: bool = True
    # Redis缓存key前缀
    INTRADAY_PREVIEW_CACHE_PREFIX: str = "intraday_preview:v1"
    # 盘中预计算结果缓存TTL（秒）— 与scheduler每5分钟刷新对齐
    INTRADAY_PREVIEW_CACHE_TTL: int = 300
    # 缓存异步续期偏移（第240秒=300-60触发续期，避免前端读到过期数据）
    INTRADAY_PREVIEW_RENEWAL_OFFSET: int = 60
    # ── 弹性系数参数 ──
    # 基准2.0（从3.0修正，实测沪深300涨1%→变动2-2.5分）
    INTRADAY_PREVIEW_ELASTIC_BASE: float = 2.0
    INTRADAY_PREVIEW_ELASTIC_LOW: float = 1.5      # 高波动(|gszzl|>3%)范围下限
    INTRADAY_PREVIEW_ELASTIC_MID_MIN: float = 2.0   # 中波动范围下限
    INTRADAY_PREVIEW_ELASTIC_MID_MAX: float = 2.5   # 中波动范围上限
    INTRADAY_PREVIEW_ELASTIC_HIGH: float = 3.0      # 低波动(|gszzl|<1%)范围上限
    INTRADAY_PREVIEW_ELASTIC_EXTREME_CLAMP: float = 1.0  # |gszzl|>5%强制系数（极端行情降敏）
    INTRADAY_PREVIEW_SCORE_DELTA_CLAMP: float = 20.0     # score_delta clamp范围（防信号跳变）
    INTRADAY_PREVIEW_GSZZL_ANOMALY_THRESHOLD: float = 10.0  # ±10%涨跌幅异常阈值（丢弃异常估值）
    # ── Scheduler时间配置 ──
    INTRADAY_PREVIEW_META_PACK_TIME: str = "15:40"  # 元数据打包时间（收盘后）
    INTRADAY_PREVIEW_SCHEDULE_TIMES: list = Field(default_factory=lambda: [
        "9:35", "10:00", "10:30", "11:00",
        "13:05", "13:30", "14:00", "14:30", "14:45",
    ])  # 盘中预计算时间点（避开开收盘波动+午休）
    # ── 对账校准 ──
    INTRADAY_PREVIEW_RECONCILE_TIME: str = "15:50"  # 对账校准时间
    INTRADAY_PREVIEW_ELASTIC_WEEKLY_UPDATE_DAY: str = "fri"  # 弹性系数周更日
    INTRADAY_PREVIEW_ELASTIC_WEEKLY_UPDATE_TIME: str = "15:45"  # 弹性系数周更时间

    # ============================================================
    # 策略验证分析表配置 (Strategy Validation Log)
    # ============================================================
    # ── Scheduler时间配置 ──
    VALIDATION_PERSIST_TIME: str = "14:50"        # 任务A: 预演持久化+系统建议
    VALIDATION_DEEPSEEK_TIME: str = "14:52"       # 任务C: DeepSeek AI建议
    VALIDATION_BACKFILL_TIME: str = "17:35"        # 任务B: T+1回验回填
    # ── Redis Key 前缀 ──
    VALIDATION_CACHE_PREFIX: str = "v5:strategy_validation"
    VALIDATION_INTRADAY_HL_PREFIX: str = "intraday_preview:v1:hl"  # 盘中高低点追踪
    # ── DeepSeek API 配置 ──
    DEEPSEEK_API_KEY: str = ""                      # 为空则跳过AI建议
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-v4-flash"         # V4-flash (deepseek-chat已于2026-07-24弃用)
    DEEPSEEK_TIMEOUT: int = 10                       # 秒, 超时后重试1次
    DEEPSEEK_MAX_TOKENS: int = 2000
    DEEPSEEK_MAX_RETRIES: int = 1                   # 失败重试次数
    DEEPSEEK_TEMPERATURE: float = 0.3               # 低温度=稳定输出


    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()


# ── 激活策略参数覆盖 ──
_ACTIVE_CONFIG_PATH = _Path(__file__).parent.parent / "data" / "active_strategy.json"


def get_active_strategy_overrides() -> dict | None:
    """从本地 JSON 读取回测激活方案的参数。如果有，用于覆盖主系统默认值。"""
    try:
        if _ACTIVE_CONFIG_PATH.exists():
            with open(_ACTIVE_CONFIG_PATH, encoding="utf-8") as f:
                data = _json.load(f)
            return data.get("params")
    except Exception:
        pass
    return None
