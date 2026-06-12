"""
基金相关接口
搜索和详情查询
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()


# Mock 基金数据
MOCK_FUNDS: list[dict] = [
    {
        "fund_code": "000001",
        "fund_name": "华夏成长混合",
        "fund_short_name": "华夏成长",
        "fund_type": "混合型",
        "manager": "王亚伟",
        "company": "华夏基金",
        "inception_date": "2001-12-18",
        "nav": 1.5240,
        "accumulated_nav": 3.9850,
        "fund_size": 85.6,
        "benchmark": "沪深300指数×80%+上证国债指数×20%",
        "tracking_index": "SH000300",
        "risk_level": "R3",
        "daily_return": 0.52,
        "week_return": 1.85,
        "month_return": -2.35,
        "year_return": 8.52,
        "description": "主要投资于具有良好成长性的上市公司的股票",
    },
    {
        "fund_code": "001632",
        "fund_name": "天弘中证食品饮料ETF联接A",
        "fund_short_name": "食品饮料ETF联接",
        "fund_type": "指数型",
        "manager": "沙川",
        "company": "天弘基金",
        "inception_date": "2015-07-29",
        "nav": 2.3850,
        "accumulated_nav": 2.3850,
        "fund_size": 45.2,
        "benchmark": "中证食品饮料指数收益率×95%+银行活期存款利率×5%",
        "tracking_index": "SZ399001",
        "risk_level": "R4",
        "daily_return": -0.35,
        "week_return": 1.25,
        "month_return": -1.85,
        "year_return": 12.35,
        "description": "紧密跟踪中证食品饮料指数",
    },
    {
        "fund_code": "320007",
        "fund_name": "诺安成长混合",
        "fund_short_name": "诺安成长",
        "fund_type": "混合型",
        "manager": "蔡嵩松",
        "company": "诺安基金",
        "inception_date": "2009-03-10",
        "nav": 1.1250,
        "accumulated_nav": 1.5700,
        "fund_size": 128.3,
        "benchmark": "中证800指数收益率×70%+中证综合债券指数收益率×30%",
        "tracking_index": "SH000300",
        "risk_level": "R4",
        "daily_return": 2.85,
        "week_return": 5.52,
        "month_return": 8.25,
        "year_return": 25.8,
        "description": "聚焦半导体及科技成长领域",
    },
    {
        "fund_code": "110022",
        "fund_name": "易方达消费行业股票",
        "fund_short_name": "易方达消费",
        "fund_type": "股票型",
        "manager": "萧楠",
        "company": "易方达基金",
        "inception_date": "2010-08-20",
        "nav": 3.8520,
        "accumulated_nav": 3.8520,
        "fund_size": 210.5,
        "benchmark": "中证内地消费主题指数×80%+中证综合债券指数×20%",
        "tracking_index": "SH000300",
        "risk_level": "R4",
        "daily_return": -0.85,
        "week_return": -2.15,
        "month_return": -5.28,
        "year_return": -8.5,
        "description": "主要投资消费行业优质上市公司",
    },
    {
        "fund_code": "005827",
        "fund_name": "易方达蓝筹精选混合",
        "fund_short_name": "易方达蓝筹",
        "fund_type": "混合型",
        "manager": "张坤",
        "company": "易方达基金",
        "inception_date": "2018-09-05",
        "nav": 2.1580,
        "accumulated_nav": 2.1580,
        "fund_size": 520.8,
        "benchmark": "沪深300指数收益率×45%+中证港股通综合指数收益率×35%+中债总财富指数收益率×20%",
        "tracking_index": "SH000300",
        "risk_level": "R3",
        "daily_return": 0.15,
        "week_return": 0.85,
        "month_return": -1.52,
        "year_return": 3.28,
        "description": "在控制风险的前提下，追求超越业绩比较基准的投资回报",
    },
    {
        "fund_code": "012345",
        "fund_name": "招商中证白酒指数(LOF)A",
        "fund_short_name": "招商白酒",
        "fund_type": "指数型",
        "manager": "侯昊",
        "company": "招商基金",
        "inception_date": "2015-05-27",
        "nav": 0.9850,
        "accumulated_nav": 2.3850,
        "fund_size": 380.2,
        "benchmark": "中证白酒指数收益率×95%+金融机构人民币活期存款基准利率×5%",
        "tracking_index": "SZ399001",
        "risk_level": "R4",
        "daily_return": -1.25,
        "week_return": -3.52,
        "month_return": -7.85,
        "year_return": -15.2,
        "description": "紧密跟踪中证白酒指数",
    },
]


@router.get("/fund/search")
async def search_funds(
    keyword: str = Query(default="", description="搜索关键词"),
    fund_type: Optional[str] = Query(default=None, description="基金类型筛选"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=50, description="每页数量"),
) -> dict:
    """
    基金搜索

    支持按名称、代码、类型搜索
    """
    results = MOCK_FUNDS

    if keyword:
        keyword_lower = keyword.lower()
        results = [
            f for f in results
            if keyword_lower in f["fund_code"].lower()
            or keyword_lower in f["fund_name"].lower()
            or keyword_lower in f["fund_short_name"].lower()
            or keyword_lower in f["manager"].lower()
        ]

    if fund_type:
        results = [f for f in results if f["fund_type"] == fund_type]

    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    paged_results = results[start:end]

    # 简化的搜索结果
    items = [
        {
            "fund_code": f["fund_code"],
            "fund_name": f["fund_name"],
            "fund_short_name": f["fund_short_name"],
            "fund_type": f["fund_type"],
            "nav": f["nav"],
            "daily_return": f["daily_return"],
            "week_return": f["week_return"],
            "month_return": f["month_return"],
            "year_return": f["year_return"],
            "fund_size": f["fund_size"],
            "risk_level": f["risk_level"],
        }
        for f in paged_results
    ]

    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "message": "ok",
    }


@router.get("/fund/detail/{code}")
async def get_fund_detail(code: str) -> dict:
    """
    获取基金详情

    包含完整信息 + 净值历史（Mock）
    """
    fund = None
    for f in MOCK_FUNDS:
        if f["fund_code"] == code:
            fund = f
            break

    if not fund:
        return {"code": 404, "data": None, "message": f"基金 {code} 不存在"}

    # Mock 净值历史（最近30天）
    today = date.today()
    nav_history = []
    base_nav = fund["nav"]
    for i in range(30, 0, -1):
        d = today - timedelta(days=i)
        # 模拟随机波动
        import random
        random.seed(hash(f"{code}{d.isoformat()}") % (2**31))
        daily_change = (random.random() - 0.48) * 0.03  # -1.44% ~ +1.56%
        nav_value = round(base_nav * (1 + sum(
            (random.random() - 0.48) * 0.03
            for _ in range(i)
        ) * 0.3), 4)
        nav_history.append({
            "date": d.isoformat(),
            "nav": max(0.5, nav_value),
            "daily_return": round(daily_change * 100, 2),
        })

    return {
        "code": 0,
        "data": {
            **fund,
            "nav_history": nav_history[-20:],  # 最近20天
        },
        "message": "ok",
    }
