"""
基金相关接口 V5.0 — 真实数据源版
搜索和详情查询

数据源优先级：
  搜索：东方财富API → Tushare fund_basic → 空结果
  详情：东方财富估值 + Tushare净值/基础信息 → 空结果
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.utils.eastmoney import (
    search_funds_combined,
    get_fund_detail_combined,
    get_fund_realtime,
    code_to_tushare,
)

router = APIRouter()


@router.get("/search")
async def search_funds(
    keyword: str = Query(default="", description="搜索关键词(代码/名称/拼音)"),
    fund_type: Optional[str] = Query(default=None, description="基金类型筛选: 股票型/混合型/指数型/债券型/货币型/QDII/FOF"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页数量"),
) -> dict:
    """
    基金搜索

    支持按名称、代码、拼音搜索
    数据源：东方财富搜索API → Tushare → 空
    """
    if not keyword.strip():
        return {
            "code": 0,
            "data": {"items": [], "total": 0, "page": page, "page_size": page_size},
            "message": "请输入搜索关键词",
        }

    result = await search_funds_combined(
        keyword=keyword.strip(),
        page=page,
        page_size=page_size,
        fund_type=fund_type,
    )

    # 统一输出格式
    items = []
    for f in result.get("items", []):
        items.append({
            "fund_code": f.get("fund_code", ""),
            "fund_name": f.get("fund_name", ""),
            "fund_short_name": f.get("fund_short_name", f.get("fund_name", "")[:8]),
            "fund_type": f.get("fund_type", ""),
            "nav": f.get("nav", 0.0),
            "daily_return": f.get("daily_return", 0.0),
            "week_return": f.get("week_return", 0.0),
            "month_return": f.get("month_return", 0.0),
            "year_return": f.get("year_return", 0.0),
            "fund_size": f.get("fund_size", 0.0),
            "risk_level": f.get("risk_level", ""),
            "manager": f.get("manager", ""),
            "company": f.get("company", ""),
            "is_buy": f.get("is_buy", True),
        })

    return {
        "code": 0,
        "data": {
            "items": items,
            "total": result.get("total", 0),
            "page": result.get("page", page),
            "page_size": result.get("page_size", page_size),
        },
        "message": "ok",
    }


@router.get("/detail/{code}")
async def get_fund_detail(code: str) -> dict:
    """
    获取基金详情

    数据源：东方财富实时估值 + Tushare基础信息/净值历史 + 东方财富持仓
    包含完整信息 + 30天净值历史
    """
    # 清理代码格式
    code = code.strip().split(".")[0]

    detail = await get_fund_detail_combined(code)

    if not detail:
        return {"code": 404, "data": None, "message": f"基金 {code} 不存在或数据获取失败"}

    # 标准化输出（与前端FundDetail类型对齐）
    output = {
        "fund_code": detail.get("fund_code", code),
        "fund_name": detail.get("fund_name", ""),
        "fund_short_name": detail.get("fund_short_name", detail.get("fund_name", "")[:8]),
        "fund_type": detail.get("fund_type", ""),
        "manager": detail.get("manager", ""),
        "company": detail.get("company", ""),
        "inception_date": detail.get("inception_date", ""),
        "nav": detail.get("nav", 0.0),
        "accumulated_nav": detail.get("accumulated_nav", 0.0),
        "fund_size": detail.get("fund_size", 0.0),
        "benchmark": detail.get("benchmark", ""),
        "tracking_index": detail.get("tracking_index", ""),
        "risk_level": detail.get("risk_level", "R3"),
        "daily_return": detail.get("daily_return", 0.0),
        "week_return": detail.get("week_return", 0.0),
        "month_return": detail.get("month_return", 0.0),
        "year_return": detail.get("year_return", 0.0),
        "description": detail.get("description", ""),
        # 实时估值
        "realtime": detail.get("realtime"),
        # 净值历史（前端需要 date + nav + daily_return）
        "nav_history": [
            {
                "date": h.get("date", ""),
                "nav": h.get("nav", 0.0),
                "daily_return": h.get("daily_return", 0.0),
            }
            for h in detail.get("nav_history", [])
        ],
        # 重仓股
        "top_holdings": detail.get("top_holdings", []),
        # 数据来源标记
        "_data_source": detail.get("_data_source", "real"),
    }

    return {"code": 0, "data": output, "message": "ok"}


@router.get("/sectors")
async def get_fund_sectors(
    fund_code: str = Query(default="", description="基金代码"),
) -> dict:
    """
    基金板块分布（预留接口）
    后续对接东方财富板块行情数据
    """
    return {
        "code": 0,
        "data": [],
        "message": "板块数据接口待接入",
    }
