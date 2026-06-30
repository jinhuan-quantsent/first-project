"""
V5 Factor Data Router - 因子数据查询路由（热力图 + 板块行情）
"""
from fastapi import APIRouter, Query

from app.services.factor_data_service import FactorDataService
from app.services.sentiment_service import SentimentService
from app.core.database import get_session
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
    """
    return await service.get_sectors(
        sector_type=sector_type,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/market/sector/{code}")
async def get_v5_sector_detail(
    code: str,
    service: FactorDataService = Depends(_get_factor_data_service),
) -> dict:
    """
    获取单个板块的成分股详情
    """
    return await service.get_sector_detail(code)
