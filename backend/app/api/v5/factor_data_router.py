"""
V5 Factor Data Router - 因子数据查询路由（热力图 + 板块行情）
"""
from fastapi import APIRouter, Query

from app.services.factor_data_service import FactorDataService
from app.services.sentiment_service import SentimentService
from app.core.database import get_session
from app.core.redis_client import cache_get, cache_set
import time as _time
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

router = APIRouter(tags=["v5-factor-data"])


def _get_factor_data_service(session: AsyncSession = Depends(get_session)) -> FactorDataService:
    """DI 工厂：构造 FactorDataService（注入 SentimentService）"""
    sentiment_service = SentimentService(db_session=session)
    return FactorDataService(sentiment_service=sentiment_service)


@router.get("/market/factor-heatmap")
async def get_v5_factor_heatmap(
    index_code: str = Query(default="SH000300", description="指数代码"),
    service: FactorDataService = Depends(_get_factor_data_service),
) -> dict:
    """
    获取 V5.0 因子热力图数据

    返回14因子的原始值、分位数、Sigmoid 分数，用于调试和分析
    """
    return await service.get_factor_heatmap(index_code)


_SECTORS_CACHE_TTL = 86400  # 24h，日频数据


@router.get("/market/sectors")
async def get_v5_sectors(
    sector_type: str = Query("concept", description="板块类型: concept=概念, industry=行业"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    sort_by: str = Query("change_pct", description="排序字段: change_pct/main_net_inflow/main_pct"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
    service: FactorDataService = Depends(_get_factor_data_service),
) -> dict:
    """
    获取板块行情列表（概念板块或行业板块）

    数据来源：东方财富 push2 API → sector_scorer V5.0 增强评分
    带 Redis 缓存（24h TTL），日频数据无需频繁刷新
    """
    cache_key = f"v5:sectors:{sector_type}:{page}:{page_size}:{sort_by}:{sort_order}"

    # 先查缓存
    cached = await cache_get(cache_key)
    if cached:
        cached["data"]["cached"] = True
        cached["data"]["elapsed_seconds"] = 0.001
        return cached

    # 缓存未命中，调用服务
    start = _time.time()
    result = await service.get_sectors(
        sector_type=sector_type,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    elapsed = round(_time.time() - start, 2)

    # 补充元信息
    if isinstance(result, dict) and result.get("code") == 0:
        result["data"]["elapsed_seconds"] = elapsed
        result["data"]["cached"] = False

    # 写入缓存（仅成功结果）
    if isinstance(result, dict) and result.get("code") == 0:
        try:
            await cache_set(cache_key, result, ttl=_SECTORS_CACHE_TTL)
        except Exception:
            pass

    return result


_SECTOR_DETAIL_CACHE_TTL = 86400  # 24h，板块成分股日频数据

# 申万行业代码需要 .SI 后缀才能被 eastmoney 识别
_SW_SUFFIX = ".SI"


@router.get("/market/sector/{code}")
async def get_v5_sector_detail(
    code: str,
    service: FactorDataService = Depends(_get_factor_data_service),
) -> dict:
    """
    获取单个板块的成分股详情

    支持裸代码(801080)和带后缀代码(801080.SI)，自动统一为 .SI 格式。
    数据来源：东方财富 API，Redis 缓存 24h
    """
    # 统一代码格式：纯6位数字 → 加 .SI 后缀
    normalized_code = code if code.endswith(_SW_SUFFIX) else code + _SW_SUFFIX
    cache_key = f"v5:sector_detail:{normalized_code}"
    cached = await cache_get(cache_key)
    if cached:
        cached["data"]["cached"] = True
        cached["data"]["elapsed_seconds"] = 0.001
        return cached

    start = _time.time()
    result = await service.get_sector_detail(normalized_code)
    elapsed = round(_time.time() - start, 2)

    if isinstance(result, dict) and result.get("code") == 0:
        result["data"]["elapsed_seconds"] = elapsed
        result["data"]["cached"] = False
        try:
            await cache_set(cache_key, result, ttl=_SECTOR_DETAIL_CACHE_TTL)
        except Exception:
            pass

    return result
