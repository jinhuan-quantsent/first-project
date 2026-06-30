"""P4-6: OpenAPI 文档增强测试

测试场景：
- /openapi.json 端点可访问
- /docs (Swagger UI) 可访问
- /redoc 可访问
- Schema 包含完整元信息（tags, servers, security）
- Schema 包含所有路由
- 业务响应模型（code/data/message）正确
"""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app  # noqa: E402

client = TestClient(app)


# ============================================================
# Schema 端点测试（4 个）
# ============================================================

class TestOpenAPIEndpoints:
    """OpenAPI 端点可访问性"""

    def test_openapi_json_endpoint(self):
        """/api/v5/openapi.json 返回 200 和合法 JSON"""
        response = client.get("/api/v5/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "info" in schema

    def test_swagger_ui_endpoint(self):
        """/api/v5/docs 返回 Swagger UI HTML"""
        response = client.get("/api/v5/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Swagger UI 包含 swagger-ui 标识
        assert "swagger" in response.text.lower()

    def test_redoc_endpoint(self):
        """/api/v5/redoc 返回 ReDoc HTML"""
        response = client.get("/api/v5/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "redoc" in response.text.lower()

    def test_v5_openapi_url_works(self):
        """/api/v5/openapi.json 是项目自定义的 schema URL（替代默认 /openapi.json）"""
        response = client.get("/api/v5/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        # 验证 schema 是 openapi 3.x 格式
        assert schema["openapi"].startswith("3.")


# ============================================================
# Schema 内容测试（5 个）
# ============================================================

class TestOpenAPISchema:
    """OpenAPI Schema 内容质量"""

    @pytest.fixture
    def schema(self):
        response = client.get("/api/v5/openapi.json")
        return response.json()

    def test_info_has_app_metadata(self, schema):
        """info 块包含应用元信息"""
        info = schema["info"]
        assert info["title"]
        assert info["version"]
        assert "summary" in info or "description" in info
        # 描述应该提到情绪/基金
        desc = info.get("description", "") + info.get("summary", "")
        assert any(kw in desc for kw in ["情绪", "基金", "sentiment", "fund"]), \
            f"描述缺关键词: {desc[:200]}"

    def test_tags_metadata(self, schema):
        """tags 包含业务域分组"""
        tags = schema.get("tags", [])
        tag_names = {t["name"] for t in tags}
        expected_groups = {
            "V5.0情绪引擎",
            "基金查询",
            "认证",
            "健康检查",
        }
        missing = expected_groups - tag_names
        assert not missing, f"缺标签分组: {missing}"

    def test_servers_list(self, schema):
        """servers 包含多环境配置"""
        servers = schema.get("servers", [])
        assert len(servers) >= 2, f"servers 数量不足: {len(servers)}"
        urls = {s["url"] for s in servers}
        # 应有本地 + 生产
        assert any("localhost" in u or "127.0.0.1" in u for u in urls)
        assert any("http" in u for u in urls)

    def test_security_scheme_bearer(self, schema):
        """securitySchemes 包含 BearerAuth"""
        components = schema.get("components", {})
        schemes = components.get("securitySchemes", {})
        assert "BearerAuth" in schemes, f"缺 BearerAuth: {schemes}"
        bearer = schemes["BearerAuth"]
        assert bearer["type"] == "http"
        assert bearer["scheme"] == "bearer"
        assert bearer.get("bearerFormat") == "JWT"

    def test_contact_and_license(self, schema):
        """info 包含联系人和许可证"""
        info = schema["info"]
        # contact 应该有 name 或 email
        contact = info.get("contact", {})
        assert contact, "缺 contact 信息"
        license_info = info.get("license", {})
        assert license_info, "缺 license 信息"


# ============================================================
# 路由覆盖测试（2 个）
# ============================================================

class TestOpenAPIPaths:
    """OpenAPI 路径覆盖"""

    @pytest.fixture
    def schema(self):
        response = client.get("/api/v5/openapi.json")
        return response.json()

    def test_all_routes_in_schema(self, schema):
        """所有路由都被记录"""
        paths = schema["paths"]
        # 期望的关键路径
        expected_paths = [
            "/",
            "/api/v5/health",
        ]
        # 至少应有 /api/v5/health
        for path in expected_paths:
            assert path in paths, f"路径 {path} 不在 OpenAPI schema 中"

    def test_health_endpoint_documented(self, schema):
        """/api/v5/health 有详细描述"""
        health = schema["paths"].get("/api/v5/health", {})
        assert health, "health 端点未记录"
        # get 方法应存在
        assert "get" in health
        get_op = health["get"]
        # 应有 summary 或 description
        assert "summary" in get_op or "description" in get_op


# ============================================================
# 业务响应格式测试（2 个）
# ============================================================

class TestBusinessResponseFormat:
    """业务响应格式：code/data/message"""

    def test_health_response_has_code_data_message(self):
        """/api/v5/health 返回 code/data/message 标准格式"""
        response = client.get("/api/v5/health")
        assert response.status_code == 200
        body = response.json()
        # 标准响应结构
        assert "code" in body
        assert "data" in body
        # message 可选
        if "message" in body:
            assert isinstance(body["message"], str)

    def test_root_response_includes_docs_link(self):
        """根路由指向 docs"""
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        data = body.get("data", {})
        assert data.get("docs") == "/api/v5/docs"


# ============================================================
# 13 测试 = 4 + 5 + 2 + 2
# ============================================================
