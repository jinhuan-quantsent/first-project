"""
自选基金接口
V4.0：注入 get_current_user，Mock → ORM CRUD
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_session
from app.models.user_watchlist import UserWatchlist
from app.models.fund_mapping import FundMapping
from app.core.config import settings
from app.engine.position_rating import calculate_position_ratings_for_all, RATING_CONFIG
from app.core.redis_client import cache_get, cache_set, cache_delete
import time as _time

_WATCHLIST_CACHE_TTL = 300  # 5分钟（盘中数据）
_WATCHLIST_CACHE_KEY = "v5:watchlist"
_POS_RATING_CACHE_KEY_ALL = "v5:pos_rating:all"

router = APIRouter(prefix="/api/v5/watchlist")


class WatchlistAdd(BaseModel):
    """添加自选"""
    fund_code: str
    fund_name: str = ""
    notes: str = ""
    alert_threshold: float = 0.0


@router.get("")
async def get_watchlist(
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """获取自选列表（含实时净值数据）"""
    # HTTP级缓存（5分钟TTL，盘中数据）
    cache_key = f"v5:watchlist:{user_id}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    from app.utils.eastmoney import get_fund_realtime, get_fund_nav_history, code_to_tushare
    import asyncio

    stmt = (
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user_id)
        .order_by(UserWatchlist.sort_order.asc(), UserWatchlist.added_at.desc())
    )
    result = await session.execute(stmt)
    items = result.scalars().all()

    if not items:
        return {"code": 0, "data": [], "message": "ok"}

    # 批量查询 fund_mapping 为每只基金附加板块信息（ORM参数化查询，无SQL注入风险）
    fund_codes = [it.fund_code for it in items]
    sector_map = {}
    try:
        stmt_fm = select(FundMapping).where(FundMapping.fund_code.in_(fund_codes))
        result_fm = await session.execute(stmt_fm)
        for fm_row in result_fm.scalars().all():
            sector_map[fm_row.fund_code] = {
                "sector_code": fm_row.index_code,
                "category": fm_row.category,
                "mapped_name": fm_row.fund_name or "",
            }
    except Exception:
        pass

    # 并行获取每只基金的实时估值数据
    async def enrich(fund_code: str) -> dict:
        nav = 0.0
        daily_ret = 0.0
        week_ret = 0.0
        month_ret = 0.0
        try:
            rt = await get_fund_realtime(fund_code)
            if rt:
                nav = rt.get("estimated_nav") or rt.get("nav", 0.0) or 0.0
                daily_ret = rt.get("estimated_change", 0.0) or 0.0
        except Exception:
            pass
        try:
            ts_code = code_to_tushare(fund_code)
            hist = await get_fund_nav_history(ts_code, days=30)
            if hist and len(hist) >= 2:
                latest = hist[-1]
                if len(hist) >= 6:
                    wk = hist[-6]
                    if wk.get("adj_nav", 0) > 0 and latest.get("adj_nav", 0) > 0:
                        week_ret = round((latest["adj_nav"] / wk["adj_nav"] - 1) * 100, 2)
                if len(hist) >= 21:
                    mo = hist[-21]
                    if mo.get("adj_nav", 0) > 0 and latest.get("adj_nav", 0) > 0:
                        month_ret = round((latest["adj_nav"] / mo["adj_nav"] - 1) * 100, 2)
        except Exception:
            pass
        return {"nav": nav, "daily": daily_ret, "week": week_ret, "month": month_ret}

    enriched = await asyncio.gather(*[enrich(it.fund_code) for it in items], return_exceptions=True)

    data = []
    for item, en in zip(items, enriched):
        if isinstance(en, Exception):
            en = {"nav": 0.0, "daily": 0.0, "week": 0.0, "month": 0.0}
        fm = sector_map.get(item.fund_code, {})
        data.append({
            "id": item.id,
            "fund_code": item.fund_code,
            "fund_name": fm.get("mapped_name") or item.fund_name,
            "fund_short_name": fm.get("mapped_name") or item.fund_name,
            "added_at": item.added_at.isoformat() if item.added_at else "",
            "notes": item.notes,
            "alert_threshold": item.alert_threshold,
            "sort_order": item.sort_order,
            "current_nav": en["nav"],
            "daily_return": en["daily"],
            "week_return": en["week"],
            "month_return": en["month"],
            "sector_code": fm.get("sector_code") if fm else None,
            "category": fm.get("category") if fm else None,
            # 建仓评级（二期注入，默认占位）
            "build_rating": None,
            "build_reason": None,
            "build_color": None,
        })

    # ── 注入建仓评级 ──
    if settings.ENABLE_BUILD_RATING and data:
        try:
            # 先查缓存（避免37秒重算）
            cached_ratings = await cache_get(_POS_RATING_CACHE_KEY_ALL)
            if cached_ratings and "sectors" in cached_ratings:
                rating_map = {s["sector_code"]: s for s in cached_ratings["sectors"]}
            else:
                ratings = await calculate_position_ratings_for_all()
                rating_map = {r.sector_code: r for r in ratings}
            for d_item in data:
                sc = d_item.get("sector_code")
                r = rating_map.get(sc) if sc else None
                if r:
                    rating_val = r.get("rating") if isinstance(r, dict) else r.rating
                    reason_val = r.get("reason") if isinstance(r, dict) else r.reason
                    d_item["build_rating"] = rating_val
                    d_item["build_reason"] = reason_val
                    d_item["build_color"] = RATING_CONFIG.get(rating_val, {}).get("color", "#6b7280")
                else:
                    d_item["build_rating"] = "watch"
                    d_item["build_reason"] = "暂无评级数据"
                    d_item["build_color"] = "#6b7280"
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"自选建仓评级注入失败: {e}")

    result = {"code": 0, "data": data, "message": "ok"}
    # 写入缓存
    await cache_set(cache_key, result, ttl=_WATCHLIST_CACHE_TTL)
    return result


@router.post("", status_code=201)
async def add_watchlist_item(
    item: WatchlistAdd,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """添加自选"""
    # 查重：同一用户不能重复添加同一基金
    exist_stmt = select(UserWatchlist).where(
        UserWatchlist.user_id == user_id,
        UserWatchlist.fund_code == item.fund_code
    )
    exist_result = await session.execute(exist_stmt)
    if exist_result.scalar_one_or_none():
        return {"code": 409, "data": None, "message": "该基金已在自选列表中"}

    # 计算排序序号
    count_stmt = select(func.count()).where(UserWatchlist.user_id == user_id)
    count_result = await session.execute(count_stmt)
    next_order = (count_result.scalar() or 0) + 1

    new_item = UserWatchlist(
        user_id=user_id,
        fund_code=item.fund_code,
        fund_name=item.fund_name or f"基金{item.fund_code}",
        notes=item.notes,
        alert_threshold=item.alert_threshold,
        sort_order=next_order,
    )
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)

    # 失效自选列表缓存
    await cache_delete(f"v5:watchlist:{user_id}")

    return {
        "code": 0,
        "data": {
            "id": new_item.id,
            "fund_code": new_item.fund_code,
            "fund_name": new_item.fund_name,
            "added_at": new_item.added_at.isoformat() if new_item.added_at else "",
            "notes": new_item.notes,
            "alert_threshold": new_item.alert_threshold,
            "sort_order": new_item.sort_order,
        },
        "message": "添加成功",
    }


@router.delete("/{item_id}")
async def delete_watchlist_item(
    item_id: int,
    user_id: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除自选"""
    # MySQL does not support RETURNING clause — use select-then-delete
    stmt = select(UserWatchlist).where(
        UserWatchlist.id == item_id, UserWatchlist.user_id == user_id
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        return {"code": 404, "data": None, "message": f"自选 {item_id} 不存在"}

    del_stmt = delete(UserWatchlist).where(
        UserWatchlist.id == item_id, UserWatchlist.user_id == user_id
    )
    await session.execute(del_stmt)
    await session.commit()

    # 失效自选列表缓存
    await cache_delete(f"v5:watchlist:{user_id}")

    return {"code": 0, "data": None, "message": "删除成功"}
