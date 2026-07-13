"""
V5.0 专属接口
11因子流水线 + 7级信号 + 4星置信度 + 5×7仓位矩阵

路由前缀：/api/v5
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.core.config import settings
from app.utils.data_source import data_source, DEFAULT_INDEX_CODES
from app.engine.factor_engine import FACTOR_NAMES, FACTOR_CLASSES
from app.engine.quantile import QuantileNorm
from app.engine.sigmoid import SigmoidMapper
from app.engine.factor_engine.base import FactorSigmoidResult
from app.engine.aggregator_v5 import AggregatorV5
from app.engine.signal_mapper import SignalMapper
from app.engine.confidence import ConfidenceEngine
from app.engine.position_v5 import PositionEngineV5
from app.engine.sentiment_macd import SentimentMACD
from app.services.sentiment_service import SentimentService

router = APIRouter(prefix="/api/v5")


# ============================================================
# Pydantic 模型
# ============================================================

class PositionAdviceRequest(BaseModel):
    """仓位建议请求"""
    fund_code: str
    current_position_pct: float


class PositionExecuteRequest(BaseModel):
    """仓位执行请求"""
    fund_code: str
    target_position_pct: float
    signal_level: str
    confidence_stars: int


# ============================================================
# API 接口
# ============================================================

@router.get("/market/sentiment/{index_code}")
async def get_v5_sentiment(
    index_code: str,
    trade_date: Optional[str] = Query(default=None, description="交易日期 YYYY-MM-DD"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 指数情绪（11因子 + 7级信号 + 4星置信度）

    返回完整流水线结果，用于前端信号详情页
    """
    result = await SentimentService(session).run_pipeline(index_code, trade_date)

    if "error" in result:
        return {"code": 404, "data": None, "message": result["error"]}

    return {"code": 0, "data": result, "message": "ok"}


@router.get("/market/multi-index")
async def get_v5_multi_index(
    codes: Optional[str] = Query(default="SH000001,SH000300,SZ399001,SZ399006", description="指数代码，逗号分隔"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取多指数 V5.0 情绪摘要

    返回简化结果（不含因子明细），用于首页仪表盘
    """
    code_list = [c.strip() for c in codes.split(",")]
    items = []

    # NOTE(D9): 当前4指数串行for-loop，冷启动3-5秒。预热缓存已缓解。
    #    长期优化方向: asyncio.gather + 每指数独立session
    for code in code_list:
        result = await SentimentService(session).run_pipeline(code, persist=False)
        if "error" in result:
            continue

        # 简化：只保留摘要字段
        items.append({
            "index_code": result["index_code"],
            "index_name": result["index_name"],
            "composite_score": result["composite_score"],
            "signal_level": result["signal_level"],
            "confidence_stars": result["confidence_stars"],
            "regime": result["regime"],
        })

    # 综合情绪（市值加权：上证0.25 + 沪深300 0.30 + 深证0.25 + 创业板0.20）
    WEIGHT_MAP = {
        "SH000001": 0.25,   # 上证指数
        "SH000300": 0.30,   # 沪深300
        "SZ399001": 0.25,   # 深证成指
        "SZ399006": 0.20,   # 创业板指
    }
    weighted_score = 0.0
    total_weight = 0.0
    for item in items:
        w = WEIGHT_MAP.get(item["index_code"], 0.0)
        if w > 0:
            weighted_score += item["composite_score"] * w
            total_weight += w

    composite_score = round(weighted_score / total_weight, 2) if total_weight > 0 else 50.0

    # 综合信号：基于加权分数重新映射
    composite_signal = signal_mapper.map(composite_score)[0] if total_weight > 0 else "B"

    # 综合体制：取多数体制
    regime_counts: dict[str, int] = {}
    for item in items:
        r = item.get("regime", "sideways")
        regime_counts[r] = regime_counts.get(r, 0) + 1
    composite_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "sideways"

    return {
        "code": 0,
        "data": {
            "indexes": items,
            "composite": {
                "composite_score": composite_score,
                "signal_level": composite_signal,
                "regime": composite_regime,
            },
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.get("/market/signal-lights/{index_code}")
async def get_v5_signal_lights(
    index_code: str,
    days: int = Query(default=3, description="查看最近N天信号"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 信号灯数据（三周期）

    返回最近N天的信号等级，用于 SignalLights 组件
    """
    today = date.today()
    signals = []

    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        trade_date = d.isoformat()

        result = await SentimentService(session).run_pipeline(index_code, trade_date, persist=False)
        if "error" in result:
            signals.append({
                "date": trade_date,
                "signal_level": "B",
                "composite_score": 50.0,
            })
        else:
            signals.append({
                "date": trade_date,
                "signal_level": result["signal_level"],
                "composite_score": result["composite_score"],
                "confidence_stars": result["confidence_stars"],
            })

    return {
        "code": 0,
        "data": {
            "index_code": index_code,
            "signals": signals,
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.post("/portfolio/position-advice")
async def get_v5_position_advice(
    req: PositionAdviceRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 仓位调整建议

    输入：fund_code + current_position_pct
    输出：PositionAdvice（5×7矩阵 + 置信度修正 + 成本校验）
    """
    # 获取市场信号（默认用 SH000300 沪深300）
    index_code = "SH000300"
    result = await SentimentService(session).run_pipeline(index_code, persist=False)

    if "error" in result:
        return {"code": 500, "data": None, "message": "无法获取市场信号"}

    signal_level = result["signal_level"]
    confidence_stars = result["confidence_stars"]
    regime = result.get("regime", "sideways")

    # 计算仓位建议
    position_engine = PositionEngineV5(session)
    advice = await position_engine.calculate(
        user_id=user_id,
        fund_code=req.fund_code,
        current_position_pct=req.current_position_pct,
        signal_level=signal_level,
        confidence_stars=confidence_stars,
        regime=regime,
    )

    return {
        "code": 0,
        "data": advice,
        "message": "ok",
    }


@router.post("/portfolio/position-execute")
async def execute_v5_position(
    req: PositionExecuteRequest,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    执行 V5.0 仓位调整

    记录执行日志，更新用户持仓
    """
    from app.models.position_execution import PositionExecution
    from app.models.user_portfolio import UserPortfolio

    # 从DB查询用户实际持仓占比
    from_position_pct = 0.0
    try:
        stmt = (
            select(UserPortfolio)
            .where(
                UserPortfolio.user_id == user_id,
                UserPortfolio.fund_code == req.fund_code,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        portfolio = result.scalar_one_or_none()
        if portfolio and portfolio.market_value and portfolio.holding_shares > 0:
            # 简化：用持仓市值占比估算（需要用户总资产，此处暂用持仓比例）
            from_position_pct = round(portfolio.market_value / max(portfolio.holding_shares * portfolio.current_nav, 1.0), 4)
    except Exception:
        pass

    execution = PositionExecution(
        user_id=user_id,
        fund_code=req.fund_code,
        execute_date=date.today(),
        from_position_pct=from_position_pct,
        to_position_pct=req.target_position_pct,
        signal_level=req.signal_level,
        confidence_stars=req.confidence_stars,
    )
    session.add(execution)
    await session.commit()

    return {
        "code": 0,
        "data": {
            "execution_id": execution.id,
            "message": "执行成功",
        },
        "message": "ok",
    }


@router.get("/market/snapshot")
async def get_v5_market_snapshot(
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    市场快照（顶部状态条数据）

    返回关键指数摘要 + 全局情绪标签（基于 V5 pipeline）
    """
    index_data = await data_source.get_all_index_data()

    items = []
    for code in DEFAULT_INDEX_CODES:
        if code not in index_data:
            continue
        data = index_data[code]
        # 简化版：直接从数据源返回，不再走V1 compatibility
        result = await SentimentService(session).run_pipeline(code, persist=False)
        items.append({
            "index_code": code,
            "index_name": data.get("index_name", code),
            "close": data.get("close"),
            "change_pct": data.get("change_pct"),
            "composite_score": result.get("composite_score", 50.0) if "error" not in result else 50.0,
            "sentiment_label": result.get("signal_level", "B") if "error" not in result else "B",
        })

    # 综合情绪取第一个
    main = items[0] if items else None

    return {
        "code": 0,
        "data": {
            "indexes": items,
            "composite_score": main.get("composite_score", 50.0) if main else 50.0,
            "global_sentiment": main.get("sentiment_label", "B") if main else "B",
            "global_score": main.get("composite_score", 50.0) if main else 50.0,
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }


@router.get("/market/factor-heatmap")
async def get_v5_factor_heatmap(
    index_code: str = Query(default="SH000300", description="指数代码"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    获取 V5.0 因子热力图数据

    返回11因子的原始值、分位数、Sigmoid分数，用于调试和分析
    """
    result = await SentimentService(session).run_pipeline(index_code, persist=False)

    if "error" in result:
        return {"code": 404, "data": None, "message": result["error"]}

    return {
        "code": 0,
        "data": {
            "index_code": index_code,
            "composite_score": result["composite_score"],
            "signal_level": result["signal_level"],
            "factors": result["factor_details"],
            "updated_at": datetime.now().isoformat(),
        },
        "message": "ok",
    }
