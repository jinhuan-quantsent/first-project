"""
缓存版本号 API
前端轮询此接口，发现版本号变化才拉全量数据，避免无意义请求。
"""
from fastapi import APIRouter, Query

from app.core.redis_client import get_data_version

router = APIRouter(tags=["v5-cache"])


@router.get("/api/v5/cache/version")
async def get_cache_version(
    modules: str | None = Query(None, description="逗号分隔的模块名，如 signal_board,holdings"),
):
    """获取各模块数据版本号（最后更新时间）"""
    module_list = modules.split(",") if modules else None
    versions = await get_data_version(module_list)
    return {"code": 200, "data": versions}
