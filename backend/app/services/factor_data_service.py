"""
Factor Data Service - V5.0 因子数据查询
包含因子热力图、单因子查询、板块行情
"""
import logging

from app.core.redis_client import cache_get, cache_set
from app.utils.eastmoney import get_sector_list, get_sector_detail
from app.engine.sector_scorer import score_sectors
from app.services.sentiment_service import SentimentService

logger = logging.getLogger(__name__)


class FactorDataService:
    """
    V5.0 因子数据 Service

    职责：
    1. 因子热力图数据
    2. 板块行情列表（东方财富 → sector_scorer V5.0 增强评分）
    3. 单板块详情
    """

    def __init__(self, sentiment_service: SentimentService = None):
        self.sentiment_service = sentiment_service

    async def get_factor_heatmap(self, index_code: str = "SH000300") -> dict:
        """
        获取 V5.0 因子热力图数据

        返回 14 因子的原始值、分位数、Sigmoid 分数，用于调试和分析
        """
        if self.sentiment_service is None:
            raise ValueError("sentiment_service is required for factor_heatmap")

        result = await self.sentiment_service.run_pipeline(index_code)

        if "error" in result:
            return {"code": 404, "data": None, "message": result["error"]}

        return {
            "code": 0,
            "data": {
                "index_code": index_code,
                "composite_score": result["composite_score"],
                "signal_level": result["signal_level"],
                "factors": result["factor_details"],
                "updated_at": result.get("updated_at"),
            },
            "message": "ok",
        }

    async def get_sectors(
        self,
        sector_type: str = "concept",
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "change_pct",
        sort_order: str = "desc",
    ) -> dict:
        """
        获取板块行情列表（概念板块或行业板块）

        数据来源：东方财富 push2 API → sector_scorer V5.0 增强评分
        返回板块涨跌幅、主力净流入、情绪评分、信号等级、结构化理由等
        """
        if sector_type not in ("concept", "industry"):
            return {"code": 400, "data": None, "message": "sector_type must be 'concept' or 'industry'"}

        raw = await get_sector_list(
            sector_type=sector_type,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        # 通过 sector_scorer V5.0 增强评分（6 因子 + 信号等级 + 结构化理由）
        items = raw.get("items", []) if isinstance(raw, dict) else []
        if items:
            scored = await score_sectors(items)
            pagination = raw.get("pagination", {}) if isinstance(raw, dict) else {}
            return {
                "code": 0,
                "data": {
                    "items": scored,
                    "pagination": pagination,
                },
                "message": "ok",
            }

        # 降级：原始数据无 items 时直接返回
        return {
            "code": 0,
            "data": raw,
            "message": "ok",
        }

    async def get_sector_detail(self, code: str) -> dict:
        """
        获取单个板块的成分股详情

        返回板块内个股涨跌、主力净流入，以及涨幅前5/跌幅前5
        """
        result = await get_sector_detail(code)

        if result is None:
            return {"code": 404, "data": None, "message": f"板块 {code} 未找到"}

        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
