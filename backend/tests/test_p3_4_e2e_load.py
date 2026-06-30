"""
E2E + 压测 — 阶段 3 P3-4

E2E 场景：
- 完整用户旅程：健康检查 → 情绪查询 → 因子雷达

压测：
- 50 次 health check（轻量）
- 20 次 multi-index（中等重量）
- 30 次 factor-radar（中等重量）

指标：P50 / P95 / P99 响应时延，错误率
"""
import statistics
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v5 import router as v5_router
from app.core.database import get_session


# ============================================================
# 共享：mock 客户端
# ============================================================
app = FastAPI()
app.include_router(v5_router, prefix="")


async def _mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    session.bind = MagicMock()
    session.bind.dialect = MagicMock()
    session.bind.dialect.name = "sqlite"
    yield session


app.dependency_overrides[get_session] = _mock_session


# ============================================================
# E2E 场景
# ============================================================
class TestE2EUserJourney:
    """完整用户旅程 E2E"""

    def test_health_to_snapshot_journey(self):
        """用户旅程：访问首页 → 查看快照 → 查看多指数"""
        with TestClient(app) as client:
            # Step 1: 健康检查
            r1 = client.get("/api/v5/health")
            assert r1.status_code == 200
            assert r1.json()["data"]["status"] == "healthy"

            # Step 2: 获取市场快照
            with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
                instance = mock_svc.return_value
                instance.get_market_snapshot = AsyncMock(return_value={
                    "code": 0, "data": {
                        "indexes": [{"index_code": "SH000001"}],
                        "global_sentiment": "neutral",
                        "global_score": 50.0,
                        "divergence_index": 0.0,
                        "conclusion": "震荡",
                        "updated_at": "2026-06-17",
                    }, "message": "ok",
                })
                r2 = client.get("/api/v5/market/snapshot")
            assert r2.status_code == 200
            body = r2.json()
            assert body["code"] == 0
            assert body["data"]["global_sentiment"] == "neutral"

            # Step 3: 获取多指数
            with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
                instance = mock_svc.return_value
                instance.run_multi_index = AsyncMock(return_value={
                    "code": 0, "data": {
                        "indexes": [
                            {"index_code": "SH000001", "composite_score": 50.0},
                            {"index_code": "SH000300", "composite_score": 55.0},
                        ],
                        "composite": {"composite_score": 52.5},
                        "updated_at": "2026-06-17",
                    }, "message": "ok",
                })
                r3 = client.get("/api/v5/market/multi-index", params={"codes": "SH000001,SH000300"})
            assert r3.status_code == 200
            assert len(r3.json()["data"]["indexes"]) == 2

    def test_factor_radar_journey(self):
        """用户旅程：Dashboard → 因子雷达图"""
        with TestClient(app) as client:
            with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
                instance = mock_svc.return_value
                instance.get_factor_radar = AsyncMock(return_value={
                    "code": 0, "data": {
                        "index_code": "SH000300",
                        "factors": [{"name": f"f_{i}", "quantile": i/14.0} for i in range(14)],
                    }, "message": "ok",
                })
                r = client.get("/api/v5/market/factor-radar", params={"index_code": "SH000300"})
            assert r.status_code == 200
            assert len(r.json()["data"]["factors"]) == 14


# ============================================================
# 压测工具
# ============================================================
def _concurrent_requests(client: TestClient, url: str, n: int) -> tuple[list, int]:
    """同步执行 n 个请求，返回每请求时延（毫秒）"""
    latencies = []
    errors = 0
    for _ in range(n):
        start = time.perf_counter()
        r = client.get(url)
        elapsed = (time.perf_counter() - start) * 1000
        latencies.append(elapsed)
        if r.status_code != 200:
            errors += 1
    return latencies, errors


def _percentile(data: list, p: int) -> float:
    """计算 P 分位"""
    if not data:
        return 0.0
    return statistics.quantiles(data, n=100)[p - 1] if len(data) >= 100 else sorted(data)[int(len(data) * p / 100)]


# ============================================================
# 压测场景
# ============================================================
class TestLoadHealthCheck:
    """health check 压测（轻量）"""

    def test_50_concurrent_health(self):
        """50 个连续 health 请求应全部成功且 P95 < 100ms"""
        with TestClient(app) as client:
            latencies, errors = _concurrent_requests(client, "/api/v5/health", 50)
            assert errors == 0, f"Got {errors} errors out of 50"
            p95 = _percentile(latencies, 95)
            p50 = _percentile(latencies, 50)
            # health 端点应非常快
            assert p95 < 100, f"P95 {p95:.1f}ms exceeds 100ms"
            print(f"\n[HEALTH] 50 reqs: P50={p50:.1f}ms, P95={p95:.1f}ms, max={max(latencies):.1f}ms")


class TestLoadMultiIndex:
    """multi-index 压测（中等）"""

    def test_20_concurrent_multi_index(self):
        """20 个 multi-index 请求应全部成功（mock service 后很快）"""
        with TestClient(app) as client, \
             patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.run_multi_index = AsyncMock(return_value={
                "code": 0, "data": {
                    "indexes": [{"index_code": f"SH{i:06d}"} for i in range(4)],
                    "composite": {"composite_score": 50.0},
                    "updated_at": "2026-06-17",
                }, "message": "ok",
            })
            latencies, errors = _concurrent_requests(client, "/api/v5/market/multi-index", 20)
            assert errors == 0, f"Got {errors} errors out of 20"
            p95 = _percentile(latencies, 95)
            print(f"\n[MULTI-INDEX] 20 reqs: P95={p95:.1f}ms, max={max(latencies):.1f}ms")


class TestLoadFactorRadar:
    """factor-radar 压测"""

    def test_30_concurrent_factor_radar(self):
        """30 个 factor-radar 请求应全部成功"""
        with TestClient(app) as client, \
             patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_factor_radar = AsyncMock(return_value={
                "code": 0, "data": {
                    "index_code": "SH000300",
                    "factors": [{"name": f"f_{i}", "quantile": 0.5} for i in range(14)],
                }, "message": "ok",
            })
            latencies, errors = _concurrent_requests(client, "/api/v5/market/factor-radar", 30)
            assert errors == 0, f"Got {errors} errors out of 30"
            p95 = _percentile(latencies, 95)
            print(f"\n[FACTOR-RADAR] 30 reqs: P95={p95:.1f}ms, max={max(latencies):.1f}ms")


class TestConcurrencyPatterns:
    """并发模式测试"""

    def test_mixed_endpoints_concurrent(self):
        """混合 4 个端点各 10 次（共 40 req）应全部成功"""
        with TestClient(app) as client, \
             patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.run_multi_index = AsyncMock(return_value={
                "code": 0, "data": {"indexes": [], "composite": {}, "updated_at": ""},
                "message": "ok",
            })
            instance.get_factor_radar = AsyncMock(return_value={
                "code": 0, "data": {"index_code": "X", "factors": []}, "message": "ok",
            })
            instance.get_market_snapshot = AsyncMock(return_value={
                "code": 0, "data": {"indexes": [], "global_sentiment": "neutral"},
                "message": "ok",
            })

            urls = [
                "/api/v5/health",
                "/api/v5/market/multi-index",
                "/api/v5/market/snapshot",
                "/api/v5/market/factor-radar",
            ]
            total_errors = 0
            all_latencies = []
            for url in urls:
                latencies, errors = _concurrent_requests(client, url, 10)
                total_errors += errors
                all_latencies.extend(latencies)
            assert total_errors == 0, f"Got {total_errors} errors in mixed test"
            print(f"\n[MIXED] 40 reqs (4 endpoints × 10): max={max(all_latencies):.1f}ms, "
                  f"mean={statistics.mean(all_latencies):.1f}ms")
