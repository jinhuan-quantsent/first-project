"""
V5.0 定时任务调度器 (APScheduler)

每日收盘后自动运行情绪计算流水线，将快照写入 market_sentiment 表。
"""
import asyncio
import logging
from typing import Optional
from datetime import date, datetime, timedelta, time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.scheduler_snapshot import _run_signal_snapshot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.utils.data_source import DEFAULT_INDEX_CODES, data_source
from app.core.redis_client import update_data_version, invalidate_module_cache

logger = logging.getLogger(__name__)


# ============================================================
# 辅助函数
# ============================================================

async def _is_trade_day() -> bool:
    """
    判断今天是否为 A 股交易日（方案 B：数据源空值检测）
    
    在 _run_daily_snapshot 开头调用，避免假日无意义运行。
    """
    try:
        test_data = await data_source.get_all_index_data()
        if not test_data:
            return False
        # 进一步检查：第一个指数的 close 是否为 None/0
        first_key = next(iter(test_data), None)
        if first_key:
            first_val = test_data[first_key]
            if not first_val.get("close"):
                return False
        return True
    except Exception as e:
        logger.warning("[Scheduler] 交易日检测失败，按交易日处理: %s", e)
        return True  # 失败时不跳过，让 pipeline 自己处理


# ============================================================
# 任务 1：每日市场快照（已有，增强）
# ============================================================

async def _run_daily_snapshot() -> None:
    """
    每日快照任务：对全部默认指数运行 V5 pipeline 并入库。

    仅 Mon-Fri 执行（APScheduler day_of_week=mon-fri），
    非交易日通过 _is_trade_day() 提前退出，避免无意义 API 调用。
    """
    # 假日智能跳过（改动 3）
    if not await _is_trade_day():
        logger.info("[Scheduler] 今日无交易数据，跳过快照")
        return

    from app.core.database import get_async_engine
    from app.services.sentiment_service import SentimentService

    today_str = date.today().isoformat()
    logger.info("[Scheduler] 开始每日快照 — %s — %d 个指数", today_str, len(DEFAULT_INDEX_CODES))

    engine = get_async_engine()
    success = 0
    fail = 0

    for code in DEFAULT_INDEX_CODES:
        try:
            async with AsyncSession(engine) as session:
                result = await asyncio.wait_for(
                    SentimentService(session).run_pipeline(code, trade_date=today_str),
                    timeout=60.0,
                )
                if result and "error" not in result:
                    await session.commit()
                    success += 1
                    logger.info(
                        "[Scheduler] ✅ %s "
                        "score=%s signal=%s",
                        result.get("index_name", code),
                        result.get("composite_score", "?"),
                        result.get("signal_level", "?"),
                    )
                else:
                    fail += 1
                    err_msg = result.get("error", "未知错误") if isinstance(result, dict) else "返回异常"
                    logger.warning("[Scheduler] ⚠️ %s 失败: %s", code, err_msg)
        except asyncio.TimeoutError:
            fail += 1
            logger.error("[Scheduler] ❌ %s 超时 (60s)", code)
        except Exception as e:
            fail += 1
            logger.error("[Scheduler] ❌ %s 异常: %s", code, e)

    logger.info("[Scheduler] 快照完成 — 成功 %d/%d, 失败 %d", success, len(DEFAULT_INDEX_CODES), fail)
    # 改动 5a：失败时报 WARNING
    if fail > 0:
        logger.warning("[Scheduler] ⚠️ 本日快照有 %d 个指数失败，请检查数据源或日志", fail)

    # 更新数据版本号 + 失效缓存
    try:
        await update_data_version("signal_board")
        await invalidate_module_cache("signal_board")
    except Exception as e:
        logger.warning("[Scheduler] 版本号更新失败(signal_board): %s", e)


# ============================================================
# 任务 2：每日板块快照（改动 1）
# ============================================================

async def _run_sector_snapshot() -> None:
    """
    每日板块快照：对所有跟踪板块计算情绪评分并写入 sector_sentiment 表。

    在每日市场快照后 15 分钟执行（15:45），等板块数据源更新完成。
    """
    from app.core.database import get_async_engine
    from app.engine.sector_scorer import score_sectors
    from app.models.sector_sentiment import SectorSentiment

    today = date.today()
    today_str = today.isoformat()

    logger.info("[Scheduler] 开始每日板块快照 — %s", today_str)

    try:
        # 调用已有的板块评分引擎
        sector_scores = await score_sectors()

        if not sector_scores:
            logger.warning("[Scheduler] 板块数据为空，跳过快照")
            return

        engine = get_async_engine()
        async with AsyncSession(engine) as session:
            for item in sector_scores:
                # P0-2 Fix: 使用新模型字段（sector_name + calc_date）
                sector_name = item.get("sector_name", item.get("name", ""))
                if not sector_name:
                    continue

                # 查找已有记录（同板块同日期 → 更新而非插入）
                from sqlalchemy import select
                stmt = select(SectorSentiment).where(
                    SectorSentiment.sector_name == sector_name,
                    SectorSentiment.calc_date == today,
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()

                if row is None:
                    row = SectorSentiment(
                        sector_name=sector_name,
                        calc_date=today,
                        sector_level="large",
                        data_source="tushare",
                    )
                    session.add(row)

                # 映射 sector_scorer 输出到新模型字段
                row.composite_score = item.get("sentiment_score", item.get("score", 50.0))
                row.sentiment_label = item.get("sentiment_label", item.get("label", "neutral"))
                # 从 momentum 推导短期趋势
                mom_5d = item.get("momentum_5d", 0.0)
                if mom_5d > 0.5:
                    row.short_trend = "up"
                elif mom_5d < -0.5:
                    row.short_trend = "down"
                else:
                    row.short_trend = "flat"

            await session.commit()

        logger.info("[Scheduler] 板块快照完成 — %d 个板块", len(sector_scores))

        # ── 写入 Redis 缓存 v5:sector:sentiment ──
        # 修复: 之前只写 DB 表（缺 signal_level/confidence_stars），
        # 导致 PositionService._get_sector_sentiment() 读 Redis 为空，
        # 所有基金 fallback 到沪深300 → 信号全部相同
        try:
            from app.core.redis_client import cache_set
            from app.api.v5.sector_router import _format_sector_item

            sectors = [_format_sector_item(s) for s in sector_scores]
            result = {
                "code": 0,
                "data": {
                    "sectors": sectors,
                    "summary": {
                        "total": len(sectors),
                        "cached": False,
                    },
                },
                "message": "ok",
            }

            # 先失效旧缓存，再写入新数据（修复自毁bug: 原顺序先写后删导致v5:sector:sentiment被清空）
            try:
                await update_data_version("sector")
                await invalidate_module_cache("sector")
            except Exception as e:
                logger.warning("[Scheduler] 版本号更新失败(sector): %s", e)

            await cache_set("v5:sector:sentiment", result, ttl=86400)
            logger.info("[Scheduler] 板块情绪已写入 Redis 缓存 — %d 个板块", len(sectors))
        except Exception as e:
            logger.error("[Scheduler] 板块情绪写入 Redis 缓存失败: %s", e)

    except Exception as e:
        logger.error("[Scheduler] 板块快照失败: %s", e)


# ============================================================
# 任务 3：每周建议验证回填（改动 2）
# ============================================================

async def _weekly_advice_verification() -> None:
    """
    每周日验证：对比 advice_log 中的建议与实际涨跌幅，回填 actual_result 和 is_verified。

    验证 7-14 天前未验证的记录。
    """
    from app.core.database import get_async_engine
    from app.models.advice_log import AdviceLog
    from sqlalchemy import select, and_, func

    logger.info("[Scheduler] 开始每周建议验证...")

    engine = get_async_engine()
    today = date.today()

    try:
        async with AsyncSession(engine) as session:
            # 查找 7-14 天前未验证的记录
            cutoff_low = today - timedelta(days=14)
            cutoff_high = today - timedelta(days=7)

            stmt = select(AdviceLog).where(
                and_(
                    AdviceLog.is_verified == 0,
                    AdviceLog.trade_date >= cutoff_low,
                    AdviceLog.trade_date <= cutoff_high,
                    AdviceLog.index_code != "",
                )
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            if not rows:
                logger.info("[Scheduler] 建议验证完成 — 无待验证记录")
                return

            verified = 0
            for row in rows:
                try:
                    # 用 Tushare index_daily 接口获取建议发出后 N 天的涨跌幅
                    actual_pct = await _fetch_index_return(
                        row.index_code,
                        start_date=row.trade_date.strftime("%Y-%m-%d"),
                        days=7,
                    )
                    if actual_pct is not None:
                        row.actual_result = round(actual_pct, 2)
                        row.is_verified = 1

                        # 简单准确度评分：建议方向与实际方向一致 → 1.0，否则 → 0.0
                        advice_positive = row.advice_type in ("buy", "hold", "add")
                        actual_positive = actual_pct > 0
                        row.accuracy_score = 1.0 if advice_positive == actual_positive else 0.0

                        verified += 1
                except Exception as e:
                    logger.warning("[Scheduler] 验证 %s 失败: %s", row.id, e)

            await session.commit()
            logger.info("[Scheduler] 建议验证完成 — %d/%d 条已验证", verified, len(rows))

    except Exception as e:
        logger.error("[Scheduler] 建议验证异常: %s", e)


async def _fetch_index_return(index_code: str, start_date: str, days: int = 7) -> Optional[float]:
    """
    获取指数在指定起始日期后 N 天的涨跌幅（%）。

    通过 Tushare index_daily 接口获取历史收盘价，计算收益率。
    失败返回 None。
    """
    try:
        from app.utils.code_format import to_tushare
        from datetime import datetime

        ts_code = to_tushare(index_code)
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = start_dt + timedelta(days=days)

        if data_source._tushare_pro:
            df = data_source._tushare_pro.index_daily(
                ts_code=ts_code,
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
            )
            if df is not None and len(df) >= 2:
                close_start = float(df.iloc[0]["close"])
                close_end = float(df.iloc[-1]["close"])
                return (close_end - close_start) / close_start * 100

        # AKShare 降级
        import akshare as ak
        df = ak.index_zh_a_hist(
            symbol=index_code.replace(".SH", "").replace(".SZ", ""),
            period="daily",
            start_date=start_dt.strftime("%Y%m%d"),
            end_date=end_dt.strftime("%Y%m%d"),
            adjust="",
        )
        if df is not None and len(df) >= 2:
            close_start = float(df.iloc[0]["收盘"])
            close_end = float(df.iloc[-1]["收盘"])
            return (close_end - close_start) / close_start * 100

    except Exception as e:
        logger.warning("[Scheduler] _fetch_index_return 失败 (%s): %s", index_code, e)

    return None




# ============================================================
# 任务 4：每日因子更新（新增）
# ============================================================

async def _run_factor_update() -> None:
    """
    每日因子更新：对所有默认指数运行因子流水线，更新 factor_history 数据。

    在每日快照后 30 分钟执行（16:00），确保所有数据源已更新。
    """
    if not await _is_trade_day():
        logger.info("[Scheduler] 今日无交易数据，跳过因子更新")
        return

    from app.core.database import get_async_engine
    from app.services.sentiment_service import SentimentService

    today_str = date.today().isoformat()
    logger.info("[Scheduler] 开始每日因子更新 — %s — %d 个指数", today_str, len(DEFAULT_INDEX_CODES))

    engine = get_async_engine()
    success = 0
    fail = 0

    for code in DEFAULT_INDEX_CODES:
        try:
            async with AsyncSession(engine) as session:
                svc = SentimentService(session)
                result = await asyncio.wait_for(
                    svc.run_pipeline(code, trade_date=today_str),
                    timeout=60.0,
                )
                if result and "error" not in result:
                    await session.commit()
                    success += 1
                    logger.info("[Scheduler] ✅ %s 因子更新成功", code)
                else:
                    fail += 1
                    err = result.get("error", "未知错误") if result else "无返回"
                    logger.warning("[Scheduler] ⚠️ %s 因子更新失败: %s", code, err)
        except asyncio.TimeoutError:
            fail += 1
            logger.error("[Scheduler] ❌ %s 因子更新超时 (60s)", code)
        except Exception as e:
            fail += 1
            logger.error("[Scheduler] ❌ %s 因子更新异常: %s", code, e)

    logger.info("[Scheduler] 因子更新完成 — 成功 %d/%d, 失败 %d", success, len(DEFAULT_INDEX_CODES), fail)
    if fail > 0:
        logger.warning("[Scheduler] ⚠️ 本日因子更新有 %d 个指数失败", fail)



# ============================================================
# 任务 8：数据就绪检查（验证用，确认数据何时全部更新完成）
# ============================================================

async def _run_data_readiness_check() -> None:
    """
    数据就绪检查：查询关键表的最新日期，判断今日数据是否已全部更新。

    在 16:30、17:00、17:30、18:00 各执行一次，记录日志供确认。
    确认后可调整缓存刷新任务的执行时间到数据就绪之后。
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.core.database import get_async_engine
    from datetime import datetime

    now_str = datetime.now().strftime("%H:%M:%S")
    today = date.today()
    today_str = today.isoformat()

    logger.info("[Scheduler] 📊 数据就绪检查 — %s %s", today_str, now_str)

    checks = {
        "market_sentiment": "SELECT MAX(trade_date) as latest FROM market_sentiment",
        "sector_sentiment": "SELECT MAX(calc_date) as latest FROM sector_sentiment",
        "factor_history": "SELECT MAX(trade_date) as latest FROM factor_history",
        "fund_nav": "SELECT MAX(nav_date) as latest FROM fund_nav",
        "daily_signal_snapshot": "SELECT MAX(snapshot_date) as latest FROM daily_signal_snapshot",
    }

    engine = get_async_engine()
    all_ready = True

    async with AsyncSessionType(engine) as session:
        for table_name, sql in checks.items():
            try:
                result = await session.execute(text(sql))
                row = result.first()
                latest = str(row[0]) if row and row[0] else "无数据"
                # 比较：latest 可能是 "2026-06-25" 或 "20260625" 格式
                is_today = latest == today_str or latest == today.strftime("%Y%m%d")
                status = "✅ 今日数据" if is_today else f"⏳ 最新={latest}"
                if not is_today:
                    all_ready = False
                logger.info("[Scheduler]   %s: %s", table_name, status)
            except Exception as e:
                logger.warning("[Scheduler]   %s: 查询失败 %s", table_name, e)
                all_ready = False

    if all_ready:
        logger.info("[Scheduler] 🎉 数据全部就绪！可安全刷新缓存")
    else:
        logger.info("[Scheduler] ⏳ 数据尚未全部就绪，等待后续任务完成")


# ============================================================
# 任务 9：建仓评级缓存刷新（17:30 预热）
# ============================================================

async def _run_cache_refresh() -> None:
    """
    建仓评级缓存刷新：在每日数据更新完成后，主动计算并写入 Redis 缓存。

    确保用户访问时永远命中缓存，无需等待计算。
    执行时间：17:30（待数据就绪检查确认后可调整）
    """
    from app.engine.position_rating import calculate_position_ratings_for_all
    from app.core.redis_client import cache_set
    from app.api.v5.sector_router import (
        _format_position_rating_item,
        _POS_RATING_CACHE_KEY_ALL,
        _POS_RATING_CACHE_TTL,
    )

    logger.info("[Scheduler] 开始建仓评级缓存刷新...")

    try:
        results = await calculate_position_ratings_for_all()

        if not results:
            logger.warning("[Scheduler] 建仓评级计算无结果，跳过缓存刷新")
            return

        sectors = [_format_position_rating_item(r) for r in results]

        rating_counts = {"strong": 0, "cautious": 0, "watch": 0, "forbidden": 0}
        for s in sectors:
            rating_counts[s["rating"]] = rating_counts.get(s["rating"], 0) + 1

        summary = {
            "total": len(sectors),
            "rating_distribution": rating_counts,
        }

        # 写入全板块缓存
        await cache_set(
            _POS_RATING_CACHE_KEY_ALL,
            {"sectors": sectors, "summary": summary},
            ttl=_POS_RATING_CACHE_TTL,
        )

        # 同时写入单板块缓存
        for item in sectors:
            sector_code = item.get("sector_code")
            if sector_code:
                await cache_set(
                    f"v5:pos_rating:{sector_code}",
                    item,
                    ttl=_POS_RATING_CACHE_TTL,
                )

        logger.info(
            "[Scheduler] ✅ 建仓评级缓存刷新完成 — %d 个板块, 分布: %s",
            len(sectors),
            rating_counts,
        )

        # === 预热其他慢接口缓存 ===
        await _prewarm_market_caches()

        # 更新数据版本号 + 失效缓存（holdings, sector, watchlist, signal_board）
        for _mod in ("holdings", "sector", "watchlist", "signal_board"):
            try:
                await update_data_version(_mod)
                await invalidate_module_cache(_mod)
            except Exception as e:
                logger.warning("[Scheduler] 版本号更新失败(%s): %s", _mod, e)

    except Exception as e:
        logger.error("[Scheduler] ❌ 建仓评级缓存刷新失败: %s", e)
        import traceback
        traceback.print_exc()


async def _prewarm_market_caches() -> None:
    """
    预热 market 相关慢接口缓存：
    - 4 指数 sentiment（run_pipeline）
    - sectors（行业+概念）
    - recommendations
    """
    from app.core.database import get_session_factory
    from app.core.redis_client import cache_set
    from app.services.sentiment_service import SentimentService
    from app.services.factor_data_service import FactorDataService
    import time

    logger.info("[Scheduler] 开始预热 market 缓存...")

    session_factory = get_session_factory()

    # 1. 预热 4 指数 sentiment
    index_codes = ["SH000001", "SH000300", "SZ399001", "SZ399006"]
    async with session_factory() as session:
        service = SentimentService(db_session=session)
        for code in index_codes:
            try:
                start = time.time()
                result = await service.run_pipeline(code)
                elapsed = round(time.time() - start, 2)
                if "error" not in result:
                    logger.info("[Scheduler]   ✅ sentiment %s (%.1fs)", code, elapsed)
                else:
                    logger.warning("[Scheduler]   ⚠️ sentiment %s: %s", code, result.get("error"))
            except Exception as e:
                logger.error("[Scheduler]   ❌ sentiment %s 失败: %s", code, e)

    # 2. 预热 sectors（行业+概念）
    async with session_factory() as session:
        sentiment_service = SentimentService(db_session=session)
        fd_service = FactorDataService(sentiment_service=sentiment_service)
        for sector_type in ["industry", "concept"]:
            try:
                start = time.time()
                result = await fd_service.get_sectors(
                    sector_type=sector_type, page=1, page_size=50,
                    sort_by="change_pct", sort_order="desc",
                )
                elapsed = round(time.time() - start, 2)
                if isinstance(result, dict) and result.get("code") == 0:
                    cache_key = f"v5:sectors:{sector_type}:1:50:change_pct:desc"
                    result["data"]["elapsed_seconds"] = elapsed
                    result["data"]["cached"] = False
                    await cache_set(cache_key, result, ttl=86400)
                    logger.info("[Scheduler]   ✅ sectors %s (%.1fs)", sector_type, elapsed)
            except Exception as e:
                logger.error("[Scheduler]   ❌ sectors %s 失败: %s", sector_type, e)

    # 3. 预热 recommendations
    try:
        from app.api.market import _get_real_sectors, generate_recommendations, generate_warnings
        from app.engine.recommendations import RecommendationResult
        start = time.time()
        sectors = await _get_real_sectors()
        result = generate_recommendations(sectors, top_n=5)
        warnings = generate_warnings(sectors, max_warnings=5)

        def _item_to_dict(item) -> dict:
            return {
                "sector_code": item.sector_code,
                "sector_name": item.sector_name,
                "sector_group": item.sector_group,
                "sentiment_score": item.sentiment_score,
                "sentiment_label": item.sentiment_label,
                "signal_level": item.signal_level,
                "momentum_5d": item.momentum_5d,
                "momentum_20d": item.momentum_20d,
                "strength_index": item.strength_index,
                "strength_rank": item.strength_rank,
                "opportunity_type": item.opportunity_type,
                "opportunity_reason": item.opportunity_reason,
                "reason": item.reason,
                "recommended_funds": item.recommended_funds,
            }

        response = {
            "code": 0,
            "data": {
                "strong_sectors": [_item_to_dict(i) for i in result.strong_sectors],
                "rebound_opportunities": [_item_to_dict(i) for i in result.rebound_opportunities],
                "steady_choices": [_item_to_dict(i) for i in result.steady_choices],
                "top_picks": [_item_to_dict(i) for i in result.top_picks],
                "summary": result.summary,
                "elapsed_seconds": round(time.time() - start, 2),
                "cached": False,
                "warnings": [
                    {
                        "sector_name": w.sector_name,
                        "sector_code": w.sector_code,
                        "sentiment_score": w.sentiment_score,
                        "momentum_5d": w.momentum_5d,
                        "warning_type": w.warning_type,
                        "signal_level": w.signal_level,
                        "reason": w.reason,
                    }
                    for w in warnings
                ],
            },
            "message": "ok",
        }
        await cache_set("v5:recommendations:all", response, ttl=86400)
        logger.info("[Scheduler]   ✅ recommendations (%.1fs)", response["data"]["elapsed_seconds"])
    except Exception as e:
        logger.error("[Scheduler]   ❌ recommendations 失败: %s", e)

    # 4. 预热 sector/sentiment (31板块评分, 最重的接口 ~30-43s)
    try:
        from app.engine.sector_scorer import score_sectors
        start = time.time()
        sector_data = await score_sectors()
        if sector_data:
            # 简化格式写入缓存（与API返回格式一致需要format，这里直接调用API逻辑）
            from app.api.v5.sector_router import _SECTOR_SENTIMENT_CACHE_KEY, _SECTOR_SENTIMENT_CACHE_TTL
            import importlib
            sector_router = importlib.import_module("app.api.v5.sector_router")
            # 直接用HTTP请求本地API来触发缓存写入（最可靠）
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:8765/api/v5/sector/sentiment", timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status == 200:
                        logger.info("[Scheduler]   ✅ sector/sentiment (%.1fs)", time.time() - start)
                    else:
                        logger.warning("[Scheduler]   ⚠️ sector/sentiment HTTP %d", resp.status)
    except Exception as e:
        logger.error("[Scheduler]   ❌ sector/sentiment 预热失败: %s", e)

    # 5. 预热 sector/radar (机会雷达, 同样依赖score_sectors但已有sentiment缓存会快一些)
    try:
        start = time.time()
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8765/api/v5/sector/radar", timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    logger.info("[Scheduler]   ✅ sector/radar (%.1fs)", time.time() - start)
                else:
                    logger.warning("[Scheduler]   ⚠️ sector/radar HTTP %d", resp.status)
    except Exception as e:
        logger.error("[Scheduler]   ❌ sector/radar 预热失败: %s", e)

    # 6. 预热 sector/detail（23板块成分股详情）
    try:
        import aiohttp
        # 申万代码需要 .SI 后缀才能被 eastmoney 正确识别
        sector_codes = [
            "801080.SI", "801710.SI", "801770.SI", "801790.SI", "801890.SI", "801120.SI",
            "801110.SI", "801760.SI", "801730.SI", "801720.SI", "801030.SI", "801150.SI",
            "801740.SI", "801750.SI", "801010.SI", "801780.SI", "801180.SI", "801040.SI",
            "801880.SI", "801950.SI", "801160.SI", "801050.SI", "801960.SI",
        ]
        start = time.time()
        warmed = 0
        async with aiohttp.ClientSession() as http_session:
            for sc in sector_codes:
                try:
                    async with http_session.get(
                        f"http://localhost:8765/api/v5/market/sector/{sc}",
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 200:
                            warmed += 1
                except Exception:
                    pass
        logger.info("[Scheduler]   ✅ sector/detail %d/23 (%.1fs)", warmed, time.time() - start)
    except Exception as e:
        logger.error("[Scheduler]   ❌ sector/detail 预热失败: %s", e)

    logger.info("[Scheduler] ✅ market 缓存预热完成")


# ============================================================
# 盘中预演辅助函数群
# ============================================================

def _calculate_elasticity(fund_code: str, gszzl: float, meta: dict) -> float:
    """弹性系数计算（板块波动率自适应）
    
    规则：
    - |gszzl|>5%: 强制1.0（极端行情降敏）
    - 高波动板块(通信/军工/电子): 1.5-2.0
    - 低波动板块(银行/食品/公用): 2.5-3.0
    - 中波动板块: 2.0-2.5
    """
    # 极值保护
    if abs(gszzl) > 5.0:
        return settings.INTRADAY_PREVIEW_ELASTIC_EXTREME_CLAMP
    
    sector_code = meta.get("sector_code") or ""
    volatility_grade = _get_volatility_grade(sector_code)
    
    # 尝试从Redis读取周更弹性系数
    from app.core.redis_client import cache_get
    import asyncio
    try:
        elastic_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:elastic:{fund_code}"
        # 同步函数中无法直接await，用线程安全方式
        # 如果是scheduler async环境中调用，弹性系数已在meta中缓存
        weekly_elastic = meta.get("weekly_elasticity")
        if weekly_elastic is not None:
            return float(weekly_elastic)
    except Exception:
        pass
    
    if volatility_grade == "high":
        base = settings.INTRADAY_PREVIEW_ELASTIC_LOW
    elif volatility_grade == "low":
        base = settings.INTRADAY_PREVIEW_ELASTIC_HIGH
    else:
        base = settings.INTRADAY_PREVIEW_ELASTIC_BASE
    
    return base


def _get_volatility_grade(sector_code: str | None) -> str:
    """板块波动率分级（申万一级）"""
    HIGH_VOL = {"801770", "801740", "801080", "801750", "801760"}  # 电力设备/计算机/电子/传媒/军工
    LOW_VOL = {"801180", "801120", "801160", "801170"}  # 银行/食品饮料/公用事业/交通运输
    BROAD = {"000300", "000905", "000016"}  # 宽基指数
    
    code = sector_code or ""
    if code in HIGH_VOL:
        return "high"
    elif code in LOW_VOL or code in BROAD:
        return "low"
    else:
        return "mid"


def _score_to_signal(score: float, boundaries: list) -> str:
    """情绪分 -> 信号等级（复用V5边界）"""
    if score < boundaries[0]: return "S+"
    if score < boundaries[1]: return "S"
    if score < boundaries[2]: return "A"
    if score < boundaries[3]: return "B"
    if score < boundaries[4]: return "C"
    if score < boundaries[5]: return "D"
    return "E"


def _get_confidence_note(confidence: int) -> str:
    """置信度时段文案"""
    if confidence <= 1: return "早盘波动大，仅供参考"
    if confidence == 2: return "趋势基本明朗"
    return "接近收盘，仍需等待确认"


def _prefix_preview_reason(reason: str) -> str:
    """给reason加预演前缀"""
    if reason.startswith("若收盘") or reason.startswith("预演"):
        return reason
    return f"若收盘维持当前行情，{reason}"


def _calc_signal_change(yesterday_signal: str | None, preview_signal: str) -> str:
    """计算信号变化方向"""
    if yesterday_signal is None:
        return "unknown"
    signal_order = ["S+", "S", "A", "B", "C", "D", "E"]
    try:
        y_idx = signal_order.index(yesterday_signal)
        p_idx = signal_order.index(preview_signal)
        if p_idx < y_idx:
            return "up"  # 信号升级（偏贪婪）
        elif p_idx > y_idx:
            return "down"  # 信号降级（偏恐惧）
        else:
            return "stable"
    except ValueError:
        return "unknown"


def _gate_price_to_position(trigger_price: float | None, ma20_price: float | None) -> float | None:
    """闸门触发价位 -> 进度条百分比位置"""
    if trigger_price is None or ma20_price is None or ma20_price == 0:
        return None
    return round((trigger_price - ma20_price) / ma20_price * 100, 2)


def _format_gate_distance(distance_pct: float | None) -> str | None:
    """格式化闸门距离为可读文案"""
    if distance_pct is None:
        return None
    if distance_pct > 0:
        return f"距触发还需涨{distance_pct:.1f}%"
    elif distance_pct < 0:
        return f"已突破，超出{abs(distance_pct):.1f}%"
    else:
        return "恰在触发线上"


def _build_anomaly_notes(
    gszzl: float | None,
    gszzl_source: str,
    elasticity: float | None,
    score_delta: float | None,
    preview_signal: str,
    yesterday_signal: str | None,
    meta_date_used: str | None,
    today_str: str,
    has_snapshot: bool,
    preview_result: dict,
) -> list[dict]:
    """构建异常场景提示列表

    检测项：
    1. 极端行情（|gszzl|>5%）：弹性系数强制降敏
    2. 情绪分钳位（score_delta 被截断）：信号变动受限制
    3. 元数据过期（meta_date != today）：预演基准可能偏移
    4. 无昨日快照（新基金 / 首次预演）：使用缓存基准
    5. 估值数据不可用：使用昨日信号预演
    6. 信号变化方向：升级 / 降级提示
    7. Gate 触发：风控提示
    """
    notes: list[dict] = []

    # 1. 极端行情
    if gszzl is not None and abs(gszzl) > 5.0:
        direction = "大涨" if gszzl > 0 else "大跌"
        notes.append({
            "type": "extreme_volatility",
            "level": "danger",
            "message": f"盘中{direction}{abs(gszzl):.1f}%触发极端行情降敏，弹性系数已强制降至1.0",
        })

    # 2. 情绪分钳位
    if gszzl is not None and elasticity is not None:
        raw_delta = abs(gszzl * elasticity)
        clamp = settings.INTRADAY_PREVIEW_SCORE_DELTA_CLAMP
        if raw_delta > clamp:
            notes.append({
                "type": "score_clamped",
                "level": "info",
                "message": f"情绪分变动被限制在±{clamp:.0f}分以内，避免信号过度跳变",
            })

    # 3. 元数据过期
    if meta_date_used and meta_date_used != today_str:
        try:
            meta_date = date.fromisoformat(meta_date_used)
            today = date.fromisoformat(today_str)
            days_diff = (today - meta_date).days
            notes.append({
                "type": "stale_meta",
                "level": "info" if days_diff <= 2 else "warning",
                "message": f"使用{days_diff}天前({meta_date_used})的元数据预演，基准可能存在偏差",
            })
        except (ValueError, TypeError):
            pass

    # 4. 无昨日快照
    if not has_snapshot:
        notes.append({
            "type": "new_fund",
            "level": "info",
            "message": "无昨日决策快照，使用板块/指数缓存作为预演基准",
        })

    # 5. 估值数据不可用
    if gszzl_source == "unavailable":
        notes.append({
            "type": "no_estimation",
            "level": "warning",
            "message": "盘中估值数据获取失败，当前显示为昨日信号预演，不代表实时行情",
        })

    # 6. 信号变化
    if yesterday_signal and preview_signal != yesterday_signal:
        change = _calc_signal_change(yesterday_signal, preview_signal)
        if change == "up":
            notes.append({
                "type": "signal_upgrade",
                "level": "info",
                "message": f"信号从{yesterday_signal}升级至{preview_signal}，情绪偏向贪婪",
            })
        elif change == "down":
            notes.append({
                "type": "signal_downgrade",
                "level": "warning",
                "message": f"信号从{yesterday_signal}降级至{preview_signal}，情绪偏向恐惧",
            })

    # 7. Gate 触发
    gates = preview_result.get("gates") or {}
    gate_1 = gates.get("gate_1") or {}
    gate_2 = gates.get("gate_2") or {}
    if gate_1.get("triggered"):
        notes.append({
            "type": "gate_triggered",
            "level": "danger",
            "message": "Gate-1已触发（MA20破位），建议关注减仓信号",
        })
    if gate_2.get("triggered"):
        notes.append({
            "type": "gate_triggered",
            "level": "danger",
            "message": "Gate-2已触发（回撤超限），建议执行减仓",
        })

    return notes


def _build_preview_summary(
    preview_confidence: int,
    gszzl: float | None,
    gszzl_source: str,
    preview_score: float,
    yesterday_score: float,
    score_delta: float | None,
    preview_signal: str,
    yesterday_signal: str | None,
    effective_stars: int,
    yesterday_confidence: int,
    preview_result: dict,
    anomaly_notes: list[dict],
) -> str:
    """构建文字版综合解读（一段话）

    结构：时段 → 估值 → 情绪分变化 → 信号 → 置信度 → Gate状态 → 操作建议 → 异常提示
    """
    period_map = {1: "早盘", 2: "午盘", 3: "尾盘"}
    period = period_map.get(preview_confidence, "盘中")

    parts: list[str] = []

    # 1. 时段 + 估值
    if gszzl is not None and gszzl_source != "unavailable":
        direction = "涨" if gszzl >= 0 else "跌"
        parts.append(f"{period}时段，盘中{direction}{abs(gszzl):.2f}%")
    else:
        parts.append(f"{period}时段，估值数据暂不可用")

    # 2. 情绪分变化
    if score_delta is not None:
        delta_str = f"{'+' if score_delta >= 0 else ''}{score_delta:.1f}"
        parts.append(f"估算情绪分{preview_score:.1f}（昨收{yesterday_score:.1f}，变动{delta_str}）")
    else:
        parts.append(f"估算情绪分{preview_score:.1f}（昨收{yesterday_score:.1f}）")

    # 3. 信号
    if yesterday_signal and preview_signal != yesterday_signal:
        parts.append(f"信号{yesterday_signal}→{preview_signal}")
    else:
        parts.append(f"信号维持{preview_signal}级")

    # 4. 置信度
    star_discount = yesterday_confidence - effective_stars
    if star_discount > 0:
        parts.append(f"置信度{effective_stars}星（时段折减-{star_discount}星）")
    else:
        parts.append(f"置信度{effective_stars}星")

    # 5. Gate 状态
    gates = preview_result.get("gates") or {}
    gate_msgs: list[str] = []
    gate_1 = gates.get("gate_1") or {}
    gate_2 = gates.get("gate_2") or {}
    if gate_1.get("triggered"):
        gate_msgs.append("Gate-1已触发")
    elif gate_1.get("current_distance_pct") is not None:
        dist = gate_1["current_distance_pct"]
        if dist > 0:
            gate_msgs.append(f"Gate-1距触发还需涨{dist:.1f}%")
    if gate_2.get("triggered"):
        gate_msgs.append("Gate-2已触发")
    elif gate_2.get("current_distance_pct") is not None:
        dist = gate_2["current_distance_pct"]
        if dist > 0:
            gate_msgs.append(f"Gate-2距触发还需涨{dist:.1f}%")
    if gate_msgs:
        parts.append("、".join(gate_msgs))

    # 6. 操作建议
    action = preview_result.get("action", "hold")
    action_map = {"increase": "建议加仓", "decrease": "建议减仓", "hold": "建议持有"}
    parts.append(action_map.get(action, "建议持有"))

    summary = "，".join(parts) + "。"

    # 7. 追加异常提示
    danger_notes = [n for n in anomaly_notes if n["level"] == "danger"]
    warning_notes = [n for n in anomaly_notes if n["level"] == "warning"]
    if danger_notes:
        summary += " ⚠" + "；".join(n["message"] for n in danger_notes) + "。"
    elif warning_notes:
        summary += " 注意：" + "；".join(n["message"] for n in warning_notes) + "。"

    return summary


def _build_system_advice_text(
    preview_output: dict,
    market_index_chg_pct: float | None,
    sector_chg_pct: float | None,
    cost_basis: float | None,
    unrealized_pnl_pct: float | None,
    holding_days: int | None,
    historical_accuracy: dict | None,
) -> str:
    """构建系统建议文本 -- 7段结构化文字(300-500字符)

    14:50任务A调用，生成后写入 strategy_validation_log.system_advice_text。
    结构: 【估值】【情绪】【大盘】【持仓】【风控】【历史】【结论】
    """
    parts: list[str] = []

    # 1. 【估值】
    gszzl = preview_output.get("gszzl")
    gszzl_source = preview_output.get("gszzl_source", "unavailable")
    if gszzl is not None:
        direction = "涨" if gszzl >= 0 else "跌"
        parts.append(f"【估值】盘中估值{direction}{abs(gszzl):.2f}%，数据来源{gszzl_source}实时接口。")
    else:
        parts.append("【估值】盘中估值数据暂不可用。")

    # 2. 【情绪】
    preview_score = preview_output.get("preview_score", 0)
    yesterday_score = preview_output.get("yesterday_score", 0)
    score_delta = preview_output.get("score_delta")
    preview_signal = preview_output.get("signal_level", "B")
    yesterday_signal = preview_output.get("yesterday_signal", "B")
    effective_stars = preview_output.get("confidence_stars", 3)
    delta_str = f"{'+' if score_delta and score_delta >= 0 else ''}{score_delta:.1f}" if score_delta is not None else "N/A"
    signal_change = f"信号{yesterday_signal}->{preview_signal}" if yesterday_signal and preview_signal != yesterday_signal else f"信号维持{preview_signal}"
    parts.append(f"【情绪】预演情绪分{preview_score:.1f}(昨{yesterday_score:.1f})，{signal_change}，置信度{effective_stars}星。")

    # 3. 【大盘】
    market_str_parts = []
    if market_index_chg_pct is not None:
        mkt_dir = "涨" if market_index_chg_pct >= 0 else "跌"
        market_str_parts.append(f"大盘{mkt_dir}{abs(market_index_chg_pct):.2f}%")
    if sector_chg_pct is not None:
        sec_dir = "涨" if sector_chg_pct >= 0 else "跌"
        market_str_parts.append(f"板块{sec_dir}{abs(sector_chg_pct):.2f}%")
    if market_str_parts:
        parts.append(f"【大盘】{'，'.join(market_str_parts)}。")
    else:
        parts.append("【大盘】市场数据暂不可用。")

    # 4. 【持仓】
    current_pct = preview_output.get("current_position_pct", 0)
    target_pct = preview_output.get("target_position_pct", 0)
    pnl_str = f"浮盈{unrealized_pnl_pct:+.1f}%" if unrealized_pnl_pct is not None else "浮盈亏数据暂无"
    days_str = f"持有{holding_days}天" if holding_days is not None else ""
    parts.append(f"【持仓】当前仓位{current_pct*100:.0f}%，目标{target_pct*100:.0f}%，{pnl_str}{('，' + days_str) if days_str else ''}。")

    # 5. 【风控】
    gates = preview_output.get("gates") or {}
    gate_1 = gates.get("gate_1") or {}
    gate_2 = gates.get("gate_2") or {}
    gate_msgs = []
    if gate_1.get("triggered"):
        gate_msgs.append("Gate-1已触发")
    elif gate_1.get("current_distance_pct") is not None:
        dist = gate_1["current_distance_pct"]
        gate_msgs.append(f"Gate-1距触发{dist:+.1f}%")
    if gate_2.get("triggered"):
        gate_msgs.append("Gate-2已触发")
    elif gate_2.get("current_distance_pct") is not None:
        dist = gate_2["current_distance_pct"]
        gate_msgs.append(f"Gate-2距触发{dist:+.1f}%")
    freq_block = preview_output.get("frequency_block_direction")
    freq_msg = f"，频率限制({freq_block})" if freq_block else "，无频率限制"
    parts.append(f"【风控】{'，'.join(gate_msgs) if gate_msgs else 'Gate正常'}{freq_msg}。")

    # 6. 【历史】— 多窗口准确率(30/60/90天)
    def _fmt_pct(v):
        return f"{v*100:.0f}%" if v is not None else "--"

    mw = historical_accuracy.get("multi_window", {}) if historical_accuracy else {}
    if mw and any(mw.get(w, {}).get(k) is not None for w in ("30d", "60d", "90d") for k in ("signal", "advice", "gate")):
        sig_parts = []
        adv_parts = []
        gate_parts = []
        for w in ("30d", "60d", "90d"):
            wd = mw.get(w, {})
            sig_parts.append(f"{w}={_fmt_pct(wd.get('signal'))}")
            adv_parts.append(f"{w}={_fmt_pct(wd.get('advice'))}")
            gate_parts.append(f"{w}={_fmt_pct(wd.get('gate'))}")
        parts.append(f"【历史】准确率趋势(以近30天为主): 信号[{', '.join(sig_parts)}] 建议[{', '.join(adv_parts)}] Gate[{', '.join(gate_parts)}]。")
    else:
        parts.append("【历史】暂无历史回验数据。")

    # 7. 【结论】— 结论方向严格与实际 action 一致
    # 修复: 原 stop_loss/warning 分支用固定文案覆盖方向，可能与 engine 的 action 矛盾
    #       (如 1星基金 target=0%/action=hold，却曾因信号等级显示"加仓")。
    #       现统一以 action 决定方向词，风控状态仅作为补充提示，杜绝方向不一致。
    # 修复②: 当前仓位为空仓(≈0%)时，不再输出"加仓/减仓/止损"等无效操作建议
    #       (如 012538 空仓却因 gate_2 止损触发显示"建议减仓"，对用户无意义)。
    overall_status = preview_output.get("overall_status", "normal")
    action = preview_output.get("action", "hold")
    current_position_pct = preview_output.get("current_position_pct", 0) or 0
    direction_map = {"increase": "建议加仓", "decrease": "建议减仓", "hold": "建议持有"}
    conclusion = direction_map.get(action, "建议持有")
    if current_position_pct < 0.001:
        conclusion = "建议持有，当前空仓无需操作"
    elif overall_status == "stop_loss":
        conclusion += "，尾盘10分钟内完成止损操作"
    elif overall_status == "warning":
        conclusion += "，维持仓位观望，关注尾盘资金流向"
    parts.append(f"【结论】{conclusion}。")

    return "\n".join(parts)


def _build_threshold_data(preview_result: dict, meta: dict, gszzl: float | None, preview_score: float = 0) -> dict:
    """构建前端ThresholdBar需要的阈值数据"""
    gates = preview_result.get("gates") or {}
    gate_zones = []
    
    # Gate-P（全市场恐慌）
    gate_p = gates.get("gate_p") or {}
    gate_zones.append({
        "id": "gate-p",
        "label": gate_p.get("label", "全市场恐慌"),
        "triggered": gate_p.get("triggered", False),
        "position": None,
    })
    
    # Gate-1（极端回撤）
    gate_1 = gates.get("gate_1") or {}
    gate_zones.append({
        "id": "gate-1",
        "label": gate_1.get("label", "极端回撤"),
        "triggered": gate_1.get("triggered", False),
        "trigger_price": gate_1.get("trigger_price"),
        "current_distance_pct": gate_1.get("current_distance_pct"),
        "status_text": _format_gate_distance(gate_1.get("current_distance_pct")),
        "drawdown": gate_1.get("drawdown"),
        "position": _gate_price_to_position(gate_1.get("trigger_price"), meta.get("ma20_price")),
    })
    
    # Gate-2（趋势破位）
    gate_2 = gates.get("gate_2") or {}
    gate_zones.append({
        "id": "gate-2",
        "label": gate_2.get("label", "趋势破位"),
        "triggered": gate_2.get("triggered", False),
        "trigger_price": gate_2.get("trigger_price"),
        "current_distance_pct": gate_2.get("current_distance_pct"),
        "status_text": _format_gate_distance(gate_2.get("current_distance_pct")),
        "exempted": gate_2.get("exempted", False),
        "position": _gate_price_to_position(gate_2.get("trigger_price"), meta.get("ma20_price")),
    })
    
    # Gate-E（情绪过热）
    gate_e = gates.get("gate_e") or {}
    gate_zones.append({
        "id": "gate-e",
        "label": gate_e.get("label", "情绪过热"),
        "triggered": gate_e.get("triggered", False),
        "position": None,
    })
    
    # 安全区间评估
    distances = []
    for d in [gate_1.get("current_distance_pct"), gate_2.get("current_distance_pct")]:
        if d is not None:
            distances.append(abs(d))
    min_distance = min(distances) if distances else 999
    
    if min_distance > 5:
        safe_zone_note = "距所有闸门阈值>5%，处于安全区间"
    elif min_distance > 2:
        safe_zone_note = "距闸门阈值2-5%，进入预警区间"
    else:
        safe_zone_note = "距闸门阈值<2%，进入临界区间"
    
    # 向上/向下触发阈值
    boundaries = meta.get("signal_boundaries") or list(settings.V5_SIGNAL_BOUNDARIES)
    yesterday_score = meta.get("yesterday_score") or 50.0
    signal_names = ["S+", "S", "A", "B", "C", "D", "E"]

    # 当前信号位置（基于预演分数）
    current_signal = _score_to_signal(preview_score, boundaries)
    current_signal_idx = 0
    try:
        current_signal_idx = signal_names.index(current_signal)
    except ValueError:
        current_signal_idx = 3  # default to B

    # 下一级信号阈值（分数更高 = 更恐惧方向）
    next_signal = signal_names[min(current_signal_idx + 1, 6)] if current_signal_idx < 6 else None
    up_trigger_pct = None
    for i, b in enumerate(boundaries):
        if b > preview_score:
            if preview_score > 0:
                up_trigger_pct = round((b - preview_score) / preview_score * 100, 1)
            break

    # 上一级信号阈值（分数更低 = 更贪婪方向）
    prev_signal = signal_names[max(current_signal_idx - 1, 0)] if current_signal_idx > 0 else None
    down_trigger_pct = None
    for i in range(len(boundaries) - 1, -1, -1):
        if boundaries[i] <= preview_score:
            if boundaries[i] > 0:
                down_trigger_pct = round((preview_score - boundaries[i]) / boundaries[i] * 100, 1)
            break

    # Gate-2 距离（保留原逻辑）
    gate2_distance_pct = None
    if gate_2.get("current_distance_pct") is not None:
        gate2_distance_pct = round(abs(gate_2["current_distance_pct"]), 2)
    
    return {
        "gate_zones": gate_zones,
        "safe_zone_note": safe_zone_note,
        "current_score": yesterday_score,
        "current_signal": current_signal,
        "next_signal": next_signal,
        "prev_signal": prev_signal,
        "up_trigger_pct": up_trigger_pct,
        "down_trigger_pct": down_trigger_pct,
        "gate2_distance_pct": gate2_distance_pct,
    }


# ============================================================
# 任务 16：盘中预演计算（交易时段内每5分钟执行）
# ============================================================

def _compute_intraday_features(series: list) -> dict:
    """计算盘中形态特征 (V5.4增强)

    输入: series = [{ts: "HH:MM", gszzl: float, preview_score: float, ...}, ...]
    输出: {shape, am_range, pm_slope, turn_points, last30_dir, gszzl_first, gszzl_last}
    """
    if not series or len(series) < 5:
        return {
            "shape": "insufficient_data",
            "am_range": 0,
            "pm_slope": 0,
            "turn_points": 0,
            "last30_dir": 0,
            "gszzl_first": None,
            "gszzl_last": None,
        }

    gszzl_vals = [p.get("gszzl") for p in series if p.get("gszzl") is not None]
    if not gszzl_vals:
        return {
            "shape": "no_data",
            "am_range": 0,
            "pm_slope": 0,
            "turn_points": 0,
            "last30_dir": 0,
            "gszzl_first": None,
            "gszzl_last": None,
        }

    gszzl_first = gszzl_vals[0]
    gszzl_last = gszzl_vals[-1]

    # 1. 振幅范围
    am_range = round(max(gszzl_vals) - min(gszzl_vals), 2)

    # 2. 形态分类 (7类: 倒V/V/单边涨/单边跌/宽幅震荡/窄幅整理/震荡)
    mid_idx = len(gszzl_vals) // 2
    first_half_avg = sum(gszzl_vals[:mid_idx]) / mid_idx if mid_idx > 0 else gszzl_first
    second_half_avg = sum(gszzl_vals[mid_idx:]) / (len(gszzl_vals) - mid_idx) if len(gszzl_vals) > mid_idx else gszzl_last

    # 方向判断
    direction = gszzl_last - gszzl_first
    first_direction = first_half_avg - gszzl_first
    second_direction = gszzl_last - second_half_avg

    if am_range < 1.0:
        shape = "窄幅整理"
    elif abs(first_direction) > 0.5 and abs(second_direction) > 0.5 and first_direction * second_direction < 0:
        # 先涨后跌 或 先跌后涨
        if first_direction > 0 and second_direction < 0:
            shape = "倒V"
        else:
            shape = "V"
    elif am_range > 3.0 and _count_turn_points(gszzl_vals) >= 3:
        shape = "宽幅震荡"
    elif direction > 0.5:
        shape = "单边涨"
    elif direction < -0.5:
        shape = "单边跌"
    else:
        shape = "震荡"

    # 3. 午后斜率 (13:00-14:40)
    pm_slope = _slope_series(series, "13:00", "14:40")

    # 4. 转折点数
    turn_points = _count_turn_points(gszzl_vals)

    # 5. 最近30分钟方向 (14:10-14:40)
    last30_dir = _slope_series(series, "14:10", "14:40")

    return {
        "shape": shape,
        "am_range": am_range,
        "pm_slope": pm_slope,
        "turn_points": turn_points,
        "last30_dir": last30_dir,
        "gszzl_first": gszzl_first,
        "gszzl_last": gszzl_last,
    }


def _slope_series(series: list, t_start: str, t_end: str) -> float:
    """计算序列中两个时间点之间的 gszzl 变化量 (斜率)"""
    val_start = None
    val_end = None
    for p in series:
        ts = p.get("ts", "")
        if ts >= t_start and val_start is None:
            val_start = p.get("gszzl")
        if ts >= t_end:
            val_end = p.get("gszzl")
            break

    if val_start is not None and val_end is not None:
        return round(val_end - val_start, 2)
    return 0


def _count_turn_points(vals: list) -> int:
    """计算转折点数 (方向变化次数)"""
    if len(vals) < 3:
        return 0
    count = 0
    for i in range(1, len(vals) - 1):
        prev_diff = vals[i] - vals[i - 1]
        next_diff = vals[i + 1] - vals[i]
        # 忽略极小波动 (阈值0.1%)
        if abs(prev_diff) < 0.1 or abs(next_diff) < 0.1:
            continue
        if prev_diff * next_diff < 0:
            count += 1
    return count


async def _run_intraday_preview_calculate() -> None:
    """
    盘中预演计算 -- 交易时段每5分钟执行
    
    对每个持仓基金：
    1. 获取基金实时估值(gszzl) via get_fund_realtime_nav()
    2. 从Redis读取元数据包(MA20/MACD/轨道/冷却期/regime)
    3. 从DailySignalSnapshot DB表读取昨日情绪分/信号/置信度
    4. 计算盘中估算情绪分（弹性系数公式）
    5. import PositionEngineV5.calculate() 产出预演结果
    6. 写入 Redis 缓存（TTL=300秒）
    
    输入替换策略：
    - signal_level: 盘中估算信号（弹性系数推算）
    - confidence_stars: 1星(早盘)/2星(午盘)/3星(尾盘)
    - regime: 元数据中的regime
    - current_position_pct: 从user_portfolio实时读取
    """
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user_portfolio import UserPortfolio
    from app.models.user_cash import UserCash
    from app.models.daily_signal_snapshot import DailySignalSnapshot
    from app.engine.position_v5 import PositionEngineV5
    from app.utils.eastmoney import get_fund_realtime_nav
    from app.core.redis_client import cache_get, cache_set

    # 1. 检查全局开关
    redis_switch = await cache_get("intraday_preview:global_switch")
    if redis_switch == "off" or not settings.ENABLE_INTRADAY_PREVIEW:
        logger.info("[Scheduler] 盘中预演关闭，跳过计算")
        return

    # 2. 检查交易时段（9:30-15:00）
    now = datetime.now()
    if now.time() < time(9, 30) or now.time() > time(15, 0):
        logger.info("[Scheduler] 非交易时段，跳过盘中预演计算")
        return

    today_str = date.today().isoformat()
    engine = get_async_engine()

    # 3. 置信度时段映射
    if now.time() < time(11, 30):
        preview_confidence = 1  # 早盘
    elif now.time() < time(14, 30):
        preview_confidence = 2  # 午盘
    else:
        preview_confidence = 3  # 尾盘

    # 4. 获取所有持仓（含用户ID+仓位百分比）
    async with AsyncSession(engine) as session:
        stmt = select(
            UserPortfolio.user_id,
            UserPortfolio.fund_code,
            UserPortfolio.market_value,
        )
        result = await session.execute(stmt)
        rows = result.all()

    # 按用户分组
    user_funds = {}
    for user_id, fund_code, market_value in rows:
        if user_id not in user_funds:
            user_funds[user_id] = {"funds": [], "total_mv": 0.0}
        user_funds[user_id]["funds"].append(fund_code)
        user_funds[user_id]["total_mv"] += float(market_value or 0)

    # 4b. 查询各用户现金余额，加入总资产（与14:40 DeepSeek统一口径）
    async with AsyncSession(engine) as session:
        cash_stmt = select(UserCash.user_id, UserCash.cash_amount)
        cash_result = await session.execute(cash_stmt)
        for uid, cash in cash_result:
            if uid in user_funds:
                user_funds[uid]["cash_amount"] = float(cash or 0.0)

    # 5. 获取最近交易日收盘数据（周末/假期：查DB最新快照日期，不用today-1）
    async with AsyncSession(engine) as session:
        from sqlalchemy import func as sa_func
        latest_date_stmt = select(sa_func.max(DailySignalSnapshot.snapshot_date)).where(
            DailySignalSnapshot.snapshot_date < date.today()
        )
        yesterday = await session.scalar(latest_date_stmt)
        if not yesterday:
            yesterday = date.today() - timedelta(days=1)
        yesterday_str = yesterday.isoformat() if hasattr(yesterday, 'isoformat') else str(yesterday)
        logger.info('[Scheduler] [preview] 昨日快照日期=%s', yesterday_str)
        
        snap_stmt = select(DailySignalSnapshot).where(
            DailySignalSnapshot.snapshot_date == yesterday
        )
        snap_result = await session.execute(snap_stmt)
        yesterday_snapshots = {s.target_code: s for s in snap_result.scalars().all()}

    success = 0
    for user_id, data in user_funds.items():
        total_assets = data["total_mv"] + data.get("cash_amount", 0.0)

        for fund_code in data["funds"]:
            try:
                # 5a. 获取基金实时估值
                gszzl = await get_fund_realtime_nav(fund_code)
                gszzl_source = "fundgz" if gszzl is not None else "unavailable"

                # 5a-2. 更新盘中高低点追踪 (供14:50任务A持久化使用)
                hl_key = f"{settings.VALIDATION_INTRADAY_HL_PREFIX}:{today_str}:{fund_code}"
                hl_data = await cache_get(hl_key)
                if gszzl is not None:
                    if hl_data and isinstance(hl_data, dict):
                        intraday_high_gszzl = max(float(hl_data.get("high", gszzl)), gszzl)
                        intraday_low_gszzl = min(float(hl_data.get("low", gszzl)), gszzl)
                    else:
                        intraday_high_gszzl = gszzl
                        intraday_low_gszzl = gszzl
                    await cache_set(hl_key, {
                        "high": intraday_high_gszzl,
                        "low": intraday_low_gszzl,
                        "updated_at": now.isoformat(),
                    }, ttl=86400)
                else:
                    # gszzl=None 时读已有数据但不更新
                    if hl_data and isinstance(hl_data, dict):
                        intraday_high_gszzl = float(hl_data.get("high")) if hl_data.get("high") is not None else None
                        intraday_low_gszzl = float(hl_data.get("low")) if hl_data.get("low") is not None else None
                    else:
                        intraday_high_gszzl = None
                        intraday_low_gszzl = None

                # 5b. 从Redis读取元数据（多天递减 fallback：今日15:40才打包，盘中使用最近可用meta）
                meta = None
                meta_date_used = None
                for offset in range(5):  # today → yesterday → -2d → -3d → -4d
                    check_date = (date.today() - timedelta(days=offset)).isoformat()
                    meta_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{check_date}:meta:{fund_code}"
                    meta = await cache_get(meta_key)
                    if meta:
                        meta_date_used = check_date
                        if offset > 0:
                            logger.info("[Scheduler] [preview] %s 使用%d天前元数据(%s)", fund_code, offset, check_date)
                        break
                if not meta:
                    logger.warning("[Scheduler] [preview] %s 元数据缺失(近5天均无)，尝试即时打包", fund_code)
                    packed = await _pack_meta_for_fund(fund_code)
                    if packed:
                        # 打包成功，重新读取 meta
                        meta = await cache_get(
                            f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:meta:{fund_code}"
                        )
                        if meta:
                            meta_date_used = today_str
                            logger.info("[Scheduler] [preview] %s 即时打包成功，继续预演", fund_code)
                        else:
                            logger.warning("[Scheduler] [preview] %s 即时打包后仍无meta，跳过", fund_code)
                            continue
                    else:
                        logger.warning("[Scheduler] [preview] %s 即时打包失败(nav不足?)，跳过", fund_code)
                        continue

                # 5c. 获取昨日收盘数据
                snap = yesterday_snapshots.get(fund_code)
                has_snapshot = snap is not None
                if snap:
                    yesterday_score = float(snap.composite_score or 50.0)
                    yesterday_signal = snap.signal_level or "B"
                    yesterday_confidence = snap.confidence_stars or 3
                else:
                    # 无昨日快照（可能是新加入的基金）-- 从Redis缓存读
                    sector_code = meta.get("sector_code")
                    if sector_code and sector_code.startswith("801"):
                        # Fix #6: aggregate key v5:sector:sentiment (含所有板块),
                        # 不是 per-sector key v5:sector:sentiment:{sector_code}(不存在)
                        sector_cache = await cache_get("v5:sector:sentiment")
                        if isinstance(sector_cache, dict):
                            sectors_list = sector_cache.get("data", {}).get("sectors", [])
                            matched = None
                            for sec in sectors_list:
                                if str(sec.get("sector_code", "")) == sector_code:
                                    matched = sec
                                    break
                            if matched:
                                yesterday_score = float(matched.get("sentiment_score", 50.0))
                                yesterday_signal = matched.get("signal_level", "B")
                            else:
                                yesterday_score = 50.0
                                yesterday_signal = "B"
                        else:
                            yesterday_score = 50.0
                            yesterday_signal = "B"
                    else:
                        broad_cache = await cache_get(f"fsa:sentiment:{fund_code}")
                        if isinstance(broad_cache, dict):
                            yesterday_score = float(broad_cache.get("score", 50.0))
                            yesterday_signal = broad_cache.get("signal", "B")
                        else:
                            yesterday_score = 50.0
                            yesterday_signal = "B"
                    yesterday_confidence = 3

                # 补充meta中的yesterday_score/signal（供threshold计算使用）
                meta["yesterday_score"] = yesterday_score
                meta["yesterday_signal"] = yesterday_signal

                # 5d. 弹性系数推算
                if gszzl is not None and yesterday_score is not None:
                    elasticity = _calculate_elasticity(fund_code, gszzl, meta)
                    score_delta = gszzl * elasticity
                    score_delta = max(-settings.INTRADAY_PREVIEW_SCORE_DELTA_CLAMP,
                                      min(settings.INTRADAY_PREVIEW_SCORE_DELTA_CLAMP, score_delta))
                    preview_score = yesterday_score + score_delta
                    preview_score = max(0, min(100, preview_score))  # clamp到0-100
                    
                    preview_signal = _score_to_signal(preview_score, list(settings.V5_SIGNAL_BOUNDARIES))
                else:
                    # 无估值数据 -- fallback到昨日信号
                    preview_score = yesterday_score
                    preview_signal = yesterday_signal or "B"
                    elasticity = None
                    score_delta = None

                # 5e. 获取当前仓位百分比
                async with AsyncSession(engine) as session:
                    pct_stmt = select(UserPortfolio.market_value).where(
                        UserPortfolio.user_id == user_id,
                        UserPortfolio.fund_code == fund_code,
                    )
                    pct_result = await session.execute(pct_stmt)
                    fund_mv = pct_result.scalar_one_or_none() or 0.0
                    
                    # 计算仓位百分比 = 单基金市值/总资产
                    current_pct = float(fund_mv) / total_assets if total_assets > 0 else 0.0

                    # 5f. import复用 PositionEngineV5
                    # 时段折减：早盘-2星、午盘-1星、尾盘-0星（不低于1星）
                    preview_discount = 3 - preview_confidence
                    effective_stars = max(1, yesterday_confidence - preview_discount)

                    pos_engine = PositionEngineV5(session)
                    preview_result = await pos_engine.calculate(
                        user_id=user_id,
                        fund_code=fund_code,
                        current_position_pct=current_pct,
                        signal_level=preview_signal,
                        confidence_stars=effective_stars,
                        regime=meta.get("regime", "sideways"),
                        cash_amount=data.get("cash_amount", 0.0),  # 盘中含现金（与14:40统一）
                        total_assets=total_assets,
                    )

                    # 5g. 构建异常提示 + 综合解读
                    anomaly_notes = _build_anomaly_notes(
                        gszzl=gszzl,
                        gszzl_source=gszzl_source,
                        elasticity=elasticity,
                        score_delta=score_delta,
                        preview_signal=preview_signal,
                        yesterday_signal=yesterday_signal,
                        meta_date_used=meta_date_used,
                        today_str=today_str,
                        has_snapshot=has_snapshot,
                        preview_result=preview_result,
                    )
                    preview_summary = _build_preview_summary(
                        preview_confidence=preview_confidence,
                        gszzl=gszzl,
                        gszzl_source=gszzl_source,
                        preview_score=round(preview_score, 2),
                        yesterday_score=yesterday_score,
                        score_delta=round(score_delta, 2) if score_delta is not None else None,
                        preview_signal=preview_signal,
                        yesterday_signal=yesterday_signal,
                        effective_stars=effective_stars,
                        yesterday_confidence=yesterday_confidence,
                        preview_result=preview_result,
                        anomaly_notes=anomaly_notes,
                    )

                    # 5h. 场景状态判定
                    _gates = preview_result.get("gates") or {}
                    _gate_1_triggered = (_gates.get("gate_1") or {}).get("triggered", False)
                    _gate_2_triggered = (_gates.get("gate_2") or {}).get("triggered", False)
                    _has_danger = any(n["level"] == "danger" for n in anomaly_notes)
                    _has_warning = any(n["level"] in ("warning", "danger") for n in anomaly_notes)

                    if _gate_1_triggered or _gate_2_triggered or preview_result.get("action") == "decrease":
                        overall_status = "stop_loss"
                    elif _has_warning or (gszzl is not None and abs(gszzl) > 3.0):
                        overall_status = "warning"
                    else:
                        overall_status = "normal"

                    # 5i. 组装预演结果
                    preview_output = {
                        "is_preview": True,
                        "preview_confidence": preview_confidence,
                        "confidence_note": _get_confidence_note(preview_confidence),
                        "accuracy_warning": "盘中信号为预演估算，需收盘确认",
                        "calc_time": now.isoformat(),
                        "data_version": "v1",
                        "date": today_str,
                        "fund_code": fund_code,
                        
                        # 估算情绪分
                        "preview_score": round(preview_score, 2),
                        "yesterday_score": yesterday_score,
                        "score_delta": round(score_delta, 2) if score_delta is not None else None,
                        "gszzl": gszzl,
                        "gszzl_source": gszzl_source,
                        "intraday_high_gszzl": round(intraday_high_gszzl, 2) if intraday_high_gszzl is not None else None,
                        "intraday_low_gszzl": round(intraday_low_gszzl, 2) if intraday_low_gszzl is not None else None,
                        "elasticity": round(elasticity, 2) if elasticity is not None else None,
                        
                        # 预演操作建议
                        "action": preview_result.get("action", "hold"),
                        "target_position_pct": preview_result.get("target_position_pct", 0),
                        "current_position_pct": preview_result.get("current_position_pct", current_pct),
                        "reason": _prefix_preview_reason(preview_result.get("reason", "")),
                        "signal_level": preview_signal,
                        "confidence_stars": effective_stars,
                        
                        # 预演风控
                        "gates": preview_result.get("gates"),
                        "track_type": preview_result.get("track_type"),
                        "sector_track": preview_result.get("sector_track"),
                        
                        # 阈值数据
                        "thresholds": _build_threshold_data(preview_result, meta, gszzl, round(preview_score, 2)),
                        
                        # 昨今对比
                        "yesterday_signal": yesterday_signal,
                        "yesterday_confidence": yesterday_confidence,
                        "signal_change": _calc_signal_change(yesterday_signal, preview_signal),

                        # 异常场景提示 + 综合解读
                        "anomaly_notes": anomaly_notes,
                        "preview_summary": preview_summary,
                        "overall_status": overall_status,
                    }

                    # 5j. 写入Redis
                    cache_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:{fund_code}:{user_id}"
                    await cache_set(cache_key, preview_output, ttl=settings.INTRADAY_PREVIEW_CACHE_TTL)

                    # 5j+1. 写入Redis序列 (盘中形态追踪 + validation-C 解耦数据源)
                    series_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:series:{today_str}:{fund_code}:{user_id}"
                    series_entry = {
                        "ts": now.strftime("%H:%M"),
                        "gszzl": gszzl,
                        "preview_score": round(preview_score, 2),
                        "preview_signal": preview_signal,
                        "action": preview_result.get("action", "hold"),
                    }
                    # 追加式写入: 读现有序列 → append → 回写
                    existing_series = await cache_get(series_key)
                    if existing_series and isinstance(existing_series, list):
                        existing_series.append(series_entry)
                        await cache_set(series_key, existing_series, ttl=86400)
                    else:
                        await cache_set(series_key, [series_entry], ttl=86400)

                    success += 1
                    logger.info("[Scheduler] [preview] %s: score=%.1f->%.1f signal=%s->%s gszzl=%.2f action=%s",
                               fund_code, yesterday_score, preview_score, yesterday_signal, preview_signal,
                               gszzl or 0, preview_result.get("action", "hold"))
            except Exception as e:
                logger.error("[Scheduler] [preview] %s FAIL: %s", fund_code, e)

    logger.info("[Scheduler] 盘中预演计算完成 -- %d 成功", success)

    # 更新数据版本号 + 失效缓存
    try:
        await update_data_version("signal_board")
        await invalidate_module_cache("signal_board")
    except Exception as e:
        logger.warning("[Scheduler] 版本号更新失败(signal_board): %s", e)

# ============================================================
# 辅助函数：为单个基金打包预演元数据（meta_pack 定时任务 & preview_calculate 即时补打共用）
# ============================================================
async def _pack_meta_for_fund(fund_code: str) -> bool:
    """
    为单个基金打包预演元数据 -- 可被 _run_intraday_meta_pack() 定时任务和
    _run_intraday_preview_calculate() 即时补打共同调用。

    返回 True 表示打包成功，False 表示失败（nav 数据不足或其他异常）。
    """
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.position_execution import PositionExecution
    from app.models.fund_nav import FundNav
    from app.engine.trend_guard import _calculate_ma20_trend, _calculate_macd
    from app.engine.trend_guard import _get_sector_track, _get_fund_sector_code, check_panic_gate
    from app.core.redis_client import cache_get, cache_set

    today = date.today()
    today_str = today.isoformat()
    engine = get_async_engine()

    try:
        async with AsyncSession(engine) as session:
            # 1. MA20价格 -- 从 fund_nav 表获取最近60条
            nav_stmt = select(FundNav.nav, FundNav.nav_date).where(
                FundNav.fund_code == fund_code
            ).order_by(FundNav.nav_date.desc()).limit(60)
            nav_result = await session.execute(nav_stmt)
            nav_rows = nav_result.all()

            if len(nav_rows) < 20:
                logger.warning("[Scheduler] [meta] %s nav数据不足(%d<20)，跳过MA20", fund_code, len(nav_rows))
                return False

            # 重组为 trend_guard 需要的 nav_history 格式
            nav_history = [{"date": str(r[1]), "nav": float(r[0])} for r in reversed(nav_rows)]

            # 纯计算函数，可直接在async环境调用
            ma20_trend = _calculate_ma20_trend(nav_history) if len(nav_history) >= 20 else "unknown"

            # 计算MA20价格（最近20条的均值）
            prices = [float(r[0]) for r in reversed(nav_rows)]
            ma20_price = sum(prices[-20:]) / 20 if len(prices) >= 20 else None

            # 2. MACD状态 -- 纯计算函数
            macd_result = _calculate_macd(nav_history) if len(nav_history) >= 35 else None

            # 3. 轨道类型 -- 同步函数，需asyncio.to_thread包装（内部用同步pymysql）
            sector_track = await asyncio.to_thread(_get_sector_track, fund_code)

            # 4. 板块代码 -- 同步函数，需asyncio.to_thread包装
            sector_code = await asyncio.to_thread(_get_fund_sector_code, fund_code)

            # 5. 冷却期 -- 从 PositionExecution 查询所有用户的最近减仓日期
            cooldown_stmt = select(PositionExecution.execute_date).where(
                PositionExecution.fund_code == fund_code,
                PositionExecution.operation_type.in_(["sell", "decrease"])
            ).order_by(PositionExecution.execute_date.desc()).limit(1)
            cooldown_result = await session.execute(cooldown_stmt)
            last_execute_date = cooldown_result.scalar_one_or_none()
            cooldown_days = (today - last_execute_date).days if last_execute_date else 999

            # 6. regime -- 从沪深300缓存获取（15:30快照已写入）
            regime_cache = await cache_get("fsa:sentiment:SH000300")
            regime = regime_cache.get("regime", "sideways") if isinstance(regime_cache, dict) else "sideways"

            # 7. 组合打包
            meta = {
                "fund_code": fund_code,
                "date": today_str,
                "ma20_price": round(ma20_price, 4) if ma20_price else None,
                "ma20_trend": ma20_trend,
                "macd": macd_result,
                "sector_track": sector_track,
                "sector_code": sector_code,
                "cooldown_days": cooldown_days,
                "cooldown_last_date": str(last_execute_date) if last_execute_date else None,
                "regime": regime,
                "matrix": settings.V5_POSITION_MATRIX,
                "conf_adj": {str(k): v for k, v in settings.V5_CONFIDENCE_POSITION_ADJ.items()},
                "cost_threshold": settings.V5_COST_THRESHOLD_PCT,
                "freq_days": settings.V5_FREQUENCY_LIMIT_DAYS,
                "signal_boundaries": list(settings.V5_SIGNAL_BOUNDARIES),
                "nav_history_length": len(nav_history),
                "is_data_sufficient": len(nav_history) >= 60,
                # V5.4 扩展: trend_guard 缓存重构所需数据
                "nav_history": nav_history,        # 60条净值 (Gate体系 + drawdown 计算需要)
                "gate_p": await asyncio.to_thread(check_panic_gate, fund_code=fund_code),  # 沪深300恐慌闸结果
                "packed_at": datetime.now().isoformat(),
            }

            cache_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:meta:{fund_code}"
            await cache_set(cache_key, meta, ttl=432000)  # TTL=5天，覆盖周末+短假期

            logger.info("[Scheduler] [meta] %s OK (ma20=%s, track=%s, regime=%s, cooldown=%dd)",
                       fund_code, ma20_trend, sector_track, regime, cooldown_days)
            return True
    except Exception as e:
        logger.error("[Scheduler] [meta] %s FAIL: %s", fund_code, e)
        return False


# 任务 14：盘中预演元数据打包（15:40 — 收盘后，在快照15:30+板块价格15:35之后）
# ============================================================
async def _run_intraday_meta_pack() -> None:
    """
    盘中预演元数据打包 -- 收盘后15:40执行

    遍历所有持仓基金，调用 _pack_meta_for_fund() 逐个打包。
    新加入的基金无需等待此任务 -- 预演计算检测到 meta 缺失时会自动调用
    _pack_meta_for_fund() 即时补打。
    """
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user_portfolio import UserPortfolio
    from app.core.redis_client import cache_get

    if not settings.ENABLE_INTRADAY_PREVIEW:
        logger.info("[Scheduler] 盘中预演全局关闭，跳过元数据打包")
        return

    # 检查Redis全局开关
    redis_switch = await cache_get("intraday_preview:global_switch")
    if redis_switch == "off":
        logger.info("[Scheduler] Redis全局开关关闭，跳过元数据打包")
        return

    engine = get_async_engine()

    # 获取所有持仓基金代码
    async with AsyncSession(engine) as session:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]

    if not fund_codes:
        logger.info("[Scheduler] 无持仓基金，跳过元数据打包")
        return

    success = 0
    for fund_code in fund_codes:
        ok = await _pack_meta_for_fund(fund_code)
        if ok:
            success += 1

    logger.info("[Scheduler] 元数据打包完成 -- %d/%d 成功", success, len(fund_codes))


# ============================================================
# 任务 15：弹性系数周更（周五收盘后）
# ============================================================
async def _run_intraday_elastic_weekly() -> None:
    """
    弹性系数每周校准 -- 周五收盘后执行

    计算逻辑：
    1. 取最近5个交易日的数据
    2. 对每个持仓基金，从 factor_history 取收盘情绪分变化(score_delta)
    3. 从 eastmoney 取盘中涨跌幅(gszzl)
    4. elasticity = avg(score_delta / gszzl) for valid days where |gszzl| > 0.5%
    5. 写入 Redis intraday_preview:v1:elastic:{fund_code}

    弹性系数范围约束：
    - 基准2.0，范围[1.5, 3.0]
    - |gszzl|>5%的极端行情日不参与计算（强制系数1.0覆盖）
    """
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user_portfolio import UserPortfolio
    from app.models.daily_signal_snapshot import DailySignalSnapshot
    from app.core.redis_client import cache_get, cache_set

    if not settings.ENABLE_INTRADAY_PREVIEW:
        logger.info("[Scheduler] 盘中预演关闭，跳过弹性系数周更")
        return

    redis_switch = await cache_get("intraday_preview:global_switch")
    if redis_switch == "off":
        logger.info("[Scheduler] Redis全局开关关闭，跳过弹性系数周更")
        return

    engine = get_async_engine()
    today = date.today()

    # 获取所有持仓基金
    async with AsyncSession(engine) as session:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]

    success = 0
    for fund_code in fund_codes:
        try:
            async with AsyncSession(engine) as session:
                # 取最近5个交易日的因子历史（含score和signal）
                stmt = select(DailySignalSnapshot).where(
                    DailySignalSnapshot.target_code == fund_code,
                    DailySignalSnapshot.snapshot_date >= today - timedelta(days=10)  # 10天窗口确保5个交易日
                ).order_by(DailySignalSnapshot.snapshot_date.desc()).limit(5)
                result = await session.execute(stmt)
                factor_rows = result.scalars().all()

                if len(factor_rows) < 2:
                    logger.warning("[Scheduler] [elastic] %s 因子历史不足(%d<2)", fund_code, len(factor_rows))
                    # fallback到默认弹性系数
                    await cache_set(
                        f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:elastic:{fund_code}",
                        {"elasticity": settings.INTRADAY_PREVIEW_ELASTIC_BASE, "source": "default", "updated_at": datetime.now().isoformat()},
                        ttl=604800  # 7天
                    )
                    success += 1
                    continue

                # 计算弹性系数：对连续两天的score差值与gszzl的比值
                elasticity_samples = []
                for i in range(len(factor_rows) - 1):
                    today_row = factor_rows[i]
                    yesterday_row = factor_rows[i + 1]

                    score_delta = float(today_row.composite_score or 0) - float(yesterday_row.composite_score or 0)

                    # 使用score波动率作为弹性系数调整因子
                    score_volatility = abs(score_delta)

                    if score_volatility > 0:
                        # 高波动日(score_delta>10) → 降低弹性系数（降敏）
                        if score_volatility > 10:
                            elasticity_samples.append(settings.INTRADAY_PREVIEW_ELASTIC_LOW)
                        # 中波动日(score_delta 5-10) → 中等弹性
                        elif score_volatility > 5:
                            elasticity_samples.append(settings.INTRADAY_PREVIEW_ELASTIC_MID_MIN)
                        # 低波动日(score_delta <5) → 高弹性系数（正常灵敏度）
                        else:
                            elasticity_samples.append(settings.INTRADAY_PREVIEW_ELASTIC_HIGH)

                if elasticity_samples:
                    avg_elasticity = sum(elasticity_samples) / len(elasticity_samples)
                    # 范围约束 [1.5, 3.0]
                    avg_elasticity = max(settings.INTRADAY_PREVIEW_ELASTIC_LOW,
                                        min(settings.INTRADAY_PREVIEW_ELASTIC_HIGH, avg_elasticity))
                else:
                    avg_elasticity = settings.INTRADAY_PREVIEW_ELASTIC_BASE

                # 写入Redis（7天有效期，下周五重新计算）
                await cache_set(
                    f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:elastic:{fund_code}",
                    {
                        "elasticity": round(avg_elasticity, 2),
                        "source": "weekly_calculated",
                        "samples": len(elasticity_samples),
                        "updated_at": datetime.now().isoformat(),
                    },
                    ttl=604800  # 7天
                )

                success += 1
                logger.info("[Scheduler] [elastic] %s: %.2f (%d samples)", fund_code, avg_elasticity, len(elasticity_samples))

        except Exception as e:
            logger.error("[Scheduler] [elastic] %s FAIL: %s", fund_code, e)

    logger.info("[Scheduler] 弹性系数周更完成 -- %d/%d", success, len(fund_codes))

# 任务 17：对账校准 -- 15:50收盘后，对比盘中预演 vs 实际收盘信号
# ============================================================

async def _run_intraday_preview_reconciliation() -> None:
    """
    对账校准 -- 每个交易日15:50执行（在元数据打包15:40之后）

    核心逻辑：
    1. 读取最后一轮盘中预演结果（Redis缓存）
    2. 读取当日收盘决策快照（DailySignalSnapshot）
    3. 对比：预演score vs 收盘score、预演signal vs 收盘signal
    4. 计算偏差并记录到 Redis 对账日志
    5. 若偏差超过阈值，自动校准弹性系数缓存（为次日预演修正）

    偏差阈值：
    - score偏差 > 20分 → 校准弹性系数（乘以修正因子）
    - score偏差 > 30分 → 强制弹性系数=1.0（极端偏差，次日降敏）
    - signal等级偏差 >= 2级 → 记录警告但不自动校准（信号跳跃需人工复核）

    对账日志Redis key: intraday_preview:v1:{date}:reconcile:{fund_code}
    """
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user_portfolio import UserPortfolio
    from app.models.daily_signal_snapshot import DailySignalSnapshot
    from app.core.redis_client import cache_get, cache_set

    if not settings.ENABLE_INTRADAY_PREVIEW:
        logger.info("[Scheduler] 盘中预演关闭，跳过对账校准")
        return

    redis_switch = await cache_get("intraday_preview:global_switch")
    if redis_switch == "off":
        logger.info("[Scheduler] Redis全局开关关闭，跳过对账校准")
        return

    engine = get_async_engine()
    today = date.today()
    today_str = today.isoformat()

    # 1. 获取所有持仓基金（跨用户，去重）
    async with AsyncSession(engine) as session:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]

    # 2. 获取当日收盘快照
    async with AsyncSession(engine) as session:
        snap_stmt = select(DailySignalSnapshot).where(
            DailySignalSnapshot.snapshot_date == today
        )
        snap_result = await session.execute(snap_stmt)
        today_snapshots = {s.target_code: s for s in snap_result.scalars().all()}

    reconcile_count = 0
    calibrated_count = 0

    for fund_code in fund_codes:
        try:
            # 3. 读取最后一轮盘中预演
            preview_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:{fund_code}:default"
            preview_data = await cache_get(preview_key)

            if not preview_data:
                # fallback：遍历用户ID寻找任意预演缓存
                async with AsyncSession(engine) as session:
                    user_stmt = select(UserPortfolio.user_id).where(
                        UserPortfolio.fund_code == fund_code
                    ).limit(1)
                    user_result = await session.execute(user_stmt)
                    user_row = user_result.first()
                    if user_row:
                        preview_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:{fund_code}:{user_row[0]}"
                        preview_data = await cache_get(preview_key)

            if not preview_data:
                logger.warning("[Scheduler] [reconcile] %s 无盘中预演缓存，跳过对账", fund_code)
                continue

            # 4. 获取收盘快照
            snap = today_snapshots.get(fund_code)
            if not snap:
                logger.warning("[Scheduler] [reconcile] %s 无当日收盘快照，跳过对账", fund_code)
                continue

            # 5. 对比
            preview_score = float(preview_data.get("preview_score", 50.0))
            actual_score = float(snap.composite_score or 50.0)
            score_diff = abs(preview_score - actual_score)

            preview_signal = preview_data.get("signal_level", "B")
            actual_signal = snap.signal_level or "B"
            signal_diff = _signal_level_distance(preview_signal, actual_signal)

            # 6. 组装对账日志
            reconcile_log = {
                "fund_code": fund_code,
                "date": today_str,
                "reconcile_time": datetime.now().isoformat(),
                "preview_score": preview_score,
                "actual_score": actual_score,
                "score_diff": round(score_diff, 2),
                "preview_signal": preview_signal,
                "actual_signal": actual_signal,
                "signal_diff": signal_diff,
                "gszzl": preview_data.get("gszzl"),
                "elasticity_used": preview_data.get("elasticity"),
                "auto_calibrated": False,
                "calibration_factor": None,
            }

            # 7. 自动校准弹性系数（若偏差超阈值）
            if score_diff > settings.INTRADAY_PREVIEW_SCORE_DELTA_CLAMP:
                # score偏差 > 20分 -> 校准
                elastic_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:elastic:{fund_code}"
                elastic_data = await cache_get(elastic_key)

                current_elasticity = float(elastic_data.get("elasticity", settings.INTRADAY_PREVIEW_ELASTIC_BASE)) if elastic_data else settings.INTRADAY_PREVIEW_ELASTIC_BASE

                if score_diff > 30:
                    # 极端偏差 -> 强制弹性系数=1.0（次日降敏）
                    new_elasticity = 1.0
                    calibration_factor = 0.0
                else:
                    # 中等偏差 -> 按比例修正
                    actual_delta = actual_score - float(preview_data.get("yesterday_score", 50.0))
                    preview_delta = preview_data.get("score_delta", 0) or 0
                    gszzl_val = preview_data.get("gszzl") or 0
                    if abs(preview_delta) > 0.5 and abs(gszzl_val) > 0.5:
                        ideal_elasticity = abs(actual_delta / preview_delta) * abs(gszzl_val)
                        # 取当前弹性系数和理想弹性系数的加权平均（50%权重，避免过度修正）
                        new_elasticity = 0.5 * current_elasticity + 0.5 * max(1.0, min(3.0, ideal_elasticity))
                    else:
                        # preview_delta太小，无法有效反推 -> 降低10%
                        new_elasticity = current_elasticity * 0.9

                    # 范围约束 [1.0, 3.0]（对账校准允许降到1.0，比周更的1.5更低）
                    new_elasticity = max(1.0, min(3.0, new_elasticity))
                    calibration_factor = round(new_elasticity / current_elasticity, 2) if current_elasticity > 0 else None

                # 更新弹性系数缓存（TTL=86400，次日meta_pack会重新读取）
                await cache_set(
                    elastic_key,
                    {
                        "elasticity": round(new_elasticity, 2),
                        "source": "reconcile_calibrated",
                        "previous_elasticity": current_elasticity,
                        "calibration_reason": f"score_diff={round(score_diff, 1)}",
                        "updated_at": datetime.now().isoformat(),
                    },
                    ttl=86400  # 1天（次日重新评估）
                )

                reconcile_log["auto_calibrated"] = True
                reconcile_log["calibration_factor"] = calibration_factor
                calibrated_count += 1
                logger.info("[Scheduler] [reconcile] %s 校准: elasticity %.2f->%.2f (score_diff=%.1f)",
                            fund_code, current_elasticity, new_elasticity, score_diff)

            # 8. 写入对账日志到Redis（保留7天，供分析）
            reconcile_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:reconcile:{fund_code}"
            await cache_set(reconcile_key, reconcile_log, ttl=604800)

            reconcile_count += 1
            logger.info("[Scheduler] [reconcile] %s: score_diff=%.1f signal_diff=%d",
                        fund_code, score_diff, signal_diff)

        except Exception as e:
            logger.error("[Scheduler] [reconcile] %s FAIL: %s", fund_code, e)

    logger.info("[Scheduler] 对账校准完成 -- %d 对账 / %d 校准 / %d 总基金",
                reconcile_count, calibrated_count, len(fund_codes))


def _signal_level_distance(signal_a: str, signal_b: str) -> int:
    """计算两个信号等级之间的距离（等级数差）"""
    signal_order = {"S+": 7, "S": 6, "A": 5, "B": 4, "C": 3, "D": 2, "E": 1}
    a_val = signal_order.get(signal_a, 4)
    b_val = signal_order.get(signal_b, 4)
    return abs(a_val - b_val)


# ============================================================
# 申万行业分类常量 — 申万代码/名称映射 + 申万→同花顺映射表
# ============================================================

# 申万一级行业代码 → 行业名称（31个，2021版）
SW_CODE_TO_NAME: dict[str, str] = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}

# 申万一级行业 → 同花顺子板块列表映射表
# 用于从同花顺 stock_board_industry_summary_ths() 实时数据转换为申万行业涨跌幅
# 多个子板块取等权平均（实时涨跌幅仅作DeepSeek上下文参考，方向对即可）
SW_TO_THS_MAPPING: dict[str, list[str]] = {
    "农林牧渔": ["养殖业", "农产品加工", "种植业与林业"],
    "基础化工": ["化学制品", "化学原料", "化学纤维", "农化制品", "塑料制品", "橡胶制品", "非金属材料"],
    "钢铁": ["钢铁"],
    "有色金属": ["工业金属", "小金属", "贵金属", "能源金属", "金属新材料"],
    "电子": ["半导体", "消费电子", "光学光电子", "元件", "电子化学品", "其他电子"],
    "家用电器": ["白色家电", "黑色家电", "小家电", "厨卫电器"],
    "食品饮料": ["白酒", "食品加工制造", "饮料制造"],
    "纺织服饰": ["服装家纺", "纺织制造"],
    "轻工制造": ["家居用品", "包装印刷", "造纸"],
    "医药生物": ["化学制药", "中药", "生物制品", "医疗器械", "医疗服务", "医药商业"],
    "公用事业": ["电力", "燃气"],
    "交通运输": ["公路铁路运输", "机场航运", "港口航运", "物流"],
    "房地产": ["房地产"],
    "商贸零售": ["零售", "贸易", "互联网电商"],
    "社会服务": ["旅游及酒店", "教育", "其他社会服务"],
    "综合": ["综合"],
    "建筑材料": ["建筑材料"],
    "建筑装饰": ["建筑装饰"],
    "电力设备": ["光伏设备", "电池", "电网设备", "风电设备", "其他电源设备"],
    "国防军工": ["军工电子", "军工装备"],
    "计算机": ["软件开发", "IT服务", "计算机设备"],
    "传媒": ["影视院线", "文化传媒", "游戏"],
    "通信": ["通信服务", "通信设备"],
    "银行": ["银行"],
    "非银金融": ["证券", "保险", "多元金融"],
    "汽车": ["汽车整车", "汽车零部件", "汽车服务及其他"],
    "机械设备": ["通用设备", "专用设备", "工程机械", "自动化设备", "电机", "轨交设备"],
    "煤炭": ["煤炭开采加工"],
    "石油石化": ["油气开采及服务", "石油加工贸易"],
    "环保": ["环保设备", "环境治理"],
    "美容护理": ["美容护理"],
}


async def _fetch_realtime_sector_changes() -> dict[str, float]:
    """
    获取申万一级行业涨跌幅（盘中实时优先，T-1降级）。

    数据源优先级:
    1. 同花顺 (stock_board_industry_summary_ths) + 映射表 — T-0 盘中实时，主力(稳定免费)
    2. 东财 web API (stock_board_industry_name_em) — T-0 盘中实时，补充(可能被限流)
    3. 申万指数历史 (index_hist_sw) — T-1 昨日日涨跌幅，兜底

    返回 {sector_name: change_pct} 字典，如 {"通信": 5.37, "有色金属": -2.80}。
    key 为申万一级行业名称。
    """
    result: dict[str, float] = {}

    # 方式1: 同花顺实时板块涨跌幅 + 申万映射表 (T-0, 主力)
    try:
        import akshare as ak
        import asyncio
        df = await asyncio.to_thread(ak.stock_board_industry_summary_ths)
        ths_data: dict[str, float] = {}
        for _, row in df.iterrows():
            name = str(row.get("板块", "")).strip()
            chg = row.get("涨跌幅")
            if name and chg is not None:
                ths_data[name] = float(chg)
        # 通过映射表转换为申万一级行业涨跌幅（等权平均）
        for sw_name, ths_list in SW_TO_THS_MAPPING.items():
            matched = [ths_data[t] for t in ths_list if t in ths_data]
            if matched:
                result[sw_name] = round(sum(matched) / len(matched), 2)
        if result:
            logger.info("[validation-A] 板块实时涨跌幅(同花顺 T-0): %d 个行业", len(result))
            return result
    except Exception as e:
        logger.warning("[validation-A] 同花顺板块涨跌幅获取失败，将降级到东财web: %s", e)

    # 方式2: 东财 web API 实时板块涨跌幅 (T-0, 补充 — 可能被限流)
    try:
        import akshare as ak
        import asyncio
        df = await asyncio.to_thread(ak.stock_board_industry_name_em)
        em_data: dict[str, float] = {}
        for _, row in df.iterrows():
            name = str(row.get("板块名称", "")).strip()
            chg = row.get("涨跌幅")
            if name and chg is not None:
                em_data[name] = float(chg)
        # 东财行业名称与申万不完全一致，尝试直接匹配申万行业名
        for sw_name in SW_TO_THS_MAPPING.keys():
            if sw_name in em_data:
                result[sw_name] = em_data[sw_name]
        if result:
            logger.info("[validation-A] 板块实时涨跌幅(东财web T-0): %d 个行业", len(result))
            return result
    except Exception as e:
        logger.warning("[validation-A] 东财web板块涨跌幅获取失败，将降级到申万指数T-1: %s", e)

    # 方式3: 申万指数历史 (T-1 降级 — 兜底)
    try:
        import akshare as ak
        import asyncio

        async def _fetch_one(code: str, name: str):
            try:
                df = await asyncio.to_thread(ak.index_hist_sw, symbol=code, period="day")
                if len(df) >= 2:
                    latest = float(df.iloc[-1]["收盘"])
                    prev = float(df.iloc[-2]["收盘"])
                    if prev > 0:
                        return name, round((latest / prev - 1) * 100, 2)
            except Exception:
                pass
            return name, None

        sem = asyncio.Semaphore(5)

        async def _fetch_with_sem(code, name):
            async with sem:
                return await _fetch_one(code, name)

        tasks = [_fetch_with_sem(c, n) for c, n in SW_CODE_TO_NAME.items()]
        results = await asyncio.gather(*tasks)
        for name, chg in results:
            if chg is not None:
                result[name] = chg
        if result:
            logger.info("[validation-A] 板块涨跌幅(申万指数 T-1降级): %d 个行业", len(result))
    except Exception as e:
        logger.warning("[validation-A] 申万指数T-1涨跌幅获取失败: %s", e)

    return result

async def _fetch_realtime_market_chg_pct() -> float | None:
    """
    获取沪深300实时涨跌幅（盘中实时优先）。

    数据源优先级:
    1. 腾讯行情 qt.gtimg.cn — T-0 盘中实时，主力（ECS可访问，东财push2从ECS TLS层被封锁）
    2. 项目既有 get_index_data("SH000300") — T-1 昨日收盘涨跌幅，兜底（盘中不含当日数据）

    返回涨跌幅(%)，如 2.15 / -0.20 / None。
    """
    chg_pct = None

    # 优先: 腾讯行情 API（实时，ECS可访问）
    try:
        import httpx
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            r = await client.get("https://qt.gtimg.cn/q=sh000300")
            r.raise_for_status()
            # 腾讯返回 GBK 编码的 ~分隔字符串
            raw_text = r.content.decode("gb18030", errors="replace")
            for line_seg in raw_text.strip().split(";"):
                line_seg = line_seg.strip()
                if not line_seg or "sh000300" not in line_seg.lower():
                    continue
                try:
                    _, val = line_seg.split("=", 1)
                    val = val.strip().strip('"')
                    fields = val.split("~")
                    current = float(fields[3])  # 当前价
                    yest_close = float(fields[4])  # 昨收
                    if yest_close and yest_close > 0:
                        chg_pct = round((current - yest_close) / yest_close * 100, 2)
                        break
                except (ValueError, IndexError):
                    continue
        if chg_pct is not None:
            logger.info("[Scheduler] 大盘涨跌幅(腾讯实时): %.2f%%", chg_pct)
    except Exception as e:
        logger.warning("[Scheduler] 腾讯行情API获取大盘涨跌幅失败: %s", e)

    # 兜底: 项目既有指数源（T-1 昨日收盘涨跌幅，盘中不含当日数据）
    if chg_pct is None:
        try:
            index_data = await data_source.get_index_data("SH000300")
            fallback_chg = (index_data or {}).get("change_pct")
            if fallback_chg is not None:
                chg_pct = float(fallback_chg)
                logger.warning("[Scheduler] 大盘涨跌幅降级为T-1(昨日收盘): %.2f%%", chg_pct)
        except Exception as e:
            logger.warning("[Scheduler] 大盘涨跌幅兜底获取失败: %s", e)

    return chg_pct



# ============================================================
# 策略验证分析表 — 任务A: 14:50预演持久化 + 系统建议
# ============================================================
async def _run_validation_persist() -> None:
    """
    策略验证-任务A: 14:50 预演持久化 + 系统建议写入

    对每个持仓基金：
    1. 获取最新gszzl（不依赖Redis缓存，避免TTL竞态）
    2. 重新计算弹性系数+情绪分+信号+仓位建议
    3. 从Redis读盘中高低点
    4. 获取大盘/板块涨跌幅
    5. 获取持仓盈亏信息
    6. 计算连续信号天数
    7. 生成系统建议文本
    8. Upsert到strategy_validation_log表(G1-G5,G3b,G4b,G7.system_advice_text,G9)
    """
    from app.core.database import get_async_engine
    from sqlalchemy import select, func as sa_func
    from app.models.user_portfolio import UserPortfolio
    from app.models.user_cash import UserCash
    from app.models.daily_signal_snapshot import DailySignalSnapshot
    from app.models.strategy_validation_log import StrategyValidationLog
    from app.models.fund_nav import FundNav
    from app.models.sector_sentiment import SectorSentiment
    from app.engine.position_v5 import PositionEngineV5
    from app.utils.eastmoney import get_fund_realtime_nav
    from app.core.redis_client import cache_get, cache_set

    if not await _is_trade_day():
        logger.info("[Scheduler] [validation-A] 非交易日，跳过")
        return

    today = date.today()
    today_str = today.isoformat()
    engine = get_async_engine()

    logger.info("[Scheduler] [validation-A] 开始预演持久化 -- %s", today_str)

    # 1. 获取大盘涨跌幅（沪深300）— 盘中实时
    # 修复: 原代码走 data_source.get_all_index_data() 且用 .get("change_pct", 0) 默认0，
    #       盘中14:45今天日线未生成时 change_pct 缺失 → 被伪装成平盘(0%)。
    #       改用混合策略: 优先腾讯行情实时(T-0盘中, qt.gtimg.cn, ECS可访问)；
    #       失败则降级到项目既有 get_index_data("SH000300")(T-1昨日收盘, 盘中不含当日数据)。
    #       任何缺失一律返回 None，绝不填 0。原东财push2从ECS TLS层被封锁，已移除。
    market_index_chg_pct = await _fetch_realtime_market_chg_pct()

    # 1b. 获取板块实时涨跌幅（申万一级行业，盘中实时 — 与大盘同口径）
    # 修复: 原从 Redis v5:sector:sentiment 读 sector_return，但该缓存由 15:45 板块评分
    #       任务写入，15:45 时 akshare 当天收盘数据未出 → 用的是前一日收盘 → 双重滞后。
    #       改为东财 web API 实时获取（akshare stock_board_industry_name_em），
    #       Redis 缓存作为降级。
    realtime_sector_changes = await _fetch_realtime_sector_changes()
    if realtime_sector_changes:
        logger.info("[validation-A] 板块实时涨跌幅: %d 个行业", len(realtime_sector_changes))
    else:
        logger.warning("[validation-A] 板块实时涨跌幅获取失败，将降级到Redis缓存")

    # 2. 获取所有持仓
    async with AsyncSession(engine) as session:
        stmt = select(
            UserPortfolio.user_id,
            UserPortfolio.fund_code,
            UserPortfolio.fund_name,
            UserPortfolio.cost_nav,
            UserPortfolio.market_value,
            UserPortfolio.holding_shares,
            UserPortfolio.buy_date,
        )
        result = await session.execute(stmt)
        portfolio_rows = result.all()

    user_funds: dict[str, dict] = {}
    for row in portfolio_rows:
        uid, fcode, fname, cnav, mv, hshares, bdate = row
        if uid not in user_funds:
            user_funds[uid] = {"funds": [], "total_mv": 0.0}
        user_funds[uid]["funds"].append({
            "fund_code": fcode,
            "fund_name": fname or "",
            "cost_nav": float(cnav or 0),
            "market_value": float(mv or 0),
            "holding_shares": float(hshares or 0),
            "buy_date": bdate,
        })
        user_funds[uid]["total_mv"] += float(mv or 0)

    # 2b. 查询各用户现金余额，加入总资产（与14:40 DeepSeek统一口径）
    async with AsyncSession(engine) as session:
        cash_stmt = select(UserCash.user_id, UserCash.cash_amount)
        cash_result = await session.execute(cash_stmt)
        for cuid, cash in cash_result:
            if cuid in user_funds:
                user_funds[cuid]["cash_amount"] = float(cash or 0.0)
    async with AsyncSession(engine) as session:
        latest_date_stmt = select(sa_func.max(DailySignalSnapshot.snapshot_date)).where(
            DailySignalSnapshot.snapshot_date < today
        )
        yesterday = await session.scalar(latest_date_stmt)
        if not yesterday:
            yesterday = today - timedelta(days=1)

        snap_stmt = select(DailySignalSnapshot).where(
            DailySignalSnapshot.snapshot_date == yesterday
        )
        snap_result = await session.execute(snap_stmt)
        yesterday_snapshots = {s.target_code: s for s in snap_result.scalars().all()}

    # 3b. Fix A: 直接从 fund_nav 表获取最新净值
    # 根因：快照在 T-1 17:05 生成时 fund_nav 可能还没有 T-1 净值，
    #   导致 snap.nav 存的是 T-2 的值。14:45 时 T-1 净值早已入库，直接查更准确。
    all_fund_codes = list({row[1] for row in portfolio_rows})
    latest_nav_map: dict[str, float] = {}
    if all_fund_codes:
        async with AsyncSession(engine) as session:
            for fc in all_fund_codes:
                nav_result = await session.execute(
                    select(FundNav.nav)
                    .where(FundNav.fund_code == fc, FundNav.nav_date <= today)
                    .order_by(FundNav.nav_date.desc())
                    .limit(1)
                )
                nav_row = nav_result.first()
                if nav_row and nav_row[0]:
                    latest_nav_map[fc] = float(nav_row[0])
    logger.info("[validation-A] Fix A: fund_nav 直接取值 %d/%d 只基金",
                len(latest_nav_map), len(all_fund_codes))

    # 4. 获取历史准确率（多窗口: 30/60/90天）
    historical_accuracy: dict = {"signal_accuracy": None, "advice_accuracy": None, "gate_accuracy": None, "multi_window": {}}
    try:
        async with AsyncSession(engine) as session:
            multi_window = {}
            for window_days in (30, 60, 90):
                window_ago = today - timedelta(days=window_days)
                w_stmt = select(
                    sa_func.avg(StrategyValidationLog.signal_accuracy),
                    sa_func.avg(StrategyValidationLog.advice_accuracy),
                    sa_func.avg(StrategyValidationLog.gate_accuracy),
                ).where(
                    StrategyValidationLog.trade_date >= window_ago,
                    StrategyValidationLog.trade_date < today,
                )
                w_result = await session.execute(w_stmt)
                w_row = w_result.one_or_none()
                key = f"{window_days}d"
                multi_window[key] = {
                    "signal": round(float(w_row[0]), 2) if w_row and w_row[0] is not None else None,
                    "advice": round(float(w_row[1]), 2) if w_row and w_row[1] is not None else None,
                    "gate": round(float(w_row[2]), 2) if w_row and w_row[2] is not None else None,
                }
            historical_accuracy["multi_window"] = multi_window
            # 30天数据保持向后兼容
            d30 = multi_window.get("30d", {})
            historical_accuracy["signal_accuracy"] = d30.get("signal")
            historical_accuracy["advice_accuracy"] = d30.get("advice")
            historical_accuracy["gate_accuracy"] = d30.get("gate")
    except Exception as e:
        logger.warning("[Scheduler] [validation-A] 获取历史准确率失败(首次运行正常): %s", e)

    # 5. 逐基金处理
    success = 0
    fail = 0
    for user_id, udata in user_funds.items():
        total_assets = udata["total_mv"] + udata.get("cash_amount", 0.0)

        for finfo in udata["funds"]:
            fund_code = finfo["fund_code"]
            try:
                # 5a. 获取最新gszzl（不读Redis缓存，避免TTL竞态）
                gszzl = await get_fund_realtime_nav(fund_code)
                gszzl_source = "fundgz" if gszzl is not None else "unavailable"

                # 5b. 从Redis读元数据（5天递减 fallback）
                meta = None
                meta_date_used = None
                for offset in range(5):
                    check_date = (today - timedelta(days=offset)).isoformat()
                    meta_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{check_date}:meta:{fund_code}"
                    meta = await cache_get(meta_key)
                    if meta:
                        meta_date_used = check_date
                        break
                if not meta:
                    logger.warning("[Scheduler] [validation-A] %s 元数据缺失，跳过", fund_code)
                    fail += 1
                    continue

                # 5c. 获取昨日收盘数据
                snap = yesterday_snapshots.get(fund_code)
                has_snapshot = snap is not None
                if snap:
                    yesterday_score = float(snap.composite_score or 50.0)
                    yesterday_signal = snap.signal_level or "B"
                    yesterday_confidence = snap.confidence_stars or 3
                    # Fix E: 昨日实际持仓近似。DailySignalSnapshot 仅存 target_position_pct
                    # (建议目标仓位)，无"实际持仓"字段；UserPortfolio 也无逐日持仓历史。
                    # 故用今日实际持仓(market_value/total_assets，盘中14:45已反映昨日
                    # 建议执行后的仓位)近似昨日实际持仓，避免把"建议目标0%"误当真实仓位。
                    yesterday_position = (finfo["market_value"] / total_assets) if total_assets > 0 else 0.0
                    # Fix A: 优先从 fund_nav 表直接取最新净值，避免快照 nav 滞后1天
                    yesterday_nav = latest_nav_map.get(fund_code)
                    if yesterday_nav is None:
                        # fallback: 快照中的 nav（可能滞后但总比 None 好）
                        yesterday_nav = float(snap.nav) if snap.nav else None
                    yesterday_track_type = snap.track_type or ""
                else:
                    sector_code = meta.get("sector_code")
                    if sector_code and str(sector_code).startswith("801"):
                        # Fix #6: 读 aggregate key, 从 sectors 列表提取
                        sector_cache = await cache_get("v5:sector:sentiment")
                        if isinstance(sector_cache, dict):
                            sectors_list = sector_cache.get("data", {}).get("sectors", [])
                            matched = None
                            for sec in sectors_list:
                                if str(sec.get("sector_code", "")) == sector_code:
                                    matched = sec
                                    break
                            if matched:
                                yesterday_score = float(matched.get("sentiment_score", 50.0))
                                yesterday_signal = matched.get("signal_level", "B")
                            else:
                                yesterday_score = 50.0
                                yesterday_signal = "B"
                        else:
                            yesterday_score = 50.0
                            yesterday_signal = "B"
                    else:
                        broad_cache = await cache_get(f"fsa:sentiment:{fund_code}")
                        if isinstance(broad_cache, dict):
                            yesterday_score = float(broad_cache.get("score", 50.0))
                            yesterday_signal = broad_cache.get("signal", "B")
                        else:
                            yesterday_score = 50.0
                            yesterday_signal = "B"
                    yesterday_confidence = 3
                    yesterday_position = 0.0
                    # Fix A: 无快照时也尝试从 fund_nav 取最新净值
                    yesterday_nav = latest_nav_map.get(fund_code)
                    yesterday_track_type = ""

                meta["yesterday_score"] = yesterday_score
                meta["yesterday_signal"] = yesterday_signal

                # 5d. 弹性系数推算
                if gszzl is not None:
                    elasticity = _calculate_elasticity(fund_code, gszzl, meta)
                    score_delta = gszzl * elasticity
                    score_delta = max(-settings.INTRADAY_PREVIEW_SCORE_DELTA_CLAMP,
                                      min(settings.INTRADAY_PREVIEW_SCORE_DELTA_CLAMP, score_delta))
                    preview_score = yesterday_score + score_delta
                    preview_score = max(0, min(100, preview_score))
                    preview_signal = _score_to_signal(preview_score, list(settings.V5_SIGNAL_BOUNDARIES))
                else:
                    preview_score = yesterday_score
                    preview_signal = yesterday_signal or "B"
                    elasticity = None
                    score_delta = None

                # 5e. 14:50 = 尾盘 → 置信度3星，无折减
                preview_confidence = 3
                effective_stars = yesterday_confidence

                # 5f. 当前仓位百分比
                current_pct = finfo["market_value"] / total_assets if total_assets > 0 else 0.0

                # 5g. 调用 PositionEngineV5
                async with AsyncSession(engine) as session:
                    pos_engine = PositionEngineV5(session)
                    preview_result = await pos_engine.calculate(
                        user_id=user_id,
                        fund_code=fund_code,
                        current_position_pct=current_pct,
                        signal_level=preview_signal,
                        confidence_stars=effective_stars,
                        regime=meta.get("regime", "sideways"),
                        cash_amount=udata.get("cash_amount", 0.0),
                        total_assets=total_assets,
                    )

                # 5h. 异常提示 + 综合解读
                anomaly_notes = _build_anomaly_notes(
                    gszzl=gszzl,
                    gszzl_source=gszzl_source,
                    elasticity=elasticity,
                    score_delta=score_delta,
                    preview_signal=preview_signal,
                    yesterday_signal=yesterday_signal,
                    meta_date_used=meta_date_used,
                    today_str=today_str,
                    has_snapshot=has_snapshot,
                    preview_result=preview_result,
                )
                preview_summary = _build_preview_summary(
                    preview_confidence=preview_confidence,
                    gszzl=gszzl,
                    gszzl_source=gszzl_source,
                    preview_score=round(preview_score, 2),
                    yesterday_score=yesterday_score,
                    score_delta=round(score_delta, 2) if score_delta is not None else None,
                    preview_signal=preview_signal,
                    yesterday_signal=yesterday_signal,
                    effective_stars=effective_stars,
                    yesterday_confidence=yesterday_confidence,
                    preview_result=preview_result,
                    anomaly_notes=anomaly_notes,
                )

                # 5i. 从Redis读盘中高低点
                hl_key = f"{settings.VALIDATION_INTRADAY_HL_PREFIX}:{today_str}:{fund_code}"
                hl_data = await cache_get(hl_key)
                intraday_high_gszzl = None
                intraday_low_gszzl = None
                if hl_data and isinstance(hl_data, dict):
                    intraday_high_gszzl = float(hl_data["high"]) if hl_data.get("high") is not None else None
                    intraday_low_gszzl = float(hl_data["low"]) if hl_data.get("low") is not None else None

                # 5j. 板块涨跌幅 — 优先东财实时，降级 Redis 缓存
                # 修复: 原从 Redis v5:sector:sentiment 读 sector_return，存在双重滞后
                #       (15:45评分时akshare当天数据未出→用前日收盘→次日14:45读到的是T-2数据)。
                #       改为东财 web API 实时获取(与大盘同口径)，Redis 作为降级。
                sector_code = meta.get("sector_code") or ""
                sector_name = meta.get("sector_name") or SW_CODE_TO_NAME.get(sector_code, "")
                sector_chg_pct = None
                if sector_code:
                    # 优先: 东财实时板块涨跌幅（盘中实时，与大盘同口径）
                    if sector_name and sector_name in realtime_sector_changes:
                        sector_chg_pct = realtime_sector_changes[sector_name]
                    # 降级: Redis v5:sector:sentiment 缓存
                    if sector_chg_pct is None:
                        try:
                            sector_cache = await cache_get("v5:sector:sentiment")
                            if sector_cache:
                                sectors_list = (
                                    sector_cache.get("data", {}).get("sectors", [])
                                    if isinstance(sector_cache, dict)
                                    else []
                                )
                                for sec in sectors_list:
                                    if str(sec.get("sector_code", "")) == str(sector_code):
                                        if not sector_name:
                                            sector_name = sec.get("sector_name", "") or ""
                                        ret = sec.get("sector_return")
                                        if ret is not None:
                                            sector_chg_pct = float(ret)
                                        break
                        except Exception:
                            pass

                # 5k. 持仓盈亏
                cost_basis = finfo["cost_nav"] if finfo["cost_nav"] > 0 else None
                holding_shares = finfo["holding_shares"]
                holding_market_value = finfo["market_value"]

                unrealized_pnl_pct = None
                if cost_basis and cost_basis > 0 and gszzl is not None and yesterday_nav and yesterday_nav > 0:
                    estimated_nav = yesterday_nav * (1 + gszzl / 100)
                    unrealized_pnl_pct = (estimated_nav - cost_basis) / cost_basis * 100

                holding_days = None
                if finfo["buy_date"]:
                    holding_days = (today - finfo["buy_date"]).days

                # 5l. 连续信号天数
                consecutive_signal_days = 1
                try:
                    async with AsyncSession(engine) as session:
                        consec_stmt = select(
                            StrategyValidationLog.preview_signal
                        ).where(
                            StrategyValidationLog.fund_code == fund_code,
                            StrategyValidationLog.trade_date < today,
                        ).order_by(StrategyValidationLog.trade_date.desc()).limit(30)
                        consec_result = await session.execute(consec_stmt)
                        for (sig,) in consec_result:
                            if sig == preview_signal:
                                consecutive_signal_days += 1
                            else:
                                break
                except Exception:
                    pass

                # 5m. 场景状态判定
                gates = preview_result.get("gates") or {}
                gate_1 = gates.get("gate_1") or {}
                gate_2 = gates.get("gate_2") or {}
                gate_e = gates.get("gate_e") or {}
                _gate_1_triggered = gate_1.get("triggered", False)
                _gate_2_triggered = gate_2.get("triggered", False)
                _gate_e_triggered = gate_e.get("triggered", False)
                _has_danger = any(n["level"] == "danger" for n in anomaly_notes)
                _has_warning = any(n["level"] in ("warning", "danger") for n in anomaly_notes)

                if _gate_1_triggered or _gate_2_triggered or preview_result.get("action") == "decrease":
                    overall_status = "stop_loss"
                elif _has_warning or (gszzl is not None and abs(gszzl) > 3.0):
                    overall_status = "warning"
                else:
                    overall_status = "normal"

                # 5n. 系统建议文本
                preview_output_for_advice = {
                    "gszzl": gszzl,
                    "gszzl_source": gszzl_source,
                    "preview_score": round(preview_score, 2),
                    "yesterday_score": yesterday_score,
                    "score_delta": round(score_delta, 2) if score_delta is not None else None,
                    "signal_level": preview_signal,
                    "yesterday_signal": yesterday_signal,
                    "confidence_stars": effective_stars,
                    "current_position_pct": current_pct,
                    "target_position_pct": preview_result.get("target_position_pct", 0),
                    "action": preview_result.get("action", "hold"),
                    "gates": gates,
                    "overall_status": overall_status,
                    "frequency_block_direction": preview_result.get("frequency_block_direction"),
                }
                system_advice_text = _build_system_advice_text(
                    preview_output=preview_output_for_advice,
                    market_index_chg_pct=market_index_chg_pct,
                    sector_chg_pct=sector_chg_pct,
                    cost_basis=cost_basis,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    holding_days=holding_days,
                    historical_accuracy=historical_accuracy,
                )

                # 5o. anomaly_flags JSON
                anomaly_flags = [
                    {"type": n["type"], "level": n["level"], "message": n["message"]}
                    for n in anomaly_notes
                ] if anomaly_notes else []

                # 5p. Gate距离
                gate_1_distance_pct = gate_1.get("current_distance_pct")
                gate_2_distance_pct = gate_2.get("current_distance_pct")
                gate_e_distance_pct = gate_e.get("current_distance_pct")

                # 5q. Upsert到 strategy_validation_log
                async with AsyncSession(engine) as session:
                    existing_stmt = select(StrategyValidationLog).where(
                        StrategyValidationLog.fund_code == fund_code,
                        StrategyValidationLog.trade_date == today,
                        StrategyValidationLog.user_id == user_id,
                    )
                    existing_result = await session.execute(existing_stmt)
                    existing_record = existing_result.scalar_one_or_none()

                    if existing_record:
                        existing_record.fund_name = finfo["fund_name"] or existing_record.fund_name
                        existing_record.sector_code = sector_code or existing_record.sector_code
                        existing_record.sector_name = sector_name or existing_record.sector_name
                        existing_record.yesterday_signal = yesterday_signal
                        existing_record.yesterday_confidence = yesterday_confidence
                        existing_record.yesterday_score = yesterday_score
                        existing_record.yesterday_position = yesterday_position
                        existing_record.yesterday_nav = yesterday_nav
                        existing_record.yesterday_track_type = yesterday_track_type
                        existing_record.preview_score = round(preview_score, 2)
                        existing_record.preview_signal = preview_signal
                        existing_record.preview_confidence = preview_confidence
                        existing_record.gszzl = gszzl
                        existing_record.gszzl_source = gszzl_source
                        existing_record.elasticity = round(elasticity, 2) if elasticity is not None else None
                        existing_record.score_delta = round(score_delta, 2) if score_delta is not None else None
                        existing_record.effective_stars = effective_stars
                        existing_record.intraday_high_gszzl = round(intraday_high_gszzl, 2) if intraday_high_gszzl is not None else None
                        existing_record.intraday_low_gszzl = round(intraday_low_gszzl, 2) if intraday_low_gszzl is not None else None
                        existing_record.preview_summary = preview_summary
                        existing_record.anomaly_flags = anomaly_flags
                        existing_record.market_index_chg_pct = market_index_chg_pct
                        existing_record.sector_chg_pct = sector_chg_pct
                        existing_record.cost_basis = cost_basis
                        existing_record.unrealized_pnl_pct = round(unrealized_pnl_pct, 2) if unrealized_pnl_pct is not None else None
                        existing_record.holding_shares = holding_shares
                        existing_record.holding_market_value = holding_market_value
                        existing_record.gate_1_triggered = 1 if _gate_1_triggered else 0
                        existing_record.gate_2_triggered = 1 if _gate_2_triggered else 0
                        existing_record.gate_e_triggered = 1 if _gate_e_triggered else 0
                        existing_record.gate_1_distance_pct = round(gate_1_distance_pct, 2) if gate_1_distance_pct is not None else None
                        existing_record.gate_2_distance_pct = round(gate_2_distance_pct, 2) if gate_2_distance_pct is not None else None
                        existing_record.gate_e_distance_pct = round(gate_e_distance_pct, 2) if gate_e_distance_pct is not None else None
                        existing_record.frequency_block_direction = preview_result.get("frequency_block_direction")
                        existing_record.overall_status = overall_status
                        existing_record.system_advice_text = system_advice_text
                        existing_record.system_advice_action = preview_result.get("action", "hold")
                        existing_record.advice_reason = preview_result.get("reason", "")
                        existing_record.consecutive_signal_days = consecutive_signal_days
                    else:
                        new_record = StrategyValidationLog(
                            trade_date=today,
                            fund_code=fund_code,
                            fund_name=finfo["fund_name"] or None,
                            sector_code=sector_code or None,
                            sector_name=sector_name or None,
                            user_id=user_id,
                            yesterday_signal=yesterday_signal,
                            yesterday_confidence=yesterday_confidence,
                            yesterday_score=yesterday_score,
                            yesterday_position=yesterday_position,
                            yesterday_nav=yesterday_nav,
                            yesterday_track_type=yesterday_track_type,
                            preview_score=round(preview_score, 2),
                            preview_signal=preview_signal,
                            preview_confidence=preview_confidence,
                            gszzl=gszzl,
                            gszzl_source=gszzl_source,
                            elasticity=round(elasticity, 2) if elasticity is not None else None,
                            score_delta=round(score_delta, 2) if score_delta is not None else None,
                            effective_stars=effective_stars,
                            intraday_high_gszzl=round(intraday_high_gszzl, 2) if intraday_high_gszzl is not None else None,
                            intraday_low_gszzl=round(intraday_low_gszzl, 2) if intraday_low_gszzl is not None else None,
                            preview_summary=preview_summary,
                            anomaly_flags=anomaly_flags,
                            market_index_chg_pct=market_index_chg_pct,
                            sector_chg_pct=sector_chg_pct,
                            cost_basis=cost_basis,
                            unrealized_pnl_pct=round(unrealized_pnl_pct, 2) if unrealized_pnl_pct is not None else None,
                            holding_shares=holding_shares,
                            holding_market_value=holding_market_value,
                            gate_1_triggered=1 if _gate_1_triggered else 0,
                            gate_2_triggered=1 if _gate_2_triggered else 0,
                            gate_e_triggered=1 if _gate_e_triggered else 0,
                            gate_1_distance_pct=round(gate_1_distance_pct, 2) if gate_1_distance_pct is not None else None,
                            gate_2_distance_pct=round(gate_2_distance_pct, 2) if gate_2_distance_pct is not None else None,
                            gate_e_distance_pct=round(gate_e_distance_pct, 2) if gate_e_distance_pct is not None else None,
                            frequency_block_direction=preview_result.get("frequency_block_direction"),
                            overall_status=overall_status,
                            system_advice_text=system_advice_text,
                            system_advice_action=preview_result.get("action", "hold"),
                            advice_reason=preview_result.get("reason", ""),
                            consecutive_signal_days=consecutive_signal_days,
                        )
                        session.add(new_record)

                    await session.commit()

                success += 1
                logger.info("[Scheduler] [validation-A] %s: score=%.1f signal=%s gszzl=%.2f status=%s",
                           fund_code, preview_score, preview_signal, gszzl or 0, overall_status)
            except Exception as e:
                fail += 1
                logger.error("[Scheduler] [validation-A] %s FAIL: %s", fund_code, e)

    logger.info("[Scheduler] [validation-A] 预演持久化完成 -- %d 成功, %d 失败", success, fail)



# ============================================================
# 策略验证分析表 — 任务C: 14:52 DeepSeek AI建议
# ============================================================
async def _run_validation_deepseek_advice() -> None:
    """
    策略验证-任务C: 14:52 DeepSeek AI建议生成

    依赖任务A(14:50)已将system_advice_text写入DB。
    对每条当日记录调用DeepSeek API生成AI建议。
    故障降级: 10s超时+1次重试→静默跳过(G8留NULL)。
    """
    import httpx
    from app.core.database import get_async_engine
    from sqlalchemy import select, func as sa_func
    from app.models.strategy_validation_log import StrategyValidationLog
    from app.models.daily_signal_snapshot import DailySignalSnapshot
    from app.models.user_portfolio import UserPortfolio
    from app.models.user_cash import UserCash

    if not await _is_trade_day():
        logger.info("[Scheduler] [validation-C] 非交易日，跳过")
        return

    if not settings.DEEPSEEK_API_KEY:
        logger.info("[Scheduler] [validation-C] DEEPSEEK_API_KEY 未配置，跳过AI建议")
        return

    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    engine = get_async_engine()

    # 获取大盘/板块涨跌数据 (解耦后需自行获取，不再依赖validation-A DB记录)
    # Fix #8: 东财push2从ECS TLS层被封锁→改用腾讯行情API(T-0实时)+get_index_data(T-1兜底)
    market_index_chg_pct = await _fetch_realtime_market_chg_pct()

    try:
        # 板块涨跌幅 (使用同花顺接口)
        sector_data = await _fetch_realtime_sector_changes()
        if sector_data and isinstance(sector_data, dict) and len(sector_data) > 0:
            # Fix #7: 获取全行业数据, per-fund循环中按基金sector提取
            logger.info("[Scheduler] [validation-C] 板块数据获取成功: %d个行业", len(sector_data))
        else:
            sector_data = {}
    except Exception as _e:
        logger.warning("[Scheduler] [validation-C] 板块数据获取失败: %s", _e)
        sector_data = {}

    # 1. 获取基金/用户列表 + 从Redis读取预演数据 (解耦: 不依赖validation-A的DB记录)
    from app.core.redis_client import cache_get, cache_set
    today_str = today.strftime("%Y-%m-%d")

    async with AsyncSession(engine) as session:
        # 获取所有活跃持仓
        portfolio_stmt = select(UserPortfolio)
        portfolio_result = await session.execute(portfolio_stmt)
        portfolios = portfolio_result.scalars().all()

    # 按基金+用户分组
    fund_user_pairs = {}  # {(fund_code, user_id): UserPortfolio}
    for p in portfolios:
        key = (p.fund_code, p.user_id)
        fund_user_pairs[key] = p

    # 构建任务列表: 读Redis预演数据 + 查已有DB记录(用于UPDATE或INSERT)
    tasks = []  # [(fund_code, user_id, preview_data, hl_data, series_data, existing_record)]
    async with AsyncSession(engine) as session:
        for (fund_code, user_id), portfolio in fund_user_pairs.items():
            # 读取Redis预演数据
            cache_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:{fund_code}:{user_id}"
            preview_data = await cache_get(cache_key)
            if not preview_data:
                continue  # 无预演数据，跳过

            # 读取盘中高低点
            hl_key = f"{settings.VALIDATION_INTRADAY_HL_PREFIX}:{today_str}:{fund_code}"
            hl_data = await cache_get(hl_key)

            # 读取序列数据(形态特征)
            series_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:series:{today_str}:{fund_code}:{user_id}"
            series_data = await cache_get(series_key)

            # 查找已有DB记录
            existing_stmt = select(StrategyValidationLog).where(
                StrategyValidationLog.trade_date == today,
                StrategyValidationLog.fund_code == fund_code,
                StrategyValidationLog.user_id == user_id,
            )
            existing_result = await session.execute(existing_stmt)
            existing_record = existing_result.scalar_one_or_none()

            tasks.append((fund_code, user_id, preview_data, hl_data, series_data, existing_record, portfolio))

    if not tasks:
        logger.info("[Scheduler] [validation-C] 无预演数据/无持仓，跳过")
        return

    # 2. 获取历史准确率（多窗口: 30/60/90天，供提示词使用）
    historical_accuracy: dict = {"signal_accuracy": None, "advice_accuracy": None, "gate_accuracy": None, "deepseek_accuracy": None, "ds_count": 0, "multi_window": {}}
    try:
        async with AsyncSession(engine) as session:
            multi_window = {}
            for window_days in (30, 60, 90):
                window_ago = today - timedelta(days=window_days)
                w_stmt = select(
                    sa_func.avg(StrategyValidationLog.signal_accuracy),
                    sa_func.avg(StrategyValidationLog.advice_accuracy),
                    sa_func.avg(StrategyValidationLog.gate_accuracy),
                    sa_func.avg(StrategyValidationLog.deepseek_advice_correct),
                    sa_func.count(StrategyValidationLog.deepseek_advice_correct),
                ).where(
                    StrategyValidationLog.trade_date >= window_ago,
                    StrategyValidationLog.trade_date < today,
                )
                w_result = await session.execute(w_stmt)
                w_row = w_result.one_or_none()
                key = f"{window_days}d"
                multi_window[key] = {
                    "signal": round(float(w_row[0]), 2) if w_row and w_row[0] is not None else None,
                    "advice": round(float(w_row[1]), 2) if w_row and w_row[1] is not None else None,
                    "gate": round(float(w_row[2]), 2) if w_row and w_row[2] is not None else None,
                    "deepseek": round(float(w_row[3]), 2) if w_row and w_row[3] is not None else None,
                    "ds_count": int(w_row[4]) if w_row and w_row[4] is not None else 0,
                }
            historical_accuracy["multi_window"] = multi_window
            # 30天数据保持向后兼容
            d30 = multi_window.get("30d", {})
            historical_accuracy["signal_accuracy"] = d30.get("signal")
            historical_accuracy["advice_accuracy"] = d30.get("advice")
            historical_accuracy["gate_accuracy"] = d30.get("gate")
            historical_accuracy["deepseek_accuracy"] = d30.get("deepseek")
            historical_accuracy["ds_count"] = d30.get("ds_count", 0)
    except Exception as e:
        logger.debug("[Scheduler] [validation-C] 获取历史准确率失败(首次运行正常): %s", e)

    success = 0
    fail = 0
    skipped = 0

    for fund_code, user_id, preview_data, hl_data, series_data, existing_record, portfolio in tasks:
        try:
            # 2a. 全unavailable→跳过
            gszzl_source = preview_data.get("gszzl_source", "unavailable")
            if gszzl_source == "unavailable":
                skipped += 1
                logger.info("[Scheduler] [validation-C] %s 估值不可用，跳过AI调用", fund_code)
                continue

            # 2b. 组装提示词
            # Phase 1: 规则5/Q4/step1 根据模式区分
            _is_independent = settings.DEEPSEEK_MODE == "independent"
            _rule5_dir = ("可参考系统建议，也可给出你的独立判断"
                          if _is_independent
                          else "【必须】等于用户输入中的'系统仓位引擎建议方向'")
            _step1_text = ("参考'系统已推导的仓位与金额'区块，给出你的首行结论"
                           if _is_independent
                           else "原样复述'系统已推导的仓位与金额'区块首行")
            _q4_text = ("请给出你的独立操作方向判断（加仓/持有/减仓），并说明依据。如与系统建议不同，请解释分歧原因。"
                        if _is_independent
                        else "请分析系统建议方向（加仓/持有/减仓）的合理性依据，结合预演数据说明为何此方向是恰当的。")
            system_prompt = (
                "你是基金投资策略分析师。基于系统预演数据给出尾盘建议。\n"
                "规则：\n"
                "1. 闸门触发 > 置信度 > 信号等级（优先级从高到低）\n"
                "2. Gate-1/Gate-2触发时必须明确提示减仓风险\n"
                "3. 建议方向只能是：加仓/持有/减仓\n"
                "4. 回复控制在500-2000字，必须包含明确的操作方向\n"
                "5. 【强制首行格式】回复第1行必须严格为：\n"
                "   【操作方向】{加仓/持有/减仓} | 当前市值¥X | 目标仓位Y% | 建议金额≈¥Z\n"
                f"   其中操作方向{_rule5_dir}；"
                "X/Y/Z【必须】等于'系统已推导的仓位与金额'区块中的数值"
                "（金额由系统计算，禁止自编、禁止改动任何数字）。\n"
                "6. '5问策略分析'仅作为首行之后的补充内容，不得覆盖首行结构化结论。\n"
                "7. 【全文方向一致性】正文分析中不得出现与首行矛盾的方向词。"
                "例如首行是'持有'，正文不得出现'建议减仓''应加仓'等相反表述；"
                "分析应围绕首行方向的合理性展开。\n"
                "8. 【偏差提示】如确有必要提示系统方向可能存在偏差，"
                "仅可在正文末尾以'【偏差提示】'开头的独立段落补充说明，"
                "该段落不得使用与首行相反的方向词作为建议，仅做风险提示。\n"
            )

            # P0+P1+P2: 历史数据补充查询
            nav_history_data = []
            signal_history_data = []
            market_sentiment_data = []
            sector_sentiment_data = []
            try:
                from app.models.fund_nav import FundNav
                async with AsyncSession(engine) as s:
                    # P0-1: 净值走势 (近10个交易日)
                    nav_stmt = select(
                        FundNav.nav_date, FundNav.nav, FundNav.daily_return
                    ).where(
                        FundNav.fund_code == fund_code,
                        FundNav.nav_date < today,
                    ).order_by(FundNav.nav_date.desc()).limit(10)
                    nav_rows = (await s.execute(nav_stmt)).all()
                    nav_history_data = [(r[0], r[1], r[2]) for r in nav_rows]

                    # P0-2: 信号趋势 (近10个交易日)
                    sig_stmt = select(
                        DailySignalSnapshot.snapshot_date,
                        DailySignalSnapshot.composite_score,
                        DailySignalSnapshot.signal_level,
                        DailySignalSnapshot.action_advice,
                        DailySignalSnapshot.regime,
                        DailySignalSnapshot.drawdown_pct,
                        DailySignalSnapshot.macd_state,
                    ).where(
                        DailySignalSnapshot.target_code == fund_code,
                        DailySignalSnapshot.snapshot_date < today,
                    ).order_by(DailySignalSnapshot.snapshot_date.desc()).limit(10)
                    sig_rows = (await s.execute(sig_stmt)).all()
                    signal_history_data = list(sig_rows)

                    # P1-1: 大盘情绪 (000300.SH 近5天)
                    mkt_stmt = select(
                        DailySignalSnapshot.snapshot_date,
                        DailySignalSnapshot.composite_score,
                        DailySignalSnapshot.signal_level,
                        DailySignalSnapshot.action_advice,
                        DailySignalSnapshot.regime,
                    ).where(
                        DailySignalSnapshot.target_code == "000300.SH",
                        DailySignalSnapshot.snapshot_date < today,
                    ).order_by(DailySignalSnapshot.snapshot_date.desc()).limit(5)
                    mkt_rows = (await s.execute(mkt_stmt)).all()
                    market_sentiment_data = list(mkt_rows)

                    # P1-2: 板块情绪 (sector_code 近5天)
                    if preview_data.get("sector_code", ""):
                        sec_stmt = select(
                            DailySignalSnapshot.snapshot_date,
                            DailySignalSnapshot.composite_score,
                            DailySignalSnapshot.signal_level,
                            DailySignalSnapshot.action_advice,
                        ).where(
                            DailySignalSnapshot.target_code == preview_data.get("sector_code", ""),
                            DailySignalSnapshot.target_type == "sector",
                            DailySignalSnapshot.snapshot_date < today,
                        ).order_by(DailySignalSnapshot.snapshot_date.desc()).limit(5)
                        sec_rows = (await s.execute(sec_stmt)).all()
                        sector_sentiment_data = list(sec_rows)
            except Exception as _e:
                logger.warning("[Scheduler] [validation-C] %s 历史数据查询失败，降级为空: %s", fund_code, _e)

            user_parts = []

            # 段1: 今日预演数据 (从Redis预演数据读取，不再依赖DB record)
            gszzl_val = preview_data.get("gszzl")
            gszzl_str = f"{gszzl_val:+.2f}%" if gszzl_val is not None else "不可用"
            preview_score_val = preview_data.get("preview_score", 0)
            preview_signal_val = preview_data.get("signal_level", "D")
            preview_confidence_val = preview_data.get("confidence_stars", 0)
            elasticity_val = preview_data.get("elasticity", 0)
            score_delta_val = preview_data.get("score_delta", 0)
            overall_status_val = preview_data.get("overall_status", "normal")
            # Gate数据
            gates_data = preview_data.get("gates") or {}
            gate_1_triggered = gates_data.get("gate_1_triggered", False)
            gate_1_distance = gates_data.get("gate_1_distance_pct")
            gate_2_triggered = gates_data.get("gate_2_triggered", False)
            gate_2_distance = gates_data.get("gate_2_distance_pct")
            gate_1_str = "已触发" if gate_1_triggered else f"距触发{gate_1_distance:+.1f}%" if gate_1_distance is not None else "未知"
            gate_2_str = "已触发" if gate_2_triggered else f"距触发{gate_2_distance:+.1f}%" if gate_2_distance is not None else "未知"
            # 日内高低点 (从hl_key读取)
            intraday_high = hl_data.get("high") if hl_data and isinstance(hl_data, dict) else preview_data.get("intraday_high_gszzl")
            intraday_low = hl_data.get("low") if hl_data and isinstance(hl_data, dict) else preview_data.get("intraday_low_gszzl")
            intraday_range = round(intraday_high - intraday_low, 2) if intraday_high is not None and intraday_low is not None else 0
            user_parts.append(
                f"【今日预演数据】\n"
                f"基金代码: {fund_code}\n"
                f"基金名称: {portfolio.fund_name if portfolio else '未知'}\n"
                f"盘中估值: {gszzl_str}\n"
                f"预演情绪分: {preview_score_val}\n"
                f"预演信号: {preview_signal_val}\n"
                f"置信度: {preview_confidence_val}星(尾盘)\n"
                f"弹性系数: {elasticity_val}\n"
                f"情绪分变化: {score_delta_val}\n"
                f"Gate-1: {gate_1_str}\n"
                f"Gate-2: {gate_2_str}\n"
                f"总状态: {overall_status_val}\n"
                f"日内高低点: {intraday_high}% / {intraday_low}% (振幅{intraday_range}%)\n"
            )
            # 段1.5: P0 净值走势 (近10个交易日)
            if nav_history_data:
                nav_lines = []
                for nd, nv, dr in reversed(nav_history_data):
                    dr_str = f"{dr:+.2f}%" if dr is not None else "N/A"
                    nav_lines.append(f"  {nd} | 净值 {nv:.4f} | 日涨跌 {dr_str}")
                navs = [nv for _, nv, _ in nav_history_data]
                dd_str = ""
                if navs:
                    peak = max(navs)
                    trough = min(navs)
                    drawdown = (trough - peak) / peak * 100 if peak > 0 else 0
                    dd_str = f"\n  近10日最大回撤: {drawdown:.2f}% (峰值{peak:.4f} -> 谷值{trough:.4f})"
                user_parts.append(
                    "【近10日净值走势】\n"
                    + "\n".join(nav_lines)
                    + dd_str
                )
            else:
                user_parts.append("【近10日净值走势】暂无历史净值数据")

            # 段1.6: P0 信号趋势 (近10个交易日)
            if signal_history_data:
                sig_lines = []
                _aa_map = {"increase": "加仓", "hold": "持有", "decrease": "减仓"}
                for row in reversed(signal_history_data):
                    sd, sc, sl, aa, rg, dd, ms = row
                    sc_str = f"{sc:.1f}" if sc is not None else "N/A"
                    aa_str = _aa_map.get(aa, aa or "N/A")
                    rg_str = rg or "N/A"
                    ms_str = ms or "N/A"
                    dd_str = f"{dd:.2f}%" if dd is not None else "N/A"
                    sig_lines.append(f"  {sd} | 信号 {sl or 'N/A'} | 情绪分 {sc_str} | 操作 {aa_str} | 回撤 {dd_str} | MACD {ms_str} | 体制 {rg_str}")
                user_parts.append(
                    "【近10日信号趋势】\n"
                    + "\n".join(sig_lines)
                )
            else:
                user_parts.append("【近10日信号趋势】暂无历史信号数据")


            # 段2: 大盘/板块/持仓
            mkt_str = f"{market_index_chg_pct:+.2f}%" if market_index_chg_pct is not None else "不可用"
            # Fix #7: per-fund板块涨跌幅, 不是31行业平均
            fund_sector_code = preview_data.get("sector_code") or ""
            fund_sector_name = SW_CODE_TO_NAME.get(fund_sector_code, "") if fund_sector_code else ""
            fund_sector_chg = sector_data.get(fund_sector_name) if fund_sector_name and sector_data else None
            if fund_sector_chg is not None:
                sec_str = f"{fund_sector_chg:+.2f}% ({fund_sector_name})"
            elif sector_data:
                chgs = list(sector_data.values())
                avg_chg = round(sum(chgs) / len(chgs), 2) if chgs else None
                sec_str = f"{avg_chg:+.2f}% (全行业平均)" if avg_chg is not None else "不可用"
            else:
                sec_str = "不可用"
            unrealized_pnl_pct_val = preview_data.get("unrealized_pnl_pct")
            pnl_str = f"{unrealized_pnl_pct_val:+.1f}%" if unrealized_pnl_pct_val is not None else "不可用"
            cost_basis_val = portfolio.cost_nav if portfolio else None
            user_parts.append(
                f"【市场上下文】\n"
                f"大盘涨跌幅: {mkt_str}\n"
                f"板块涨跌幅: {sec_str}\n"
                f"浮盈亏: {pnl_str}\n"
                f"成本净值: {cost_basis_val}\n"
            )
            # 段2.5: P1 大盘情绪 (近5个交易日)
            if market_sentiment_data:
                mkt_lines = []
                _aa_map = {"increase": "加仓", "hold": "持有", "decrease": "减仓"}
                for row in reversed(market_sentiment_data):
                    sd, sc, sl, aa, rg = row
                    sc_str = f"{sc:.1f}" if sc is not None else "N/A"
                    aa_str = _aa_map.get(aa, aa or "N/A")
                    mkt_lines.append(f"  {sd} | 情绪分 {sc_str} | 信号 {sl or 'N/A'} | 操作 {aa_str} | 体制 {rg or 'N/A'}")
                user_parts.append(
                    "【近5日大盘情绪(沪深300)】\n"
                    + "\n".join(mkt_lines)
                )
            else:
                user_parts.append("【近5日大盘情绪(沪深300)】暂无数据")

            # 段2.6: P1 板块情绪 (近5个交易日)
            if sector_sentiment_data:
                sec_lines = []
                _aa_map = {"increase": "加仓", "hold": "持有", "decrease": "减仓"}
                for row in reversed(sector_sentiment_data):
                    sd, sc, sl, aa = row
                    sc_str = f"{sc:.1f}" if sc is not None else "N/A"
                    aa_str = _aa_map.get(aa, aa or "N/A")
                    sec_lines.append(f"  {sd} | 情绪分 {sc_str} | 信号 {sl or 'N/A'} | 操作 {aa_str}")
                sec_name = fund_sector_name or preview_data.get("sector_code", "") or "N/A"
                user_parts.append(
                    f"【近5日板块情绪({sec_name})】\n"
                    + "\n".join(sec_lines)
                )
            else:
                user_parts.append("【近5日板块情绪】暂无数据")


            # 段3: 历史回验 — 多窗口准确率(30/60/90天)
            def _fmt_pct_v(v):
                return f"{v*100:.0f}%" if v is not None else "--"

            mw = historical_accuracy.get("multi_window", {})
            if mw and any(mw.get(w, {}).get(k) is not None for w in ("30d", "60d", "90d") for k in ("signal", "advice", "gate", "deepseek")):
                # 单行紧凑格式: 准确率趋势(以近30天为主): 信号[30d=72%, 60d=78%, 90d=--] 建议[...] Gate[...] AI[...](n=9)
                sig_p = ", ".join(f"{w}={_fmt_pct_v(mw.get(w, {}).get('signal'))}" for w in ("30d", "60d", "90d"))
                adv_p = ", ".join(f"{w}={_fmt_pct_v(mw.get(w, {}).get('advice'))}" for w in ("30d", "60d", "90d"))
                gate_p = ", ".join(f"{w}={_fmt_pct_v(mw.get(w, {}).get('gate'))}" for w in ("30d", "60d", "90d"))
                ds_p = ", ".join(f"{w}={_fmt_pct_v(mw.get(w, {}).get('deepseek'))}" for w in ("30d", "60d", "90d"))
                _ds_cnt = historical_accuracy.get("ds_count", 0)
                _cnt_str = f"(n={_ds_cnt})" if _ds_cnt else ""
                user_parts.append(f"【历史回验】准确率趋势(以近30天为主): 信号[{sig_p}] 建议[{adv_p}] Gate[{gate_p}] AI[{ds_p}]{_cnt_str}")
            else:
                user_parts.append("【历史回验】暂无历史数据")

            # 段3.1: Per-fund历史成绩单 — min_samples=10硬门槛
            try:
                async with AsyncSession(engine) as _pf_session:
                    thirty_days_ago = today - timedelta(days=30)
                    pf_stmt = select(
                        sa_func.avg(StrategyValidationLog.signal_accuracy),
                        sa_func.avg(StrategyValidationLog.advice_accuracy),
                        sa_func.avg(StrategyValidationLog.deepseek_advice_correct),
                        sa_func.count(StrategyValidationLog.deepseek_advice_correct),
                    ).where(
                        StrategyValidationLog.fund_code == fund_code,
                        StrategyValidationLog.trade_date >= thirty_days_ago,
                        StrategyValidationLog.trade_date < today,
                    )
                    pf_result = await _pf_session.execute(pf_stmt)
                    pf_row = pf_result.one_or_none()
                    if pf_row and pf_row[3] is not None and pf_row[3] >= 10:
                        pf_sig = f"{pf_row[0]*100:.0f}%" if pf_row[0] is not None else "--"
                        pf_adv = f"{pf_row[1]*100:.0f}%" if pf_row[1] is not None else "--"
                        pf_ds = f"{pf_row[2]*100:.0f}%" if pf_row[2] is not None else "--"
                        pf_n = int(pf_row[3])
                        user_parts.append(f"【本基金历史回验参考】信号{pf_sig} 建议{pf_adv} AI{pf_ds} (n={pf_n})")
            except Exception as e:
                logger.debug("[Scheduler] [validation-C] Per-fund准确率查询失败: %s", e)

            # 段3.5: P2 前日信号对比
            if preview_data.get("yesterday_signal", "N/A") or preview_data.get("yesterday_score") is not None:
                y_sig = preview_data.get("yesterday_signal", "N/A") or "N/A"
                yesterday_score_val = preview_data.get("yesterday_score")
                y_score = f"{yesterday_score_val:.1f}" if yesterday_score_val is not None else "N/A"
                t_sig = preview_signal_val
                t_score = f"{preview_score_val:.1f}" if preview_score_val is not None else "N/A"
                delta_str = f"{score_delta_val:+.1f}" if score_delta_val is not None else "N/A"
                _switched = "有变化" if y_sig != t_sig else "维持不变"
                user_parts.append(
                    f"【前日信号对比】\n"
                    f"  昨日信号: {y_sig} (情绪分 {y_score})\n"
                    f"  今日预演: {t_sig} (情绪分 {t_score})\n"
                    f"  情绪分变化: {delta_str}\n"
                    f"  信号切换: {_switched}"
                )

            # 段4: 系统建议
            # 段1.5: 盘中形态特征 (V5.4增强)
            if series_data and isinstance(series_data, list) and len(series_data) >= 5:
                features = _compute_intraday_features(series_data)
                user_parts.append(
                    f"【盘中形态特征】\n"
                    f"形态分类: {features['shape']}\n"
                    f"日内振幅: {features['am_range']}%\n"
                    f"午后斜率: {features['pm_slope']}%\n"
                    f"转折点数: {features['turn_points']}\n"
                    f"近30分钟方向: {features['last30_dir']}\n"
                )

            # 段4.5: 系统已推导金额区块（阶段1 — 金额由系统算，模型只翻译，零黑箱）
            system_action = "持有"
            target_position_pct = 0.0
            current_position_pct = 0.0
            total_assets = 0.0
            suggested_amount = 0.0
            try:
                async with AsyncSession(engine) as s:
                    # target_position_pct / action_advice 来自当日 daily_signal_snapshot
                    snap_stmt = select(DailySignalSnapshot).where(
                        DailySignalSnapshot.snapshot_date == today,
                        DailySignalSnapshot.target_code == fund_code,
                    ).order_by(DailySignalSnapshot.id.desc()).limit(1)
                    snap_res = await s.execute(snap_stmt)
                    snap_row = snap_res.scalar_one_or_none()
                    # FIX: 今天没有则 fallback 到最近一次 snapshot（14:40验证C时今天的尚未生成）
                    if snap_row is None:
                        fb_stmt = select(DailySignalSnapshot).where(
                            DailySignalSnapshot.snapshot_date < today,
                            DailySignalSnapshot.target_code == fund_code,
                        ).order_by(DailySignalSnapshot.snapshot_date.desc()).limit(1)
                        snap_row = (await s.execute(fb_stmt)).scalar_one_or_none()
                    snap_target_pct = float(snap_row.target_position_pct) if (snap_row and snap_row.target_position_pct is not None) else 0.0
                    snap_action = snap_row.action_advice if snap_row else None
                    target_position_pct = snap_target_pct

                    # 实时算总资产 = Σ(user_portfolio.market_value) + user_cash.cash_amount
                    mv_res = await s.execute(
                        select(sa_func.sum(UserPortfolio.market_value)).where(UserPortfolio.user_id == user_id)
                    )
                    total_market_value = float(mv_res.scalar() or 0.0)
                    cash_row = (await s.execute(select(UserCash).where(UserCash.user_id == user_id))).scalar_one_or_none()
                    cash_amount = float(cash_row.cash_amount) if cash_row else 0.0
                    total_assets = total_market_value + cash_amount

                    # 本基金持仓市值
                    fund_mv_res = await s.execute(
                        select(UserPortfolio.market_value).where(
                            UserPortfolio.user_id == user_id,
                            UserPortfolio.fund_code == fund_code,
                        ).limit(1)
                    )
                    fund_market_value = float(fund_mv_res.scalar() or 0.0)
                    current_position_pct = fund_market_value / total_assets if total_assets > 0 else 0.0

                # 统一真相源：解耦后使用 DailySignalSnapshot 方向（无 system_advice_action）
                _raw_action = snap_action  # 解耦后无system_advice_action，只用DailySignalSnapshot
                if _raw_action == "increase":
                    system_action = "加仓"
                elif _raw_action in ("decrease", "sell"):
                    system_action = "减仓"
                else:
                    system_action = "持有"

                # 持有时建议金额=0；否则 = |target - current| × total_assets
                suggested_amount = 0.0 if system_action == "持有" else abs(target_position_pct - current_position_pct) * total_assets
            except Exception as _e:
                logger.warning("[Scheduler] [validation-C] %s 推导金额失败，降级为空金额区块: %s", fund_code, _e)

            # 系统已推导金额区块（模型严禁修改金额，仅翻译）
            user_parts.append(
                "【系统已推导的仓位与金额（请勿修改任何数字，仅供翻译）】\n"
                f"基金代码: {fund_code}\n"
                f"当前持仓市值: ¥{current_position_pct * total_assets:.0f}  (持仓占比 {current_position_pct * 100:.1f}%)\n"
                f"目标仓位: {target_position_pct * 100:.1f}%\n"
                f"系统总资产: ¥{total_assets:.0f}\n"
                f"系统仓位引擎建议方向: {system_action}\n"
                f"系统推导建议金额: ≈¥{suggested_amount:.0f}   （= |{target_position_pct:.4f} - {current_position_pct:.4f}| × ¥{total_assets:.0f}）\n"
            )

            # 段5: 先复述首行，再做补充分析（阶段1）
            user_parts.append(
                "【请按以下结构回复】\n"
                f"第一步：{_step1_text}"
                "（操作方向 | 当前市值 | 目标仓位 | 建议金额），不得改动任何数字。\n"
                "第二步：基于预演数据做补充策略分析，回答如下问题：\n"
                "1. 弹性系数是否合理？盘中估值变化对情绪分的影响是否过大或过小？\n"
                "2. 信号等级的边界是否需要调整？当前信号与昨日信号的切换是否合理？\n"
                "3. Gate阈值（Gate-1/Gate-2）的触发距离是否合适？\n"
                f"4. {_q4_text}\n"
                "5. 预演估算与实际收盘可能存在多少偏差？\n"
            )

            user_prompt = "\n\n".join(user_parts)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            # 2c. 调用 DeepSeek API（带重试）
            api_url = f"{settings.DEEPSEEK_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            }
            body = {
                "model": settings.DEEPSEEK_MODEL,
                "messages": messages,
                "max_tokens": settings.DEEPSEEK_MAX_TOKENS,
                "temperature": settings.DEEPSEEK_TEMPERATURE,
            }

            ai_response = None
            last_err = None
            for attempt in range(settings.DEEPSEEK_MAX_RETRIES + 1):
                try:
                    async with httpx.AsyncClient(timeout=settings.DEEPSEEK_TIMEOUT) as client:
                        resp = await client.post(api_url, headers=headers, json=body)
                        resp.raise_for_status()
                        resp_data = resp.json()
                        ai_response = resp_data["choices"][0]["message"]["content"]
                        break
                except Exception as e:
                    last_err = e
                    if attempt < settings.DEEPSEEK_MAX_RETRIES:
                        logger.warning("[Scheduler] [validation-C] %s 第%d次调用失败，重试: %s", fund_code, attempt + 1, e)
                    else:
                        logger.error("[Scheduler] [validation-C] %s DeepSeek调用最终失败(降级): %s", fund_code, e)

            if ai_response is None:
                fail += 1
                # 失败可见化：写入可区分标记，便于排查（不抛异常，scheduler 继续其它基金）
                try:
                    async with AsyncSession(engine) as session:
                        if existing_record:
                            # UPDATE已有记录
                            existing_record.deepseek_advice = f"[DEEPSEEK_CALL_FAILED: {str(last_err)[:200]}]"
                            session.add(existing_record)
                            await session.commit()
                        else:
                            # INSERT新记录 (validation-A尚未创建)
                            new_fail_record = StrategyValidationLog(
                                trade_date=today,
                                fund_code=fund_code,
                                user_id=user_id,
                                deepseek_advice=f"[DEEPSEEK_CALL_FAILED: {str(last_err)[:200]}]",
                            )
                            session.add(new_fail_record)
                            await session.commit()
                except Exception:
                    logger.warning("[Scheduler] [validation-C] %s 标记CALL_FAILED写入失败", fund_code)
                continue

            # 2d. 提取建议方向（仅从首行解析，避免分析段中的方向词污染）
            first_line = ai_response.strip().split("\n")[0] if ai_response else ""
            advice_action = "hold"
            if "加仓" in first_line or "增持" in first_line:
                advice_action = "increase"
            elif "减仓" in first_line or "减持" in first_line or "止损" in first_line:
                advice_action = "decrease"

            # Phase 1: Feature Flag 控制 override 行为
            _action_cn_to_code = {"加仓": "increase", "持有": "hold", "减仓": "decrease"}
            system_action_code = _action_cn_to_code.get(system_action, "hold")
            final_action = advice_action
            action_mismatch = False
            if _is_independent:
                # 独立顾问模式：不 override，保留 AI 原始方向
                # 但 Gate 安全边界仍强制系统方向（安全官建议）
                _gate_triggered = (gate_1_triggered == 1) or (gate_2_triggered == 1)
                if _gate_triggered and system_action_code != advice_action:
                    final_action = system_action_code
                    action_mismatch = True
                    logger.warning(
                        "[Scheduler] [validation-C] %s Gate已触发，强制系统方向(%s)覆盖AI方向(%s) — 安全边界",
                        fund_code, system_action_code, advice_action,
                    )
                    _action_code_to_cn = {"increase": "加仓", "hold": "持有", "decrease": "减仓"}
                    override_note = (
                        f"[系统override-Gate安全] Gate已触发，模型方向{_action_code_to_cn.get(advice_action, advice_action)}被强制覆盖为系统方向{system_action}。\n\n"
                    )
                    ai_response = override_note + ai_response
                elif system_action_code != advice_action:
                    action_mismatch = True
                    logger.info(
                        "[Scheduler] [validation-C] %s AI独立方向(%s)与系统(%s)不同 — independent模式保留AI方向",
                        fund_code, advice_action, system_action_code,
                    )
            else:
                # 翻译器模式：强制 override 为系统方向
                if system_action_code != advice_action:
                    final_action = system_action_code
                    action_mismatch = True
                    logger.warning(
                        "[Scheduler] [validation-C] %s 模型解析action(%s)与系统权威(%s)不一致，强制override为系统action",
                        fund_code, advice_action, system_action_code,
                    )
                    # 在advice文本前插入override标注，使存储文本自洽
                    _action_code_to_cn = {"increase": "加仓", "hold": "持有", "decrease": "减仓"}
                    override_note = (
                        f"[系统override] 模型首行方向解析为{_action_code_to_cn.get(advice_action, advice_action)}，"
                        f"系统权威方向为{system_action}，已强制采用系统方向。\n\n"
                    )
                    ai_response = override_note + ai_response

            # 2e. 更新DB
            async with AsyncSession(engine) as session:
                if existing_record:
                    # UPDATE已有记录 (validation-A已创建或之前INSERT的)
                    existing_record.deepseek_advice = ai_response
                    existing_record.deepseek_advice_action = final_action
                    if action_mismatch:
                        existing_record.ext_text1 = (
                            '{"raw_action": "%s", "flag": "model_mismatch"}' % advice_action
                        )
                    session.add(existing_record)
                    await session.commit()
                else:
                    # INSERT新记录 (validation-A尚未创建)
                    new_record = StrategyValidationLog(
                        trade_date=today,
                        fund_code=fund_code,
                        user_id=user_id,
                        deepseek_advice=ai_response,
                        deepseek_advice_action=final_action,
                    )
                    if action_mismatch:
                        new_record.ext_text1 = (
                            '{"raw_action": "%s", "flag": "model_mismatch"}' % advice_action
                        )
                    session.add(new_record)
                    await session.commit()

            success += 1
            logger.info("[Scheduler] [validation-C] %s AI建议=%s (%d字)",
                       fund_code, final_action, len(ai_response))
        except Exception as e:
            fail += 1
            logger.error("[Scheduler] [validation-C] %s FAIL: %s", fund_code, e)

    logger.info("[Scheduler] [validation-C] AI建议完成 -- %d 成功, %d 失败, %d 跳过", success, fail, skipped)

    # 更新 ai_analysis 模块版本号（AI建议已更新，通知前端刷新）
    try:
        await update_data_version("ai_analysis")
        await invalidate_module_cache("ai_analysis")
    except Exception as e:
        logger.warning("[Scheduler] 版本号更新失败(ai_analysis): %s", e)


# ============================================================
# 策略验证分析表 — 任务B: 17:45 T+1回验回填
# ============================================================
async def _run_validation_backfill() -> None:

    """
    策略验证-任务B: 17:45 T+1回验回填

    处理昨天的strategy_validation_log记录：
    1. 获取昨日实际净值(fund_nav) → 计算actual_nav_change_pct
    2. 从daily_signal_snapshot获取actual_score/actual_signal_level
    3. 从advice_log获取actual_action
    4. 计算actual_trend (up/down/flat)
    5. 计算signal_accuracy / advice_accuracy / gate_accuracy
    6. 计算validation_score (综合评分)
    7. 回填deepseek_advice_correct
    8. UPDATE strategy_validation_log
    """
    from app.core.database import get_async_engine
    from sqlalchemy import select, or_
    from app.models.strategy_validation_log import StrategyValidationLog
    from app.models.fund_nav import FundNav
    from app.models.daily_signal_snapshot import DailySignalSnapshot
    from app.models.advice_log import AdviceLog

    if not await _is_trade_day():
        logger.info("[Scheduler] [validation-B] 非交易日，跳过")
        return

    today = date.today()
    engine = get_async_engine()

    # [Bugfix] 查找最近一个有记录的交易日(而非简单today-1)
    # 周一 today-1=周日, validation-A 周末不运行 -> 查不到数据 -> early return 跳过快照生成
    async with AsyncSession(engine) as _date_sess:
        _last_td_stmt = select(StrategyValidationLog.trade_date).where(
            StrategyValidationLog.trade_date < today
        ).order_by(StrategyValidationLog.trade_date.desc()).limit(1)
        _last_td_result = await _date_sess.execute(_last_td_stmt)
        _last_td_row = _last_td_result.first()
        yesterday = _last_td_row[0] if _last_td_row else today - timedelta(days=1)

    logger.info("[Scheduler] [validation-B] 开始T+1回验 -- 处理%s数据", yesterday.isoformat())

    # 1. 查询昨天未回验的记录
    async with AsyncSession(engine) as session:
        stmt = select(StrategyValidationLog).where(
            StrategyValidationLog.trade_date == yesterday,
            or_(
                StrategyValidationLog.actual_trend.is_(None),
                StrategyValidationLog.actual_score.is_(None),
            ),
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

    if not records:
        logger.info("[Scheduler] [validation-B] 无待回验记录，跳过回验循环(快照继续生成)")

    success = 0
    fail = 0
    skipped = 0

    for record in records:
        try:
            fund_code = record.fund_code

            # 2. 获取实际净值
            actual_nav = None
            prev_nav = None
            try:
                async with AsyncSession(engine) as session:
                    nav_stmt = select(FundNav.nav, FundNav.nav_date).where(
                        FundNav.fund_code == fund_code,
                        FundNav.nav_date <= yesterday,
                    ).order_by(FundNav.nav_date.desc()).limit(2)
                    nav_result = await session.execute(nav_stmt)
                    nav_rows = nav_result.all()
                    if nav_rows:
                        actual_nav = float(nav_rows[0][0]) if nav_rows[0][0] else None
                        if len(nav_rows) > 1:
                            prev_nav = float(nav_rows[1][0]) if nav_rows[1][0] else None
            except Exception:
                pass

            if actual_nav is None or prev_nav is None or prev_nav == 0:
                skipped += 1
                logger.info("[Scheduler] [validation-B] %s 净值未更新，跳过(下次重试)", fund_code)
                continue

            # 3. 计算净值变化
            actual_nav_change_pct = round((actual_nav - prev_nav) / prev_nav * 100, 2)

            # 4. 判断趋势
            if actual_nav_change_pct > 0.5:
                actual_trend = "up"
            elif actual_nav_change_pct < -0.5:
                actual_trend = "down"
            else:
                actual_trend = "flat"

            # 5. 从 daily_signal_snapshot 获取实际信号/情绪分
            actual_score = None
            actual_signal_level = None
            actual_action = None
            actual_target_position = None
            actual_signal = None
            try:
                async with AsyncSession(engine) as session:
                    # 尝试 fund_code → sector_code → broad 递减查找
                    lookup_codes = []
                    if record.fund_code:
                        lookup_codes.append(record.fund_code)
                    lookup_codes.extend(["000300.SH", "000001.SH"])

                    for code in lookup_codes:
                        snap_stmt = select(DailySignalSnapshot).where(
                            DailySignalSnapshot.target_code == code,
                            DailySignalSnapshot.snapshot_date == yesterday,
                        )
                        snap_result = await session.execute(snap_stmt)
                        snap = snap_result.scalar_one_or_none()
                        if snap:
                            actual_score = float(snap.composite_score) if snap.composite_score else None
                            actual_signal_level = snap.signal_level
                            actual_signal = snap.signal_level
                            actual_action = snap.action_advice
                            actual_target_position = float(snap.target_position_pct) if snap.target_position_pct else None
                            break
            except Exception:
                pass

            # 6. 尝试从 advice_log 获取 actual_action（如果 snapshot 没找到）
            if actual_action is None:
                try:
                    async with AsyncSession(engine) as session:
                        advice_stmt = select(AdviceLog.advice_type, AdviceLog.signal_level).where(
                            AdviceLog.fund_code == fund_code,
                            AdviceLog.advice_date == yesterday,
                        ).order_by(AdviceLog.id.desc()).limit(1)
                        advice_result = await session.execute(advice_stmt)
                        advice_row = advice_result.first()
                        if advice_row:
                            advice_type = advice_row[0]
                            if advice_type:
                                type_map = {"buy": "increase", "hold": "hold", "reduce": "decrease", "watch": "hold"}
                                actual_action = type_map.get(advice_type, "hold")
                            if advice_row[1] and actual_signal is None:
                                actual_signal = advice_row[1]
                except Exception:
                    pass

            # 7. 信号准确度
            preview_signal = record.preview_signal or "B"
            is_bullish = preview_signal in ("S+", "S", "A")
            is_bearish = preview_signal in ("D", "E")
            is_neutral = preview_signal in ("B", "C")

            if is_bullish:
                signal_accuracy = 1.0 if actual_trend == "up" else (0.5 if actual_trend == "flat" else 0.0)
            elif is_bearish:
                signal_accuracy = 1.0 if actual_trend == "down" else (0.5 if actual_trend == "flat" else 0.0)
            else:
                signal_accuracy = 1.0 if actual_trend == "flat" else 0.5

            # 8. 建议准确度
            advice_accuracy = None
            if actual_action:
                if actual_action == "increase":
                    advice_accuracy = 1.0 if actual_trend == "up" else (0.5 if actual_trend == "flat" else 0.0)
                elif actual_action == "decrease":
                    advice_accuracy = 1.0 if actual_trend == "down" else (0.5 if actual_trend == "flat" else 0.0)
                else:  # hold
                    advice_accuracy = 1.0 if actual_trend in ("down", "flat") else 0.5

            # 9. Gate准确度 — 区分 Gate-1(加仓信号) vs Gate-2(减仓信号)
            if record.gate_1_triggered == 1 and record.gate_2_triggered == 1:
                # 两个Gate同时触发(矛盾信号), 取0.5部分正确
                gate_accuracy = 0.5
            elif record.gate_1_triggered == 1:
                # Gate-1: 加仓信号 — 大涨(>3%)=正确, 其他=错误
                gate_accuracy = 1.0 if actual_nav_change_pct > 3.0 else 0.0
            elif record.gate_2_triggered == 1:
                # Gate-2: 减仓信号 — 大跌(<-3%)=正确(规避风险), 其他=错误
                gate_accuracy = 1.0 if actual_nav_change_pct < -3.0 else 0.0
            else:
                # 无Gate触发 — 未大跌(>-5%)=正确(无需干预), 大跌=错误(应预警)
                gate_accuracy = 1.0 if actual_nav_change_pct > -5.0 else 0.0

            # 10. 综合评分
            validation_score = round(
                signal_accuracy * 30 + (advice_accuracy or 0) * 30 + gate_accuracy * 40,
                2,
            )

            # 11. DeepSeek准确度 — 用AI原始方向回验(即使被Gate覆盖,仍评估AI真实判断)
            #    3级评分: 1.0=命中, 0.5=震荡市部分正确, 0.0=方向错误
            deepseek_advice_correct = None
            if record.deepseek_advice_action:
                import json as _json
                ds_eval_action = record.deepseek_advice_action
                # 优先用 ext_text1 中的 raw_action(Gate覆盖前的AI原始判断)
                if record.ext_text1:
                    try:
                        _ext = _json.loads(record.ext_text1)
                        if _ext.get("raw_action"):
                            ds_eval_action = _ext["raw_action"]
                    except Exception:
                        pass

                if ds_eval_action == "increase":
                    if actual_trend == "up":
                        deepseek_advice_correct = 1.0
                    elif actual_trend == "flat":
                        deepseek_advice_correct = 0.5
                    else:
                        deepseek_advice_correct = 0.0
                elif ds_eval_action == "decrease":
                    if actual_trend == "down":
                        deepseek_advice_correct = 1.0
                    elif actual_trend == "flat":
                        deepseek_advice_correct = 0.5
                    else:
                        deepseek_advice_correct = 0.0
                else:  # hold
                    if actual_trend in ("down", "flat"):
                        deepseek_advice_correct = 1.0
                    else:
                        deepseek_advice_correct = 0.5

            # 12. UPDATE
            async with AsyncSession(engine) as session:
                update_stmt = select(StrategyValidationLog).where(
                    StrategyValidationLog.id == record.id
                )
                update_result = await session.execute(update_stmt)
                db_record = update_result.scalar_one_or_none()
                if db_record:
                    db_record.actual_nav = actual_nav
                    db_record.actual_nav_change_pct = actual_nav_change_pct
                    db_record.actual_score = actual_score
                    db_record.actual_signal_level = actual_signal_level
                    db_record.actual_trend = actual_trend
                    db_record.actual_action = actual_action
                    db_record.actual_target_position = actual_target_position
                    db_record.actual_signal = actual_signal
                    db_record.signal_accuracy = signal_accuracy
                    db_record.advice_accuracy = advice_accuracy
                    db_record.gate_accuracy = gate_accuracy
                    db_record.validation_score = validation_score
                    db_record.deepseek_advice_correct = deepseek_advice_correct
                    await session.commit()

            success += 1
            logger.info("[Scheduler] [validation-B] %s: trend=%s nav_chg=%.2f%% score=%.1f/%.1f acc=%.2f",
                       fund_code, actual_trend, actual_nav_change_pct,
                       record.preview_score or 0, actual_score or 0, validation_score)
        except Exception as e:
            fail += 1
            logger.error("[Scheduler] [validation-B] %s FAIL: %s", record.fund_code, e)

    logger.info("[Scheduler] [validation-B] T+1回验完成 -- %d 成功, %d 失败, %d 跳过", success, fail, skipped)

    # 更新数据版本号 + 失效缓存
    for _mod in ("ai_analysis", "holdings"):
        try:
            await update_data_version(_mod)
            await invalidate_module_cache(_mod)
        except Exception as e:
            logger.warning("[Scheduler] 版本号更新失败(%s): %s", _mod, e)

    # 13. 数据完整性检查 — 分级阈值监控
    try:
        from sqlalchemy import text as _text
        async with AsyncSession(engine) as session:
            comp_sql = _text("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN elasticity IS NULL THEN 1 ELSE 0 END) as elasticity_null,
                    SUM(CASE WHEN preview_score IS NULL THEN 1 ELSE 0 END) as preview_null,
                    SUM(CASE WHEN yesterday_score IS NULL THEN 1 ELSE 0 END) as yesterday_null,
                    SUM(CASE WHEN market_index_chg_pct IS NULL THEN 1 ELSE 0 END) as market_null,
                    SUM(CASE WHEN sector_chg_pct IS NULL THEN 1 ELSE 0 END) as sector_null,
                    SUM(CASE WHEN gszzl IS NULL THEN 1 ELSE 0 END) as gszzl_null,
                    SUM(CASE WHEN actual_trend IS NULL THEN 1 ELSE 0 END) as trend_null,
                    SUM(CASE WHEN deepseek_advice_correct IS NULL THEN 1 ELSE 0 END) as ds_null,
                    SUM(CASE WHEN unrealized_pnl_pct IS NULL THEN 1 ELSE 0 END) as pnl_null,
                    SUM(CASE WHEN holding_market_value IS NULL THEN 1 ELSE 0 END) as holding_null
                FROM strategy_validation_log
                WHERE trade_date = :check_date
            """)
            comp_result = await session.execute(comp_sql, {"check_date": yesterday})
            comp_row = comp_result.one()
            total = comp_row[0] or 0
            if total > 0:
                # 分级阈值: 核心因子98%, 市场数据90%, 派生数据80%
                field_checks = [
                    ("elasticity", comp_row[1] or 0, 0.98, "核心"),
                    ("preview_score", comp_row[2] or 0, 0.98, "核心"),
                    ("yesterday_score", comp_row[3] or 0, 0.98, "核心"),
                    ("market_index_chg_pct", comp_row[4] or 0, 0.90, "市场"),
                    ("sector_chg_pct", comp_row[5] or 0, 0.90, "市场"),
                    ("gszzl", comp_row[6] or 0, 0.90, "市场"),
                    ("actual_trend", comp_row[7] or 0, 0.98, "核心"),
                    ("deepseek_advice_correct", comp_row[8] or 0, 0.98, "核心"),
                    ("unrealized_pnl_pct", comp_row[9] or 0, 0.80, "派生"),
                    ("holding_market_value", comp_row[10] or 0, 0.80, "派生"),
                ]
                alert_count = 0
                for field_name, null_count, threshold, tier in field_checks:
                    fill_rate = 1 - null_count / total
                    if fill_rate < threshold:
                        alert_count += 1
                        logger.warning(
                            "[validation-B] [数据完整性告警] %s: NULL率=%.0f%% (%d/%d), 低于阈值%.0f%% [%s]",
                            field_name, (1 - fill_rate) * 100, null_count, total, threshold * 100, tier,
                        )
                logger.info("[validation-B] [数据完整性] %s 检查完成: %d/%d 字段告警", yesterday, alert_count, len(field_checks))
    except Exception as e:
        logger.warning("[Scheduler] [validation-B] 数据完整性检查失败: %s", e)

    # ================================================================
    # 分析日报快照写入 (系统进化4方向结果持久化)
    # ================================================================
    try:
        from app.models.analysis_daily_snapshot import AnalysisDailySnapshot
        from sqlalchemy import text as sa_text, func as sa_func2, delete as sa_delete
        import numpy as _np
        import math as _math

        snap_date = yesterday
        engine = get_async_engine()

        async with AsyncSession(engine) as session:
            # 先清除当天旧快照 (防重跑重复)
            await session.execute(
                sa_delete(AnalysisDailySnapshot).where(
                    AnalysisDailySnapshot.snapshot_date == snap_date
                )
            )

            records_written = 0

            # === 1. 滚动窗口快照 (全局 30/60/90天) ===
            for window_days in [30, 60, 90]:
                window_ago = today - timedelta(days=window_days)
                rw_stmt = select(
                    sa_func2.avg(StrategyValidationLog.signal_accuracy),
                    sa_func2.avg(StrategyValidationLog.advice_accuracy),
                    sa_func2.avg(StrategyValidationLog.gate_accuracy),
                    sa_func2.avg(StrategyValidationLog.deepseek_advice_correct),
                    sa_func2.count(StrategyValidationLog.deepseek_advice_correct),
                ).where(
                    StrategyValidationLog.trade_date >= window_ago,
                    StrategyValidationLog.trade_date < today,
                )
                rw_result = await session.execute(rw_stmt)
                rw_row = rw_result.one_or_none()
                if rw_row and rw_row[4] and int(rw_row[4]) > 0:
                    metrics = ["signal_accuracy", "advice_accuracy", "gate_accuracy", "deepseek_accuracy"]
                    for idx, metric in enumerate(metrics):
                        val = rw_row[idx]
                        session.add(AnalysisDailySnapshot(
                            snapshot_date=snap_date,
                            analysis_type="rolling_window",
                            fund_code=None,
                            metric_name=f"{metric}_{window_days}d",
                            metric_value=round(float(val), 4) if val is not None else None,
                            sample_size=int(rw_row[4]),
                        ))
                        records_written += 1

            # === 2. Per-fund 快照 (每基金 30天) ===
            pf_30ago = today - timedelta(days=30)
            pf_stmt = select(
                StrategyValidationLog.fund_code,
                sa_func2.avg(StrategyValidationLog.signal_accuracy),
                sa_func2.avg(StrategyValidationLog.advice_accuracy),
                sa_func2.avg(StrategyValidationLog.gate_accuracy),
                sa_func2.avg(StrategyValidationLog.deepseek_advice_correct),
                sa_func2.count(StrategyValidationLog.deepseek_advice_correct),
            ).where(
                StrategyValidationLog.trade_date >= pf_30ago,
                StrategyValidationLog.trade_date < today,
            ).group_by(StrategyValidationLog.fund_code)

            pf_result = await session.execute(pf_stmt)
            for pf_row in pf_result.fetchall():
                fund_code = pf_row[0]
                pf_n = int(pf_row[5]) if pf_row[5] else 0
                metrics = ["signal_accuracy", "advice_accuracy", "gate_accuracy", "deepseek_accuracy"]
                for idx, metric in enumerate(metrics):
                    val = pf_row[idx + 1]
                    session.add(AnalysisDailySnapshot(
                        snapshot_date=snap_date,
                        analysis_type="per_fund",
                        fund_code=fund_code,
                        metric_name=metric,
                        metric_value=round(float(val), 4) if val is not None else None,
                        sample_size=pf_n,
                    ))
                    records_written += 1

            # === 3. 因子相关性快照 (Pearson + ANOVA, 默认对 deepseek_advice_correct) ===
            try:
                from scipy import stats as sp_stats
                corr_sql = sa_text("""
                    SELECT
                        v.elasticity, v.preview_score, v.yesterday_score,
                        v.yesterday_confidence, v.market_index_chg_pct,
                        v.sector_chg_pct, v.gszzl,
                        v.gate_1_distance_pct, v.gate_2_distance_pct,
                        v.score_delta,
                        s.regime, s.macd_state,
                        v.deepseek_advice_correct AS result_value
                    FROM strategy_validation_log v
                    LEFT JOIN daily_signal_snapshot s
                        ON v.fund_code = s.target_code COLLATE utf8mb4_unicode_ci
                        AND v.trade_date = s.snapshot_date
                        AND s.target_type = 'fund'
                    WHERE v.trade_date >= :start_date
                    AND v.trade_date < :today
                    AND v.deepseek_advice_correct IS NOT NULL
                """)
                corr_result = await session.execute(corr_sql, {
                    "start_date": today - timedelta(days=30),
                    "today": today,
                })
                corr_rows = corr_result.fetchall()

                cont_factors = [
                    "elasticity", "preview_score", "yesterday_score",
                    "yesterday_confidence", "market_index_chg_pct",
                    "sector_chg_pct", "gszzl",
                    "gate_1_distance_pct", "gate_2_distance_pct", "score_delta",
                ]
                cat_factors = ["regime", "macd_state"]
                n_tests = len(cont_factors) + len(cat_factors)
                bonferroni_alpha = 0.05 / n_tests

                if len(corr_rows) >= 5:
                    result_values = _np.array([float(r[-1]) for r in corr_rows], dtype=float)

                    for idx, factor_name in enumerate(cont_factors):
                        pairs = [(float(r[idx]), float(r[-1])) for r in corr_rows if r[idx] is not None]
                        if len(pairs) < 5:
                            session.add(AnalysisDailySnapshot(
                                snapshot_date=snap_date, analysis_type="factor_correlation",
                                fund_code=None, metric_name=factor_name,
                                metric_value=None, sample_size=len(pairs),
                                p_value=None, is_significant=0,
                                extra={"note": "samples insufficient"},
                            ))
                            records_written += 1
                            continue

                        x = _np.array([p[0] for p in pairs], dtype=float)
                        y = _np.array([p[1] for p in pairs], dtype=float)
                        try:
                            corr, p_val = sp_stats.pearsonr(x, y)
                        except Exception:
                            corr, p_val = 0.0, 1.0
                        if _math.isnan(corr):
                            corr = 0.0
                        if _math.isnan(p_val):
                            p_val = 1.0

                        session.add(AnalysisDailySnapshot(
                            snapshot_date=snap_date, analysis_type="factor_correlation",
                            fund_code=None, metric_name=factor_name,
                            metric_value=round(float(corr), 4),
                            sample_size=len(pairs),
                            p_value=round(float(p_val), 6),
                            is_significant=1 if float(p_val) < bonferroni_alpha else 0,
                        ))
                        records_written += 1

                    cat_offset = len(cont_factors)
                    for idx, factor_name in enumerate(cat_factors):
                        col_idx = cat_offset + idx
                        groups = {}
                        for r in corr_rows:
                            val = r[col_idx]
                            if val is not None:
                                groups.setdefault(val, []).append(float(r[-1]))

                        group_stats = {}
                        for g, vals in sorted(groups.items(), key=lambda x: -len(x[1])):
                            if vals:
                                group_stats[g] = {"mean": round(float(_np.mean(vals)), 4), "n": len(vals)}

                        anova_p = None
                        valid_groups = [v for v in groups.values() if len(v) >= 2]
                        if len(valid_groups) >= 2:
                            try:
                                _f, anova_p = sp_stats.f_oneway(*[_np.array(v) for v in valid_groups])
                                if _math.isnan(anova_p):
                                    anova_p = None
                            except Exception:
                                pass

                        session.add(AnalysisDailySnapshot(
                            snapshot_date=snap_date, analysis_type="factor_correlation",
                            fund_code=None, metric_name=factor_name,
                            metric_value=round(float(anova_p), 4) if anova_p is not None else None,
                            sample_size=sum(len(v) for v in groups.values()),
                            p_value=round(float(anova_p), 6) if anova_p is not None else None,
                            is_significant=1 if anova_p is not None and float(anova_p) < bonferroni_alpha else 0,
                            extra={"groups": group_stats, "type": "anova"},
                        ))
                        records_written += 1
            except ImportError:
                logger.info("[validation-B] scipy未安装, 因子相关性快照跳过")
            except Exception as e:
                logger.warning("[validation-B] 因子相关性快照失败: %s", e)

            # === 4. 数据完整性快照 (各字段NULL率) ===
            dq_fields = {
                "elasticity": "core", "preview_score": "core", "yesterday_score": "core",
                "actual_trend": "core", "deepseek_advice_correct": "core",
                "market_index_chg_pct": "market", "sector_chg_pct": "market", "gszzl": "market",
                "unrealized_pnl_pct": "derived", "holding_market_value": "derived",
            }
            dq_sql_parts = [
                f"SUM(CASE WHEN `{f}` IS NULL THEN 1 ELSE 0 END) as `{f}_null`"
                for f in dq_fields
            ]
            dq_sql = sa_text(
                f"SELECT COUNT(*) as total, {', '.join(dq_sql_parts)} "
                f"FROM strategy_validation_log WHERE trade_date = :check_date"
            )
            dq_result = await session.execute(dq_sql, {"check_date": snap_date})
            dq_row = dq_result.one()
            total = int(dq_row[0]) if dq_row[0] else 0

            if total > 0:
                for idx, (field_name, tier) in enumerate(dq_fields.items()):
                    null_count = int(dq_row[idx + 1]) if dq_row[idx + 1] else 0
                    null_rate = round(null_count / total, 4)
                    session.add(AnalysisDailySnapshot(
                        snapshot_date=snap_date,
                        analysis_type="data_quality",
                        fund_code=None,
                        metric_name=field_name,
                        metric_value=null_rate,
                        sample_size=total,
                        is_significant=1 if null_rate > 0 else 0,
                        extra={"tier": tier, "null_count": null_count},
                    ))
                    records_written += 1

            await session.commit()
            logger.info("[validation-B] [分析快照] %s 写入完成: %d 条记录", snap_date, records_written)

    except Exception as e:
        logger.warning("[Scheduler] [validation-B] 分析快照写入失败: %s", e)


# ============================================================
# Scheduler 初始化
# ============================================================

def init_scheduler() -> AsyncIOScheduler:
    """
    初始化并启动 APScheduler。

    在 FastAPI lifespan startup 中调用。
    返回 scheduler 实例供 shutdown 时关闭。
    """
    scheduler = AsyncIOScheduler(
        timezone="Asia/Shanghai",
        job_defaults={"coalesce": True, "max_instances": 1},
    )

    # 任务 1：每个交易日 15:30 执行市场快照
    scheduler.add_job(
        _run_daily_snapshot,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=30,
            timezone="Asia/Shanghai",
        ),
        id="daily_snapshot",
        name="每日情绪快照",
        replace_existing=True,
    )

    # 任务 2：每个交易日 15:45 执行板块快照（改动 1）
    scheduler.add_job(
        _run_sector_snapshot,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=45,
            timezone="Asia/Shanghai",
        ),
        id="daily_sector_snapshot",
        name="每日板块快照",
        replace_existing=True,
    )

    # 任务 3：每周日 22:00 执行建议验证回填（改动 2）
    scheduler.add_job(
        _weekly_advice_verification,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=22,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="weekly_advice_verification",
        name="每周建议验证",
        replace_existing=True,
    )


    # 任务 4：每个交易日 16:00 执行因子更新
    scheduler.add_job(
        _run_factor_update,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=16,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="daily_factor_update",
        name="每日因子更新",
        replace_existing=True,
    )


    # 任务 5：每个交易日 17:00 执行净值更新
    scheduler.add_job(
        _run_nav_update,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=17,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="daily_nav_update",
        name="每日净值更新",
        replace_existing=True,
    )

    # 任务 6：盘中实时估值更新（14:30、14:45、15:00）
    for minute in [30, 45]:
        scheduler.add_job(
            _run_realtime_estimate,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=14,
                minute=minute,
                timezone="Asia/Shanghai",
            ),
            id=f"realtime_estimate_{minute}",
            name=f"盘中实时估值 {minute}分",
            replace_existing=True,
        )
    scheduler.add_job(
        _run_realtime_estimate,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="realtime_estimate_1500",
        name="盘中实时估值 15:00",
        replace_existing=True,
    )

    # 任务 7：每日净值复查（22:00）
    scheduler.add_job(
        _run_nav_recheck,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=22,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="daily_nav_recheck",
        name="每日净值复查",
        replace_existing=True,
    )


    # 任务 8：数据就绪检查（16:30、17:00、17:30、18:00）
    for check_hour, check_minute in [("16", "30"), ("17", "00"), ("17", "30"), ("18", "00")]:
        scheduler.add_job(
            _run_data_readiness_check,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=int(check_hour),
                minute=int(check_minute),
                timezone="Asia/Shanghai",
            ),
            id=f"data_readiness_{check_hour}{check_minute}",
            name=f"数据就绪检查 {check_hour}:{check_minute}",
            replace_existing=True,
        )

    # 任务 9：建仓评级缓存刷新（17:30）
    scheduler.add_job(
        _run_cache_refresh,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=17,
            minute=30,
            timezone="Asia/Shanghai",
        ),
        id="cache_refresh",
        name="建仓评级缓存刷新",
        replace_existing=True,
    )

    # 修复⑤: 启动时自检持仓基金 nav 深度
    # 修复⑤: 启动30秒后自动检查持仓基金 nav 深度
    # 用 APScheduler 一次性任务替代 asyncio.create_task，避免函数定义顺序问题
    scheduler.add_job(
        _startup_nav_depth_check,
        trigger="date",
        run_date=datetime.now() + timedelta(seconds=30),
        id="startup_nav_depth_check",
        name="启动nav深度自检",
        replace_existing=True,
    )
    

    # 任务 10：每日决策快照（17:05 - 因子16:00+净值17:00之后）
    scheduler.add_job(
        _run_signal_snapshot,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=17,
            minute=5,
            timezone="Asia/Shanghai",
        ),
        id="daily_signal_snapshot",
        name="每日决策快照",
        replace_existing=True,
    )

    # 任务 14：盘中预演元数据打包（15:40 — 在快照15:30+板块价格15:35之后）
    scheduler.add_job(
        _run_intraday_meta_pack,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=40,
            timezone="Asia/Shanghai",
        ),
        id="intraday_meta_pack",
        name="盘中预演元数据打包",
        replace_existing=True,
    )

    # 任务 15：弹性系数周更（周五17:35 — 在决策快照17:05之后，确保当日分数已入库）
    scheduler.add_job(
        _run_intraday_elastic_weekly,
        trigger=CronTrigger(
            day_of_week="fri",
            hour=17,
            minute=35,
            timezone="Asia/Shanghai",
        ),
        id="intraday_elastic_weekly",
        name="弹性系数周更",
        replace_existing=True,
    )

    # 任务 17：对账校准（15:50 -- 在元数据打包15:40之后）
    scheduler.add_job(
        _run_intraday_preview_reconciliation,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=50,
            timezone="Asia/Shanghai",
        ),
        id="intraday_preview_reconciliation",
        name="对账校准",
        replace_existing=True,
    )

    # 任务 16：盘中预演计算（交易时段每5分钟，函数内部检查时段）
    scheduler.add_job(
        _run_intraday_preview_calculate,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour="9-14",
            minute="*/5",
            timezone="Asia/Shanghai",
        ),
        id="intraday_preview_calculate",
        name="盘中预演计算(每5分钟)",
        replace_existing=True,
    )
    # 15:00 也是交易时段末尾
    scheduler.add_job(
        _run_intraday_preview_calculate,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=15,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="intraday_preview_calculate_1500",
        name="盘中预演计算15:00",
        replace_existing=True,
    )

    # 任务 V1：策略验证-预演持久化+系统建议（14:45）
    scheduler.add_job(
        _run_validation_persist,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=14,
            minute=45,
            timezone="Asia/Shanghai",
        ),
        id="validation_persist",
        name="策略验证-预演持久化+系统建议",
        replace_existing=True,
    )

    # 任务 V2：策略验证-DeepSeek AI建议（14:40）
    scheduler.add_job(
        _run_validation_deepseek_advice,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=14,
            minute=40,
            timezone="Asia/Shanghai",
        ),
        id="validation_deepseek",
        name="策略验证-AI建议",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 任务 V3：策略验证-T+1回验回填（17:45，从17:35调整避开17:30缓存刷新）
    scheduler.add_job(
        _run_validation_backfill,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=17,
            minute=45,
            timezone="Asia/Shanghai",
        ),
        id="validation_backfill",
        name="策略验证-T+1回验",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # 任务 5b：每日 08:00 早盘补拉（17:00+22:00 兜底窗口，基金公司延迟发布最终兜底）
    scheduler.add_job(
        _run_nav_morning_fetch,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=8,
            minute=0,
            timezone="Asia/Shanghai",
        ),
        id="daily_nav_morning_fetch",
        name="每日08:00早盘补拉",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "[Scheduler] 已启动 — 08:00 早盘补拉 | 14:30/14:45/15:00 实时估值 | 15:30 市场快照 | 15:45 板块快照 | 16:00 因子更新 | 16:05 基金净值(crontab) | 17:00 净值更新 | 17:05 决策快照 | 17:30 缓存刷新 | 22:00 净值复查 | 数据就绪检查 16:30/17:00/17:30/18:00 | 9:30-15:00 盘中预演(5min) | 15:40 预演元数据 | 周五17:35 弹性系数周更 | 15:50 对账校准 | 每周日 22:00 建议验证 | 14:45 策略验证持久化 | 14:40 AI建议 | 17:45 T+1回验"
    )
    return scheduler


# ============================================================
# 任务 5：每日净值更新（新增）
# ============================================================

# ============================================================
# 任务 5：每日净值更新（新增）
# ============================================================

async def _run_nav_update() -> None:
    """
    每日净值更新：对所有持仓基金拉取最新净值并写入 fund_nav 表，
    同时更新 user_portfolio.current_nav。

    在每日因子更新后 1 小时执行（17:00），确保基金公司已公布净值。
    """
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.core.database import get_async_engine
    from app.models.fund_nav import FundNav
    from app.models.user_portfolio import UserPortfolio
    import tushare as ts
    from datetime import date as date_type

    today = date_type.today()
    today_str = today.strftime("%Y%m%d")
    # 修复②: 拉最近7天而非只拉今天，避免漏一天永远缺
    lookback_str = (today - timedelta(days=7)).strftime("%Y%m%d")
    logger.info("[Scheduler] 开始每日净值更新 — %s (拉取 %s~%s)", today_str, lookback_str, today_str)

    # 获取 Tushare token
    from app.core.config import settings
    if not settings.TUSHARE_TOKEN:
        logger.error("[Scheduler] TUSHARE_TOKEN 未配置，跳过净值更新")
        return

    try:
        pro = ts.pro_api(settings.TUSHARE_TOKEN)
    except Exception as e:
        logger.error("[Scheduler] Tushare 初始化失败: %s", e)
        return

    engine = get_async_engine()
    async with AsyncSessionType(engine) as session:
        # 获取所有持仓基金代码
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]

        if not fund_codes:
            logger.info("[Scheduler] 无持仓基金，跳过净值更新")
            return

        updated = 0
        failed = 0

        for fund_code in fund_codes:
            try:
                # 转换基金代码为 Tushare 格式
                from app.utils.code_format import to_tushare
                ts_code = to_tushare(fund_code)
                base_code = ts_code.split('.')[0]
                primary_suffix = ts_code.split('.')[-1]
                suffixes = [primary_suffix]
                if primary_suffix == 'OF':
                    suffixes.extend(['SH', 'SZ'])
                elif primary_suffix in ('SH', 'SZ'):
                    suffixes.extend(['OF', 'SZ' if primary_suffix == 'SH' else 'SH'])

                df = None
                for suf in suffixes:
                    try_code = f"{base_code}.{suf}"
                    try:
                        df = pro.fund_nav(ts_code=try_code, start_date=lookback_str, end_date=today_str)
                        if df is not None and not df.empty:
                            break
                    except Exception:
                        continue

                if df is None or df.empty:
                    logger.warning("[Scheduler] %s 无净值数据", fund_code)
                    failed += 1
                    continue

                # 获取最新净值
                nav_val = float(df.iloc[0]['unit_nav'])
                nav_date = str(df.iloc[0]['nav_date'])

                # 写入 fund_nav 表（先查是否已存在）
                from sqlalchemy import select as select_
                existing = await session.execute(
                    select_(FundNav).where(
                        FundNav.fund_code == fund_code,
                        FundNav.nav_date == nav_date
                    )
                )
                if existing.scalar_one_or_none() is None:
                    session.add(FundNav(
                        fund_code=fund_code,
                        nav_date=nav_date,
                        nav=nav_val,
                    ))
                    await session.flush()

                # 更新 user_portfolio: current_nav + 级联更新 market_value/total_return/return_rate
                await session.execute(
                    text("""
                        UPDATE user_portfolio
                        SET current_nav = :nav,
                            market_value = ROUND(holding_shares * :nav, 2),
                            total_return = ROUND((:nav - cost_nav) * holding_shares, 2),
                            return_rate = ROUND(((:nav - cost_nav) / NULLIF(cost_nav, 0)) * 100, 2),
                            updated_at = NOW()
                        WHERE fund_code = :code
                    """),
                    {"nav": nav_val, "code": fund_code}
                )

                updated += 1
                logger.info("[Scheduler] ✅ %s 净值更新: %.4f", fund_code, nav_val)

            except Exception as e:
                failed += 1
                logger.error("[Scheduler] ❌ %s 净值更新失败: %s", fund_code, e)

        await session.commit()
        logger.info("[Scheduler] 净值更新完成 — 成功 %d/%d, 失败 %d", updated, len(fund_codes), failed)

        # 更新 daily_return：根据 fund_nav 最近两条净值计算当日收益
        if updated > 0:
            logger.info("[Scheduler] 开始更新 daily_return ...")
            dr_updated = 0
            for fund_code in fund_codes:
                try:
                    nav_result = await session.execute(
                        text(
                            "SELECT nav FROM fund_nav "
                            "WHERE fund_code = :code "
                            "ORDER BY nav_date DESC "
                            "LIMIT 2"
                        ),
                        {"code": fund_code},
                    )
                    rows = nav_result.all()
                    if len(rows) < 2:
                        continue
                    today_nav = float(rows[0][0])
                    yesterday_nav = float(rows[1][0])
                    if yesterday_nav <= 0:
                        continue
                    # 获取 holding_shares 并计算 daily_return = shares * (today_nav - yesterday_nav)
                    hs_result = await session.execute(
                        text("SELECT holding_shares FROM user_portfolio WHERE fund_code = :code"),
                        {"code": fund_code},
                    )
                    hs_row = hs_result.first()
                    if hs_row and hs_row[0]:
                        dr = round(float(hs_row[0]) * (today_nav - yesterday_nav), 2)
                        await session.execute(
                            text("UPDATE user_portfolio SET daily_return = :dr WHERE fund_code = :code"),
                            {"dr": dr, "code": fund_code},
                        )
                        dr_updated += 1
                except Exception as e:
                    logger.warning("[Scheduler] %s daily_return 更新失败: %s", fund_code, e)
            logger.info("[Scheduler] daily_return 更新完成 — %d 只", dr_updated)

            # ── 更新 weight_pct（持仓占比）──
            # 修复: 之前无更新逻辑，导致 weight_pct 全为 0
            try:
                wp_result = await session.execute(
                    text("SELECT fund_code, market_value FROM user_portfolio")
                )
                wp_rows = wp_result.all()
                total_mv = sum(float(r[1] or 0) for r in wp_rows)
                if total_mv > 0:
                    wp_updated = 0
                    for fc, mv in wp_rows:
                        wp = round(float(mv or 0) / total_mv, 4) if mv and float(mv) > 0 else 0.0
                        await session.execute(
                            text("UPDATE user_portfolio SET weight_pct = :wp WHERE fund_code = :code"),
                            {"wp": wp, "code": fc},
                        )
                        wp_updated += 1
                    await session.commit()
                    logger.info("[Scheduler] weight_pct 更新完成 — %d 只 (总市值=%.2f)", wp_updated, total_mv)
            except Exception as e:
                logger.warning("[Scheduler] weight_pct 更新失败: %s", e)

        if failed > 0:
            logger.warning("[Scheduler] ⚠️ 本日净值更新有 %d 个基金失败", failed)



# ============================================================
# 任务 6：盘中实时估值更新（14:30、14:45、15:00）
# ============================================================

async def _run_realtime_estimate() -> None:
    """
    盘中实时估值更新：调用东方财富 API 获取实时估算净值，
    计算并更新 user_portfolio.daily_return。

    执行时间：每个交易日 14:30、14:45、15:00
    """
    import json
    import re
    import asyncio
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.core.database import get_async_engine

    def _fetch_estimate(fund_code: str):
        """同步函数：获取单只基金的实时估值"""
        import urllib.request
        url = "https://fundgz.1234567.com.cn/js/" + fund_code + ".js"
        req = urllib.request.Request(url, headers={"Referer": "https://fund.eastmoney.com/"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
        m = re.search(r"jsonpgz\((.*)\)", raw)
        if not m:
            return None
        d = json.loads(m.group(1))
        return float(d.get("gszzl", 0))

    logger.info("[Scheduler] 开始盘中实时估值更新...")
    engine = get_async_engine()
    async with AsyncSessionType(engine) as session:
        result = await session.execute(text("SELECT fund_code, market_value FROM user_portfolio"))
        rows = result.all()
        updated = 0
        for fund_code, market_value in rows:
            if not market_value:
                continue
            try:
                gszzl = await asyncio.to_thread(_fetch_estimate, fund_code)
                if gszzl is None:
                    continue
                dr = round(float(market_value) * gszzl / 100, 2)
                await session.execute(
                    text("UPDATE user_portfolio SET daily_return = :dr WHERE fund_code = :code"),
                    {"dr": dr, "code": fund_code}
                )
                updated += 1
            except Exception as e:
                logger.warning("[Scheduler] %s 实时估值失败: %s", fund_code, e)
        await session.commit()
        logger.info("[Scheduler] 实时估值更新完成 — %d 只", updated)


async def _run_nav_recheck() -> None:
    import tushare as ts
    from datetime import date as date_type
    from sqlalchemy import text, select
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.core.database import get_async_engine
    from app.models.fund_nav import FundNav
    from app.core.config import settings
    from app.models.user_portfolio import UserPortfolio
    today = date_type.today()
    today_str = today.strftime("%Y%m%d")
    # 修复③: 拉最近7天，弥补历史缺漏
    lookback_str = (today - timedelta(days=7)).strftime("%Y%m%d")
    logger.info("[Scheduler] 开始净值复查 — %s (拉取 %s~%s)", today_str, lookback_str, today_str)
    if not settings.TUSHARE_TOKEN:
        return
    pro = ts.pro_api(settings.TUSHARE_TOKEN)
    engine = get_async_engine()
    async with AsyncSessionType(engine) as session:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]
        updated = 0
        for fund_code in fund_codes:
            try:
                from app.utils.code_format import to_tushare
                ts_code = to_tushare(fund_code)
                df = pro.fund_nav(ts_code=ts_code, start_date=lookback_str, end_date=today_str)
                if df is None or df.empty:
                    continue
                nav_val = float(df.iloc[0]["unit_nav"])
                nav_date = str(df.iloc[0]["nav_date"])
                existing = await session.execute(
                    select(FundNav).where(FundNav.fund_code == fund_code, FundNav.nav_date == nav_date)
                )
                if existing.scalar_one_or_none() is None:
                    session.add(FundNav(fund_code=fund_code, nav_date=nav_date, nav=nav_val))
                    await session.flush()
                # 级联更新: current_nav + market_value + total_return + return_rate
                await session.execute(
                    text("""
                        UPDATE user_portfolio
                        SET current_nav = :nav,
                            market_value = ROUND(holding_shares * :nav, 2),
                            total_return = ROUND((:nav - cost_nav) * holding_shares, 2),
                            return_rate = ROUND(((:nav - cost_nav) / NULLIF(cost_nav, 0)) * 100, 2),
                            updated_at = NOW()
                        WHERE fund_code = :code
                    """),
                    {"nav": nav_val, "code": fund_code}
                )
                hs_row = (await session.execute(
                    text("SELECT holding_shares FROM user_portfolio WHERE fund_code = :code"),
                    {"code": fund_code}
                )).first()
                if hs_row and hs_row[0]:
                    nav_rows = (await session.execute(
                        text("SELECT nav FROM fund_nav WHERE fund_code = :code ORDER BY nav_date DESC LIMIT 2"),
                        {"code": fund_code}
                    )).all()
                    if len(nav_rows) >= 2:
                        shares = float(hs_row[0])
                        dr = round(shares * (float(nav_rows[0][0]) - float(nav_rows[1][0])), 2)
                        await session.execute(
                            text("UPDATE user_portfolio SET daily_return = :dr WHERE fund_code = :code"),
                            {"dr": dr, "code": fund_code}
                        )
                updated += 1
            except Exception as e:
                logger.warning("[Scheduler] %s 净值复查失败: %s", fund_code, e)
        await session.commit()
        logger.info("[Scheduler] 净值复查完成 — %d/%d", updated, len(fund_codes))


# ============================================================
# 任务 7b：每日 08:00 早盘补拉（基金公司延迟发布兜底）
# 17:00 + 22:00 两轮仍可能缺净值，08:00 是最终兜底窗口。
# ============================================================

async def _run_nav_morning_fetch() -> None:
    """
    08:00 早盘补拉：检查所有持仓基金 fund_nav 最新日期，
    若不满足则拉取最近3天补全，并更新 current_nav + daily_return。
    与 _run_nav_update 的区别：只补缺失的基金，遍历所有返回行。
    """
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.core.database import get_async_engine
    from app.models.fund_nav import FundNav
    from app.models.user_portfolio import UserPortfolio
    import tushare as ts
    from datetime import date as date_type

    today = date_type.today()
    today_str = today.strftime("%Y%m%d")
    lookback_str = (today - timedelta(days=3)).strftime("%Y%m%d")
    logger.info("[Scheduler] 开始08:00早盘补拉 — %s (拉取 %s~%s)", today_str, lookback_str, today_str)

    from app.core.config import settings
    if not settings.TUSHARE_TOKEN:
        logger.error("[Scheduler] TUSHARE_TOKEN 未配置，跳过早盘补拉")
        return

    try:
        pro = ts.pro_api(settings.TUSHARE_TOKEN)
    except Exception as e:
        logger.error("[Scheduler] Tushare 初始化失败: %s", e)
        return

    engine = get_async_engine()
    async with AsyncSessionType(engine) as session:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]

        if not fund_codes:
            logger.info("[Scheduler] 无持仓基金，跳过早盘补拉")
            return

        # 逐只检查最新 nav_date，决定是否需要补拉
        to_fetch: list[str] = []
        for fund_code in fund_codes:
            latest_row = (await session.execute(
                text("SELECT MAX(nav_date) FROM fund_nav WHERE fund_code = :code"),
                {"code": fund_code}
            )).scalar()
            if latest_row is None or str(latest_row) < today_str:
                to_fetch.append(fund_code)
            # latest_row >= today_str 说明已有今天净值，跳过

        if not to_fetch:
            logger.info("[Scheduler] 早盘补拉：所有 %d 只基金净值已是最新，无需补拉", len(fund_codes))
            return

        logger.info("[Scheduler] 早盘补拉：%d/%d 只基金需要补拉", len(to_fetch), len(fund_codes))

        updated = 0
        failed = 0

        for fund_code in to_fetch:
            try:
                from app.utils.code_format import to_tushare
                ts_code = to_tushare(fund_code)
                base_code = ts_code.split('.')[0]
                primary_suffix = ts_code.split('.')[-1]
                suffixes = [primary_suffix]
                if primary_suffix == 'OF':
                    suffixes.extend(['SH', 'SZ'])
                elif primary_suffix in ('SH', 'SZ'):
                    suffixes.extend(['OF', 'SZ' if primary_suffix == 'SH' else 'SH'])

                df = None
                for suf in suffixes:
                    try_code = f"{base_code}.{suf}"
                    try:
                        df = pro.fund_nav(ts_code=try_code, start_date=lookback_str, end_date=today_str)
                        if df is not None and not df.empty:
                            break
                    except Exception:
                        continue

                if df is None or df.empty:
                    logger.warning("[Scheduler] 早盘补拉 %s：Tushare 仍无数据", fund_code)
                    failed += 1
                    continue

                # 遍历所有返回行，补全缺失的日期
                new_count = 0
                for _, row in df.iterrows():
                    nav_val = float(row["unit_nav"])
                    nav_date = str(row["nav_date"])
                    existing = await session.execute(
                        select(FundNav).where(
                            FundNav.fund_code == fund_code,
                            FundNav.nav_date == nav_date
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(FundNav(
                            fund_code=fund_code,
                            nav_date=nav_date,
                            nav=nav_val,
                        ))
                        await session.flush()
                        new_count += 1

                # 取最新净值更新 current_nav + 级联 market_value/total_return/return_rate
                nav_val = float(df.iloc[0]["unit_nav"])
                await session.execute(
                    text("""
                        UPDATE user_portfolio
                        SET current_nav = :nav,
                            market_value = ROUND(holding_shares * :nav, 2),
                            total_return = ROUND((:nav - cost_nav) * holding_shares, 2),
                            return_rate = ROUND(((:nav - cost_nav) / NULLIF(cost_nav, 0)) * 100, 2),
                            updated_at = NOW()
                        WHERE fund_code = :code
                    """),
                    {"nav": nav_val, "code": fund_code}
                )

                updated += 1
                logger.info("[Scheduler] ✅ 早盘补拉 %s：新增 %d 条，最新净值 %.4f (%s)",
                           fund_code, new_count, nav_val, df.iloc[0]["nav_date"])

            except Exception as e:
                failed += 1
                logger.error("[Scheduler] ❌ 早盘补拉 %s 失败: %s", fund_code, e)

        await session.commit()
        logger.info("[Scheduler] 早盘补拉完成 — 成功 %d, 失败 %d, 跳过 %d",
                    updated, failed, len(fund_codes) - len(to_fetch))

        # 更新 daily_return
        if updated > 0:
            dr_updated = 0
            for fund_code in to_fetch:
                try:
                    nav_result = await session.execute(
                        text("SELECT nav FROM fund_nav WHERE fund_code = :code ORDER BY nav_date DESC LIMIT 2"),
                        {"code": fund_code}
                    )
                    rows = nav_result.all()
                    if len(rows) < 2:
                        continue
                    today_nav = float(rows[0][0])
                    yesterday_nav = float(rows[1][0])
                    if yesterday_nav <= 0:
                        continue
                    # 获取 holding_shares 并计算 daily_return = shares * (today_nav - yesterday_nav)
                    hs_result = await session.execute(
                        text("SELECT holding_shares FROM user_portfolio WHERE fund_code = :code"),
                        {"code": fund_code}
                    )
                    hs_row = hs_result.first()
                    if hs_row and hs_row[0]:
                        dr = round(float(hs_row[0]) * (today_nav - yesterday_nav), 2)
                        await session.execute(
                            text("UPDATE user_portfolio SET daily_return = :dr WHERE fund_code = :code"),
                            {"dr": dr, "code": fund_code}
                        )
                        dr_updated += 1
                except Exception as e:
                    logger.warning("[Scheduler] 早盘补拉 %s daily_return 失败: %s", fund_code, e)
            logger.info("[Scheduler] 早盘补拉 daily_return 更新 — %d 只", dr_updated)


# ============================================================
# 修复⑤: 启动时自检持仓基金 nav 深度，不足60天自动补365天
# ============================================================

async def _startup_nav_depth_check() -> None:
    """
    服务启动时自检：对所有持仓基金检查 fund_nav 数据深度。
    不足60天（MACD计算所需）的基金自动补填365天历史数据。
    确保趋势卫士 MACD 不会因数据不足而全部返回"中性"。
    """
    import tushare as ts
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType
    from app.core.database import get_async_engine
    from app.models.fund_nav import FundNav
    from app.models.user_portfolio import UserPortfolio
    from app.core.config import settings
    from app.utils.code_format import to_tushare
    from datetime import date as date_type, timedelta

    MIN_DEPTH = 60

    logger.info("[Startup] 开始持仓基金 nav 深度自检...")

    if not settings.TUSHARE_TOKEN:
        logger.warning("[Startup] TUSHARE_TOKEN 未配置，跳过 nav 自检")
        return

    try:
        pro = ts.pro_api(settings.TUSHARE_TOKEN)
    except Exception as e:
        logger.error("[Startup] Tushare 初始化失败: %s", e)
        return

    engine = get_async_engine()
    async with AsyncSessionType(engine) as session:
        result = await session.execute(select(UserPortfolio.fund_code).distinct())
        fund_codes = [row[0] for row in result.all()]

        if not fund_codes:
            logger.info("[Startup] 无持仓基金，跳过自检")
            return

        needs_backfill = []
        for fund_code in fund_codes:
            cnt_result = await session.execute(
                select(func.count()).where(FundNav.fund_code == fund_code)
            )
            count = cnt_result.scalar() or 0
            if count < MIN_DEPTH:
                needs_backfill.append((fund_code, count))
                logger.info("[Startup] %s: %d条 < %d(阈值)，需要补填", fund_code, count, MIN_DEPTH)
            else:
                logger.info("[Startup] %s: %d条 OK", fund_code, count)

        if not needs_backfill:
            logger.info("[Startup] 所有持仓基金 nav 深度充足")
            return

        logger.info("[Startup] 需补填 %d 只基金...", len(needs_backfill))

        today = date_type.today()
        start_str = (today - timedelta(days=400)).strftime("%Y%m%d")
        end_str = today.strftime("%Y%m%d")

        total_inserted = 0
        for fund_code, current_count in needs_backfill:
            try:
                ts_code = to_tushare(fund_code)
                base_code = ts_code.split('.')[0]
                primary_suffix = ts_code.split('.')[-1]
                suffixes = [primary_suffix]
                if primary_suffix == 'OF':
                    suffixes.extend(['SH', 'SZ'])

                df = None
                for suf in suffixes:
                    try_code = f"{base_code}.{suf}"
                    try:
                        df = pro.fund_nav(ts_code=try_code, start_date=start_str, end_date=end_str)
                        if df is not None and not df.empty:
                            break
                    except Exception:
                        continue

                if df is None or df.empty:
                    logger.warning("[Startup] %s 无法获取净值数据", fund_code)
                    continue

                inserted = 0
                for _, row in df.iterrows():
                    nav_date = str(row['nav_date'])
                    nav_val = float(row['unit_nav'])
                    existing = await session.execute(
                        select(FundNav).where(
                            FundNav.fund_code == fund_code,
                            FundNav.nav_date == nav_date
                        )
                    )
                    if existing.scalar_one_or_none() is None:
                        session.add(FundNav(
                            fund_code=fund_code,
                            nav_date=nav_date,
                            nav=nav_val,
                        ))
                        await session.flush()
                        inserted += 1

                total_inserted += inserted
                logger.info("[Startup] %s 补填完成: %d条(新增%d条)", fund_code, len(df), inserted)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error("[Startup] %s 补填失败: %s", fund_code, e)

        await session.commit()
        logger.info("[Startup] nav 自检完成: 补填%d只基金, 新增%d条", len(needs_backfill), total_inserted)
