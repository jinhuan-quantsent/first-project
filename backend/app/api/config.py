"""
配置版本管理接口
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()

# Mock 配置版本
MOCK_CONFIG_VERSIONS = [
    {
        "version": "v3.5.0",
        "released_at": "2025-01-15T10:00:00",
        "changes": [
            "新增7因子评分模型",
            "引入市值加权的多指数综合情绪",
            "新增板块情绪热力图",
        ],
        "weights": {
            "波动率": 0.15,
            "换手率": 0.10,
            "涨跌比": 0.15,
            "新高占比": 0.12,
            "融资融券": 0.18,
            "股债比": 0.15,
            "RSI": 0.15,
        },
    },
    {
        "version": "v3.4.0",
        "released_at": "2024-12-01T10:00:00",
        "changes": [
            "优化波动率评分区间",
            "新增融资融券因子",
            "调整因子权重",
        ],
        "weights": {
            "波动率": 0.20,
            "换手率": 0.10,
            "涨跌比": 0.15,
            "新高占比": 0.10,
            "融资融券": 0.15,
            "股债比": 0.15,
            "RSI": 0.15,
        },
    },
    {
        "version": "v3.3.0",
        "released_at": "2024-10-20T10:00:00",
        "changes": [
            "初始7因子模型上线",
        ],
        "weights": {
            "波动率": 0.20,
            "换手率": 0.10,
            "涨跌比": 0.20,
            "新高占比": 0.10,
            "融资融券": 0.10,
            "股债比": 0.15,
            "RSI": 0.15,
        },
    },
]


@router.get("/config/versions")
async def get_config_versions() -> dict:
    """获取配置版本列表"""
    return {
        "code": 0,
        "data": {
            "current_version": "v3.5.0",
            "versions": MOCK_CONFIG_VERSIONS,
        },
        "message": "ok",
    }


@router.post("/config/rollback")
async def rollback_config(
    target_version: str = Query(..., description="目标版本号"),
) -> dict:
    """回滚到指定配置版本"""
    version = None
    for v in MOCK_CONFIG_VERSIONS:
        if v["version"] == target_version:
            version = v
            break

    if not version:
        return {"code": 404, "data": None, "message": f"版本 {target_version} 不存在"}

    return {
        "code": 0,
        "data": {
            "rolled_back_to": target_version,
            "weights": version["weights"],
            "rolled_back_at": datetime.now().isoformat(),
        },
        "message": f"已回滚至 {target_version}",
    }


@router.post("/config/apply-optimization")
async def apply_optimization() -> dict:
    """应用优化建议"""
    return {
        "code": 0,
        "data": {
            "applied": True,
            "new_params": {
                "sentiment_threshold_buy": 25.0,
                "sentiment_threshold_sell": 72.0,
            },
            "applied_at": datetime.now().isoformat(),
        },
        "message": "优化参数已应用",
    }
