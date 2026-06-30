"""
P4-3: Prometheus 指标 + /metrics 端点

提供：
1. 基础 HTTP 指标（请求数、延迟、状态码）— prometheus-fastapi-instrumentator 自动
2. 业务指标（情绪计算次数、信号灯分布、数据库查询延迟）— 自定义
3. /metrics 端点（Prometheus 抓取）

用法：
    from app.core.metrics import business_counter, setup_metrics

    setup_metrics(app)  # 在 main.py 中调用
"""
from typing import Optional

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram, Gauge, Summary
from prometheus_client.exposition import generate_latest
from prometheus_client import CONTENT_TYPE_LATEST
from fastapi.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# 业务指标定义
# ============================================================

# 1. 情绪计算（每次 API 调用）
emotion_calculation_total = Counter(
    "fsa_emotion_calculation_total",
    "Total number of emotion calculations",
    ["factor_count", "result"],  # factor_count: 14 | less ; result: success | error
)

# 2. 信号灯分布（实时分布）
signal_distribution = Gauge(
    "fsa_signal_distribution",
    "Current distribution of signal lights (S+/S/A/B/C/D/E)",
    ["signal_level"],
)

# 3. 因子得分（按因子）
factor_score = Gauge(
    "fsa_factor_score",
    "Latest score for each of 14 factors",
    ["factor_name"],
)

# 4. 数据库查询延迟
db_query_duration = Histogram(
    "fsa_db_query_duration_seconds",
    "Database query duration in seconds",
    ["query_type"],  # select | insert | update | delete
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# 5. Supabase 远程连接（仅 P4-1 启用时记录）
supabase_connections_active = Gauge(
    "fsa_supabase_connections_active",
    "Active connections to Supabase Postgres",
)

# 6. 缓存命中率
cache_hits_total = Counter(
    "fsa_cache_hits_total",
    "Total cache hits",
    ["cache_type"],  # redis | memory
)
cache_misses_total = Counter(
    "fsa_cache_misses_total",
    "Total cache misses",
    ["cache_type"],
)

# 7. Tushare/AkShare API 调用
external_api_duration = Summary(
    "fsa_external_api_duration_seconds",
    "External API call duration",
    ["api_name", "endpoint"],
)

# 8. 应用启动时间（uptime 监控）
app_start_time = Gauge(
    "fsa_app_start_time_seconds",
    "Application start time as Unix timestamp",
)


# ============================================================
# /metrics 端点
# ============================================================

def metrics_endpoint() -> Response:
    """Prometheus 抓取端点（GET /metrics）"""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


# ============================================================
# Instrumentator 初始化（HTTP 指标）
# ============================================================

def setup_metrics(app: FastAPI) -> None:
    """初始化 Prometheus 指标 + 注册 /metrics 端点

    调用时机：在 FastAPI app 创建后、所有 router include_router 之后
    """
    import time as _time
    app_start_time.set(_time.time())

    # HTTP 指标（请求数/延迟/状态码）
    Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,  # 总是启用 metrics（个人项目，安全/性能均可控）
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/"],  # 避免自监控噪声
        inprogress_name="fsa_http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
        tags=["监控"],
    )

    logger.info("📊 Prometheus metrics enabled at /metrics")


# ============================================================
# 业务工具函数
# ============================================================

def record_emotion_calculation(factor_count: int, success: bool = True) -> None:
    """记录情绪计算事件"""
    emotion_calculation_total.labels(
        factor_count=str(factor_count) if factor_count >= 14 else "less",
        result="success" if success else "error",
    ).inc()


def record_signal_distribution(distribution: dict) -> None:
    """记录信号灯分布（如 {"S+": 2, "S": 5, "A": 10, ...}）"""
    for level, count in distribution.items():
        signal_distribution.labels(signal_level=level).set(count)


def record_cache_hit(cache_type: str = "redis") -> None:
    cache_hits_total.labels(cache_type=cache_type).inc()


def record_cache_miss(cache_type: str = "redis") -> None:
    cache_misses_total.labels(cache_type=cache_type).inc()
