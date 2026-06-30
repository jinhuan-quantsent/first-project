"""
V5 API 集成测试

验证 V5.0 路由可达性、响应格式、关键字段。
V5 router 路径前缀: /api/v5/* （不混用 V1 路径 /api/v1/*）

覆盖：
- GET /api/v5/health
- GET /api/v5/market/sentiment/{index_code}
- GET /api/v5/market/multi-index
- GET /api/v5/market/signal-lights/{index_code}
- GET /api/v5/market/snapshot
- GET /api/v5/market/divergence
- GET /api/v5/market/factor-radar
- GET /api/v5/market/factor-heatmap
- GET /api/v5/market/sectors
- GET /api/v5/market/sector/{code}
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v5 import router as v5_router
from app.core.database import get_session


# ============================================================
# 测试客户端构造（mock DB session）
# ============================================================
app = FastAPI()
app.include_router(v5_router, prefix="")
API_PREFIX = "/api/v5"


async def _override_get_session():
    """覆盖 get_session 依赖，返回 mock session"""
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


app.dependency_overrides[get_session] = _override_get_session
client = TestClient(app)


# ============================================================
# 响应格式 helper
# ============================================================
def assert_unified_format(response, expected_code=0, expected_status=200):
    """Assert 标准响应格式 {code, data, message}"""
    assert response.status_code == expected_status, \
        f"Expected {expected_status}, got {response.status_code}: {response.text[:200]}"
    body = response.json()
    assert "code" in body, "Missing 'code'"
    assert "data" in body, "Missing 'data'"
    assert "message" in body, "Missing 'message'"
    assert body["code"] == expected_code, f"Expected code={expected_code}, got {body['code']}"
    return body


# ============================================================
# Health endpoint tests
# ============================================================
class TestV5HealthEndpoint:
    """GET /api/v5/health"""

    def test_health_returns_ok(self):
        response = client.get(f"{API_PREFIX}/health")
        body = assert_unified_format(response)
        data = body["data"]
        assert data["status"] == "healthy"
        assert data["service"] == "fund-sentiment-v5"
        assert data["version"] == "5.0"
        assert "checked_at" in data

    def test_health_response_format(self):
        response = client.get(f"{API_PREFIX}/health")
        body = response.json()
        assert isinstance(body["code"], int)
        assert isinstance(body["data"], dict)
        assert isinstance(body["message"], str)


# ============================================================
# Sentiment endpoint tests
# ============================================================
class TestV5SentimentEndpoint:
    """GET /api/v5/market/sentiment/{index_code}"""

    def test_sentiment_with_valid_index(self):
        """有效指数代码应返回 200 + 14 因子结果"""
        mock_result = {
            "index_code": "SH000300",
            "composite_score": 55.0,
            "sentiment_label": "neutral",
            "factors": {},
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.run_pipeline = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/sentiment/SH000300")

        body = assert_unified_format(response)
        assert body["data"]["composite_score"] == 55.0
        assert body["data"]["sentiment_label"] == "neutral"

    def test_sentiment_index_not_found(self):
        """无效指数代码应返回 code=404"""
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.run_pipeline = AsyncMock(return_value={"error": "Index INVALID not found"})

            response = client.get(f"{API_PREFIX}/market/sentiment/INVALID")

        body = response.json()
        assert body["code"] == 404
        assert body["data"] is None


class TestV5MultiIndexEndpoint:
    """GET /api/v5/market/multi-index"""

    def test_multi_index_default(self):
        """默认调用应返回 4 指数 + composite"""
        mock_result = {
            "code": 0,
            "data": {
                "indexes": [
                    {"index_code": "SH000001", "composite_score": 50.0, "sentiment_label": "neutral"},
                    {"index_code": "SH000300", "composite_score": 55.0, "sentiment_label": "neutral"},
                    {"index_code": "SZ399001", "composite_score": 60.0, "sentiment_label": "greed"},
                    {"index_code": "SZ399006", "composite_score": 45.0, "sentiment_label": "fear"},
                ],
                "composite": {"composite_score": 52.5, "sentiment_label": "neutral"},
                "updated_at": "2026-06-17T00:00:00",
            },
            "message": "ok",
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.run_multi_index = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/multi-index")

        body = response.json()
        assert body["code"] == 0
        assert len(body["data"]["indexes"]) == 4
        assert "composite" in body["data"]

    def test_multi_index_specific_codes(self):
        """指定指数代码应工作"""
        mock_result = {
            "code": 0,
            "data": {
                "indexes": [
                    {"index_code": "SH000001", "composite_score": 50.0},
                ],
                "composite": {},
                "updated_at": "2026-06-17",
            },
            "message": "ok",
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.run_multi_index = AsyncMock(return_value=mock_result)

            response = client.get(
                f"{API_PREFIX}/market/multi-index",
                params={"codes": "SH000001"},
            )

        body = response.json()
        assert body["code"] == 0


class TestV5SignalLightsEndpoint:
    """GET /api/v5/market/signal-lights/{index_code}"""

    def test_signal_lights_default_days(self):
        """默认 days=3 应返回 3 天信号"""
        mock_result = {
            "code": 0,
            "data": {
                "index_code": "SH000300",
                "signals": [
                    {"date": "2026-06-15", "level": 3, "label": "中性"},
                    {"date": "2026-06-16", "level": 3, "label": "中性"},
                    {"date": "2026-06-17", "level": 4, "label": "贪婪"},
                ],
            },
            "message": "ok",
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_signal_lights = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/signal-lights/SH000300")

        body = response.json()
        assert body["code"] == 0
        assert len(body["data"]["signals"]) == 3


class TestV5SnapshotEndpoint:
    """GET /api/v5/market/snapshot"""

    def test_snapshot_returns_4_indexes(self):
        """snapshot 应返回 4 指数摘要"""
        mock_result = {
            "code": 0,
            "data": {
                "indexes": [{"index_code": f"SH{i:06d}"} for i in range(4)],
                "global_sentiment": "neutral",
                "global_score": 52.0,
                "divergence_index": 0.0,
                "conclusion": "震荡",
                "updated_at": "2026-06-17T00:00:00",
            },
            "message": "ok",
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_market_snapshot = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/snapshot")

        body = response.json()
        assert body["code"] == 0
        assert len(body["data"]["indexes"]) == 4
        assert "global_sentiment" in body["data"]


class TestV5DivergenceEndpoint:
    """GET /api/v5/market/divergence"""

    def test_divergence_no_alert(self):
        """无背离时返回空 alerts"""
        mock_result = {
            "code": 0,
            "data": {"alerts": [], "divergence_index": 0.0},
            "message": "ok",
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_divergence_alert = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/divergence")

        body = response.json()
        assert body["code"] == 0
        assert body["data"]["alerts"] == []


class TestV5FactorRadarEndpoint:
    """GET /api/v5/market/factor-radar"""

    def test_factor_radar_default(self):
        """默认 SH000300 应返回 14 因子分位数值"""
        mock_result = {
            "code": 0,
            "data": {
                "index_code": "SH000300",
                "factors": [{"name": f"factor_{i}", "quantile": i / 14.0} for i in range(14)],
            },
            "message": "ok",
        }
        with patch("app.api.v5.sentiment_router.SentimentService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_factor_radar = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/factor-radar")

        body = response.json()
        assert body["code"] == 0
        assert len(body["data"]["factors"]) == 14


# ============================================================
# Factor data endpoint tests
# ============================================================
class TestV5FactorHeatmapEndpoint:
    """GET /api/v5/market/factor-heatmap"""

    def test_factor_heatmap_default(self):
        """默认 SH000300 应返回 14 因子热力图数据"""
        mock_result = {
            "code": 0,
            "data": {
                "index_code": "SH000300",
                "heatmap": [{"factor": f"f_{i}", "raw": 0.5, "quantile": 0.5, "sigmoid": 50.0} for i in range(14)],
            },
            "message": "ok",
        }
        with patch("app.api.v5.factor_data_router.FactorDataService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_factor_heatmap = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/factor-heatmap")

        body = response.json()
        assert body["code"] == 0
        assert len(body["data"]["heatmap"]) == 14


class TestV5SectorsEndpoint:
    """GET /api/v5/market/sectors"""

    def test_sectors_default(self):
        """默认参数应返回板块列表"""
        mock_result = {
            "code": 0,
            "data": {
                "items": [{"code": f"BK{i:04d}", "name": f"sector_{i}", "change_pct": 1.0} for i in range(10)],
                "total": 100,
                "page": 1,
                "page_size": 20,
            },
            "message": "ok",
        }
        with patch("app.api.v5.factor_data_router.FactorDataService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_sectors = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/sectors")

        body = response.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 100


class TestV5SectorDetailEndpoint:
    """GET /api/v5/market/sector/{code}"""

    def test_sector_detail(self):
        """单个板块应返回成分股"""
        mock_result = {
            "code": 0,
            "data": {
                "code": "BK0001",
                "name": "新能源",
                "stocks": [{"code": "600519", "name": "贵州茅台"}],
            },
            "message": "ok",
        }
        with patch("app.api.v5.factor_data_router.FactorDataService") as mock_svc:
            instance = mock_svc.return_value
            instance.get_sector_detail = AsyncMock(return_value=mock_result)

            response = client.get(f"{API_PREFIX}/market/sector/BK0001")

        body = response.json()
        assert body["code"] == 0
        assert body["data"]["code"] == "BK0001"


# ============================================================
# 路由可达性批量验证
# ============================================================
class TestV5RoutesReachability:
    """所有 V5 路由应可被注册（即使 handler 失败也不应 404）"""

    def test_all_v5_routes_registered(self):
        """验证 14 个 endpoint 都已注册到 OpenAPI schema"""
        schema = app.openapi()
        paths = schema["paths"].keys()
        expected = {
            "/api/v5/health",
            "/api/v5/market/sentiment/{index_code}",
            "/api/v5/market/multi-index",
            "/api/v5/market/signal-lights/{index_code}",
            "/api/v5/market/snapshot",
            "/api/v5/market/divergence",
            "/api/v5/market/factor-radar",
            "/api/v5/market/factor-heatmap",
            "/api/v5/market/sectors",
            "/api/v5/market/sector/{code}",
            "/api/v5/portfolio/position-advice",
            "/api/v5/portfolio/position-execute",
            "/api/v5/portfolio/{item_id}/market-value",
            "/api/v5/advice/dca/{index_code}",
        }
        missing = expected - set(paths)
        assert not missing, f"Missing routes: {missing}"

    def test_no_v1_routes_should_exist(self):
        """确认没有 /api/v1/* 路由（V1 时代已废弃）"""
        schema = app.openapi()
        v1_routes = [p for p in schema["paths"].keys() if "/v1/" in p]
        assert v1_routes == [], f"V1 routes should not exist: {v1_routes}"
