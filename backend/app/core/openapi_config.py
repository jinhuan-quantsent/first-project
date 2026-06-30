"""OpenAPI 元数据配置 - P4-6

集中管理 OpenAPI 文档的：
- 应用元信息（title, description, version）
- 联系人/许可证
- 标签分组（按业务域）
- 服务器列表（开发/生产）
- 通用响应示例
"""
from typing import List

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


# ============================================================
# 应用元信息
# ============================================================

OPENAPI_DESCRIPTION = """
# 基金情绪分析系统 V5.0 API 文档

为个人基金投资者提供实时情绪指标的大盘择时与基金优选决策工具。

## 核心功能

- **市场情绪分析**：基于多维度情绪指标实时分析大盘情绪
- **因子计算**：14 个核心情绪因子的计算、查询、回测
- **基金优选**：根据情绪指标筛选最优基金
- **投资组合管理**：自选基金、持仓跟踪
- **回测引擎**：基于历史数据验证策略有效性
- **智能建议**：基于情绪的择时与仓位建议

## 技术栈

- **后端**：FastAPI + SQLAlchemy 2.0 (async) + Pydantic 2
- **数据库**：SQLite (开发) / PostgreSQL + Supabase (生产)
- **缓存**：Redis
- **认证**：Supabase Auth (JWT)
- **监控**：Prometheus + Grafana
- **部署**：Aliyun ECS (Nginx + Gunicorn + Uvicorn)

## 认证

所有 V5.0 接口需要在 Header 中携带 JWT Token：

```
Authorization: Bearer <your-jwt-token>
```

可通过 `/api/v5/auth/signup` 或 `/api/v5/auth/login` 获取。

## 响应格式

所有接口统一返回格式：

```json
{
  "code": 0,
  "data": { ... },
  "message": "ok"
}
```

- `code = 0`：成功
- `code = -1`：系统错误
- `code = 401`：未认证
- `code = 403`：无权限
- `code = 404`：资源不存在
- `code = 429`：请求过快

## 错误处理

- 4xx：客户端错误，参数问题或权限不足
- 5xx：服务器内部错误，请查看日志
- 429：触发限流，请稍后重试

## 速率限制

- 匿名接口：60 req/min
- 认证接口：300 req/min
- 管理接口：1000 req/min
"""

OPENAPI_TAGS_METADATA: List[dict] = [
    {
        "name": "健康检查",
        "description": "服务健康检查、性能指标、系统状态",
    },
    {
        "name": "认证",
        "description": "用户注册、登录、登出、Token 刷新、密码重置",
    },
    {
        "name": "V5.0情绪引擎",
        "description": "V5.0 核心：多指数情绪、因子计算、信号生成、智能建议",
    },
    {
        "name": "基金查询",
        "description": "基金基本信息、净值、持仓、收益",
    },
    {
        "name": "市场数据",
        "description": "市场情绪、市场概览、热力图、行业板块",
    },
    {
        "name": "持仓管理",
        "description": "用户持仓管理、交易记录、收益统计",
    },
    {
        "name": "自选基金",
        "description": "自选基金管理（增删改查）",
    },
    {
        "name": "V5.0回测引擎",
        "description": "策略回测、收益曲线、绩效分析",
    },
]


OPENAPI_CONTACT = {
    "name": "基金情绪分析系统",
    "url": "https://github.com/your-repo/fund-sentiment-v5",
    "email": "support@example.com",
}

OPENAPI_LICENSE = {
    "name": "MIT License",
    "url": "https://opensource.org/licenses/MIT",
}

OPENAPI_SERVERS = [
    {
        "url": "http://localhost:8000",
        "description": "本地开发",
    },
    {
        "url": "https://fundsent.example.com",
        "description": "生产环境 (Aliyun ECS)",
    },
    {
        "url": "https://staging-fundsent.example.com",
        "description": "预发布环境",
    },
]


def custom_openapi(app: FastAPI):
    """生成增强版 OpenAPI schema

    特性：
    - 完整应用描述
    - 标签分组说明
    - 联系人/许可证
    - 多环境服务器列表
    - 安全方案（Bearer JWT）
    """

    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        summary="基金情绪分析系统 V5.0 API",
        description=OPENAPI_DESCRIPTION,
        routes=app.routes,
        tags=OPENAPI_TAGS_METADATA,
        contact=OPENAPI_CONTACT,
        license_info=OPENAPI_LICENSE,
        servers=OPENAPI_SERVERS,
    )

    # 添加安全方案（Bearer JWT）
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Supabase Auth 颁发的 JWT Token",
        }
    }

    # 给所有需要鉴权的接口添加安全要求
    security_optional = [
        # V5.0 情绪引擎：部分接口需要鉴权
        {"BearerAuth": []},
    ]

    # 默认安全应用到所有非 health 接口
    for path, path_item in openapi_schema["paths"].items():
        if "/health" in path or "/metrics" in path:
            continue
        for method, operation in path_item.items():
            if method in ("get", "post", "put", "delete", "patch"):
                # 不强制 security（部分接口允许匿名），但标注可选
                operation.setdefault("security", security_optional)

    app.openapi_schema = openapi_schema
    return openapi_schema
