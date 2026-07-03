"""
API integration tests using FastAPI TestClient

Tests all major endpoints:
- GET /api/v1/health
- GET /api/v1/market/multi-index
- GET /api/v1/market/snapshot
- GET /api/v1/fund/search
- GET /api/v1/fund/detail/{code}

Also verifies unified response format:
{"code": 0, "data": ..., "message": "ok"}

NOTE: We build a minimal FastAPI app to avoid pydantic-settings dependency
that is not installed in the test environment.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import router as health_router
from app.api.market import router as market_router
from app.api.fund import router as fund_router

# Build minimal app with only the routers we need
app = FastAPI()
API_PREFIX = "/api/v1"
app.include_router(health_router, prefix=API_PREFIX, tags=["健康检查"])
app.include_router(market_router, prefix=API_PREFIX, tags=["大盘情绪"])
app.include_router(fund_router, prefix=API_PREFIX, tags=["基金查询"])

client = TestClient(app)


# ============================================================
# Response format helper
# ============================================================
def assert_ok_response(response, status_code=200):
    """Assert standard success response format."""
    assert response.status_code == status_code, \
        f"Expected {status_code}, got {response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body["code"] == 0, f"Expected code=0, got {body['code']}"
    assert body["message"] == "ok"
    assert body["data"] is not None
    return body


def assert_error_response(response, status_code=200, expected_code=None):
    """Assert standard error response format."""
    body = response.json()
    if expected_code is not None:
        assert body["code"] == expected_code
    else:
        assert body["code"] != 0
    assert body["data"] is None or body["code"] == 404
    return body


# ============================================================
# Health check tests
# ============================================================
class TestHealthEndpoint:
    """Test GET /api/v1/health"""

    def test_health_returns_200(self):
        response = client.get(f"{API_PREFIX}/health")
        body = assert_ok_response(response)
        assert body["data"]["status"] == "healthy"
        assert body["data"]["version"] == "3.5.0"
        assert "timestamp" in body["data"]

    def test_health_response_format(self):
        """Health check must follow unified response format"""
        response = client.get(f"{API_PREFIX}/health")
        body = response.json()
        assert "code" in body
        assert "data" in body
        assert "message" in body
        assert isinstance(body["code"], int)
        assert isinstance(body["data"], dict)
        assert isinstance(body["message"], str)

    def test_health_has_required_fields(self):
        """Health check data must contain required fields"""
        response = client.get(f"{API_PREFIX}/health")
        body = response.json()
        data = body["data"]
        required_fields = ["status", "timestamp", "version", "db", "redis"]
        for field in required_fields:
            assert field in data, f"Missing field '{field}' in health response"


# ============================================================
# Multi-index endpoint tests
# ============================================================
class TestMultiIndexEndpoint:
    """Test GET /api/v1/market/multi-index"""

    def test_default_codes(self):
        """Default call returns 4 indexes"""
        response = client.get(f"{API_PREFIX}/market/multi-index")
        body = assert_ok_response(response)
        data = body["data"]
        assert "indexes" in data
        assert "composite" in data
        assert "updated_at" in data
        assert len(data["indexes"]) == 4

    def test_specific_codes(self):
        """Request specific indexes"""
        response = client.get(
            f"{API_PREFIX}/market/multi-index",
            params={"codes": "SH000001,SH000300"}
        )
        body = assert_ok_response(response)
        assert len(body["data"]["indexes"]) == 2

    def test_index_item_structure(self):
        """Each index item has required fields"""
        response = client.get(f"{API_PREFIX}/market/multi-index")
        body = response.json()
        for item in body["data"]["indexes"]:
            required_fields = [
                "index_code", "index_name", "close", "change_pct",
                "composite_score", "sentiment_label", "top3_factors",
                "trend_direction", "trend_strength", "is_extreme", "conclusion",
            ]
            for field in required_fields:
                assert field in item, f"Missing '{field}' in index item {item.get('index_code')}"

    def test_top3_factors_structure(self):
        """Top3 factors must have correct structure"""
        response = client.get(f"{API_PREFIX}/market/multi-index")
        body = response.json()
        for item in body["data"]["indexes"]:
            top3 = item["top3_factors"]
            assert 1 <= len(top3) <= 3, f"Expected 1-3 top factors, got {len(top3)}"
            for factor in top3:
                assert "factor_name" in factor
                assert "score" in factor
                assert "label" in factor
                assert "is_extreme" in factor

    def test_composite_structure(self):
        """Composite result has required fields"""
        response = client.get(f"{API_PREFIX}/market/multi-index")
        body = response.json()
        composite = body["data"]["composite"]
        required_fields = [
            "composite_score", "sentiment_label", "divergence_index",
            "conclusion", "operation_advice",
        ]
        for field in required_fields:
            assert field in composite, f"Missing '{field}' in composite"

    def test_sentiment_label_valid(self):
        """Sentiment labels must be valid"""
        valid_labels = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}
        response = client.get(f"{API_PREFIX}/market/multi-index")
        body = response.json()
        for item in body["data"]["indexes"]:
            assert item["sentiment_label"] in valid_labels, \
                f"Invalid sentiment label: {item['sentiment_label']}"
        assert body["data"]["composite"]["sentiment_label"] in valid_labels

    def test_composite_score_in_range(self):
        """Composite score must be 0-100"""
        response = client.get(f"{API_PREFIX}/market/multi-index")
        body = response.json()
        for item in body["data"]["indexes"]:
            assert 0 <= item["composite_score"] <= 100, \
                f"Score {item['composite_score']} out of range for {item['index_code']}"
        assert 0 <= body["data"]["composite"]["composite_score"] <= 100

    def test_single_code(self):
        """Single index code should work"""
        response = client.get(
            f"{API_PREFIX}/market/multi-index",
            params={"codes": "SH000001"}
        )
        body = assert_ok_response(response)
        assert len(body["data"]["indexes"]) == 1

    def test_invalid_code_ignored(self):
        """Invalid codes should be silently ignored"""
        response = client.get(
            f"{API_PREFIX}/market/multi-index",
            params={"codes": "INVALID,SH000001"}
        )
        body = assert_ok_response(response)
        assert len(body["data"]["indexes"]) == 1


# ============================================================
# Market snapshot endpoint tests
# ============================================================
class TestMarketSnapshotEndpoint:
    """Test GET /api/v1/market/snapshot"""

    def test_snapshot_returns_ok(self):
        response = client.get(f"{API_PREFIX}/market/snapshot")
        body = assert_ok_response(response)
        data = body["data"]
        assert "indexes" in data
        assert "global_sentiment" in data
        assert "global_score" in data
        assert "divergence_index" in data
        assert "conclusion" in data
        assert "updated_at" in data

    def test_snapshot_has_4_indexes(self):
        response = client.get(f"{API_PREFIX}/market/snapshot")
        body = response.json()
        assert len(body["data"]["indexes"]) == 4

    def test_snapshot_index_structure(self):
        """Snapshot index items must have the IndexSnapshot structure"""
        response = client.get(f"{API_PREFIX}/market/snapshot")
        body = response.json()
        for item in body["data"]["indexes"]:
            required_fields = [
                "index_code", "index_name", "close", "change_pct",
                "composite_score", "sentiment_label",
            ]
            for field in required_fields:
                assert field in item, f"Missing '{field}' in snapshot index"

    def test_snapshot_global_sentiment_valid(self):
        """Global sentiment label must be valid"""
        valid_labels = {"extreme_fear", "fear", "neutral", "greed", "extreme_greed"}
        response = client.get(f"{API_PREFIX}/market/snapshot")
        body = response.json()
        assert body["data"]["global_sentiment"] in valid_labels

    def test_snapshot_global_score_in_range(self):
        """Global score must be 0-100"""
        response = client.get(f"{API_PREFIX}/market/snapshot")
        body = response.json()
        assert 0 <= body["data"]["global_score"] <= 100


# ============================================================
# Fund search endpoint tests
# ============================================================
class TestFundSearchEndpoint:
    """Test GET /api/v1/fund/search"""

    def test_search_all_funds(self):
        """Search without keyword returns all funds"""
        response = client.get(f"{API_PREFIX}/fund/search")
        body = assert_ok_response(response)
        data = body["data"]
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] > 0
        assert len(data["items"]) > 0

    def test_search_by_name(self):
        """Search by fund name"""
        response = client.get(
            f"{API_PREFIX}/fund/search",
            params={"keyword": "华夏"}
        )
        body = assert_ok_response(response)
        items = body["data"]["items"]
        assert len(items) >= 1
        for item in items:
            assert "华夏" in item["fund_name"]

    def test_search_by_code(self):
        """Search by fund code"""
        response = client.get(
            f"{API_PREFIX}/fund/search",
            params={"keyword": "000001"}
        )
        body = assert_ok_response(response)
        items = body["data"]["items"]
        assert len(items) >= 1
        assert items[0]["fund_code"] == "000001"

    def test_search_by_manager(self):
        """Search by manager name"""
        response = client.get(
            f"{API_PREFIX}/fund/search",
            params={"keyword": "张坤"}
        )
        body = assert_ok_response(response)
        items = body["data"]["items"]
        assert len(items) >= 1

    def test_search_no_results(self):
        """Search for non-existent fund"""
        response = client.get(
            f"{API_PREFIX}/fund/search",
            params={"keyword": "不存在的基金xyz"}
        )
        body = assert_ok_response(response)
        assert body["data"]["total"] == 0
        assert len(body["data"]["items"]) == 0

    def test_search_by_type(self):
        """Filter by fund type"""
        response = client.get(
            f"{API_PREFIX}/fund/search",
            params={"fund_type": "指数型"}
        )
        body = assert_ok_response(response)
        for item in body["data"]["items"]:
            assert item["fund_type"] == "指数型"

    def test_search_pagination(self):
        """Pagination should work"""
        response = client.get(
            f"{API_PREFIX}/fund/search",
            params={"page": 1, "page_size": 2}
        )
        body = assert_ok_response(response)
        assert body["data"]["page"] == 1
        assert body["data"]["page_size"] == 2
        assert len(body["data"]["items"]) <= 2

    def test_search_result_structure(self):
        """Search result items must have correct structure"""
        response = client.get(f"{API_PREFIX}/fund/search")
        body = response.json()
        for item in body["data"]["items"]:
            required_fields = [
                "fund_code", "fund_name", "fund_short_name", "fund_type",
                "nav", "daily_return", "week_return", "month_return",
                "year_return", "fund_size", "risk_level",
            ]
            for field in required_fields:
                assert field in item, f"Missing '{field}' in search result"


# ============================================================
# Fund detail endpoint tests
# ============================================================
class TestFundDetailEndpoint:
    """Test GET /api/v1/fund/detail/{code}"""

    def test_detail_existing_fund(self):
        """Get detail for existing fund"""
        response = client.get(f"{API_PREFIX}/fund/detail/000001")
        body = assert_ok_response(response)
        data = body["data"]
        assert data["fund_code"] == "000001"
        assert data["fund_name"] == "华夏成长混合"

    def test_detail_has_complete_info(self):
        """Detail must contain all fund info fields"""
        response = client.get(f"{API_PREFIX}/fund/detail/000001")
        body = response.json()
        data = body["data"]
        required_fields = [
            "fund_code", "fund_name", "fund_short_name", "fund_type",
            "manager", "company", "inception_date", "nav", "accumulated_nav",
            "fund_size", "benchmark", "tracking_index", "risk_level",
            "daily_return", "week_return", "month_return", "year_return",
            "description",
        ]
        for field in required_fields:
            assert field in data, f"Missing '{field}' in fund detail"

    def test_detail_has_nav_history(self):
        """Detail must include NAV history"""
        response = client.get(f"{API_PREFIX}/fund/detail/000001")
        body = response.json()
        data = body["data"]
        assert "nav_history" in data
        assert len(data["nav_history"]) > 0
        for point in data["nav_history"]:
            assert "date" in point
            assert "nav" in point
            assert "daily_return" in point

    def test_detail_nonexistent_fund(self):
        """Non-existent fund returns 404"""
        response = client.get(f"{API_PREFIX}/fund/detail/999999")
        body = assert_error_response(response, expected_code=404)
        assert "不存在" in body["message"]

    def test_detail_all_mock_funds(self):
        """All 6 mock funds should be accessible"""
        codes = ["000001", "001632", "320007", "110022", "005827", "012345"]
        for code in codes:
            response = client.get(f"{API_PREFIX}/fund/detail/{code}")
            assert response.json()["code"] == 0, f"Fund {code} returned error"


# ============================================================
# Index detail endpoint tests
# ============================================================
class TestIndexDetailEndpoint:
    """Test GET /api/v1/market/index/{code}"""

    def test_index_detail_existing(self):
        """Get detail for existing index"""
        response = client.get(f"{API_PREFIX}/market/index/SH000001")
        body = assert_ok_response(response)
        data = body["data"]
        assert data["index_code"] == "SH000001"
        assert data["index_name"] == "上证综指"

    def test_index_detail_has_factor_scores(self):
        """Index detail must have 7 factor scores"""
        response = client.get(f"{API_PREFIX}/market/index/SH000001")
        body = response.json()
        data = body["data"]
        assert "factor_scores" in data
        assert len(data["factor_scores"]) == 7

    def test_index_detail_has_position_advice(self):
        """Index detail must have position advice"""
        response = client.get(f"{API_PREFIX}/market/index/SH000001")
        body = response.json()
        data = body["data"]
        assert "position_advice" in data
        pa = data["position_advice"]
        assert "suggested_position" in pa
        assert "cash_reserve" in pa
        assert "action" in pa
        assert "reason" in pa
        assert "risk_level" in pa

    def test_index_detail_has_history(self):
        """Index detail must have sentiment history"""
        response = client.get(f"{API_PREFIX}/market/index/SH000001")
        body = response.json()
        data = body["data"]
        assert "history" in data
        assert len(data["history"]) > 0
        for point in data["history"]:
            assert "date" in point
            assert "composite_score" in point
            assert "sentiment_label" in point

    def test_index_detail_nonexistent(self):
        """Non-existent index returns 404"""
        response = client.get(f"{API_PREFIX}/market/index/INVALID")
        body = assert_error_response(response, expected_code=404)

    def test_all_4_indexes_accessible(self):
        """All 4 mock indexes should be accessible"""
        codes = ["SH000001", "SH000300", "SZ399001", "SZ399006"]
        for code in codes:
            response = client.get(f"{API_PREFIX}/market/index/{code}")
            assert response.json()["code"] == 0, f"Index {code} returned error"


# ============================================================
# Cross-cutting response format tests
# ============================================================
class TestResponseFormat:
    """Test unified response format across all endpoints"""

    ENDPOINTS = [
        f"{API_PREFIX}/health",
        f"{API_PREFIX}/market/multi-index",
        f"{API_PREFIX}/market/snapshot",
        f"{API_PREFIX}/fund/search",
        f"{API_PREFIX}/fund/detail/000001",
        f"{API_PREFIX}/market/index/SH000001",
    ]

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_unified_response_format(self, endpoint):
        """All endpoints must follow {code, data, message} format"""
        response = client.get(endpoint)
        body = response.json()
        assert "code" in body, f"Missing 'code' in {endpoint}"
        assert "data" in body, f"Missing 'data' in {endpoint}"
        assert "message" in body, f"Missing 'message' in {endpoint}"

    @pytest.mark.parametrize("endpoint", ENDPOINTS)
    def test_success_endpoints_code_zero(self, endpoint):
        """All success endpoints should return code=0"""
        response = client.get(endpoint)
        body = response.json()
        assert body["code"] == 0, f"Expected code=0 for {endpoint}, got {body['code']}"

    def test_404_response_format(self):
        """404 responses should also follow the format with data=None"""
        response = client.get(f"{API_PREFIX}/fund/detail/999999")
        body = response.json()
        assert body["code"] == 404
        assert body["data"] is None
        assert isinstance(body["message"], str)
        assert len(body["message"]) > 0
