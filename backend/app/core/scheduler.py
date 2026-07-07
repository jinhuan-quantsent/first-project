"""
V5.0 定时任务调度器 (APScheduler)

每日收盘后自动运行情绪计算流水线，将快照写入 market_sentiment 表。
"""
import asyncio
import logging
from typing import Optional
from datetime import date, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.core.scheduler_snapshot import _run_signal_snapshot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.utils.data_source import DEFAULT_INDEX_CODES, data_source

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
    from app.engine.v5 import _run_v5_pipeline

    today_str = date.today().isoformat()
    logger.info("[Scheduler] 开始每日快照 — %s — %d 个指数", today_str, len(DEFAULT_INDEX_CODES))

    engine = get_async_engine()
    success = 0
    fail = 0

    for code in DEFAULT_INDEX_CODES:
        try:
            async with AsyncSession(engine) as session:
                result = await asyncio.wait_for(
                    _run_v5_pipeline(code, trade_date=today_str, db_session=session),
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
                async with session.get("http://localhost:8000/api/v5/sector/sentiment", timeout=aiohttp.ClientTimeout(total=120)) as resp:
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
            async with session.get("http://localhost:8000/api/v5/sector/radar", timeout=aiohttp.ClientTimeout(total=120)) as resp:
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
                        f"http://localhost:8000/api/v5/market/sector/{sc}",
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

    scheduler.start()
    logger.info(
        "[Scheduler] 已启动 — 14:30/14:45/15:00 实时估值 | 15:30 市场快照 | 15:45 板块快照 | 16:00 因子更新 | 16:05 基金净值(crontab) | 17:00 净值更新 | 17:05 决策快照 | 17:30 缓存刷新 | 22:00 净值复查 | 数据就绪检查 16:30/17:00/17:30/18:00 | 每周日 22:00 建议验证"
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

                # 更新 user_portfolio.current_nav
                await session.execute(
                    text("UPDATE user_portfolio SET current_nav = :nav, updated_at = NOW() WHERE fund_code = :code"),
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
                    daily_pct = (today_nav - yesterday_nav) / yesterday_nav
                    # 获取市值并计算 daily_return
                    mv_result = await session.execute(
                        text("SELECT market_value FROM user_portfolio WHERE fund_code = :code"),
                        {"code": fund_code},
                    )
                    mv_row = mv_result.first()
                    if mv_row and mv_row[0]:
                        dr = round(float(mv_row[0]) * daily_pct, 2)
                        await session.execute(
                            text("UPDATE user_portfolio SET daily_return = :dr WHERE fund_code = :code"),
                            {"dr": dr, "code": fund_code},
                        )
                        dr_updated += 1
                except Exception as e:
                    logger.warning("[Scheduler] %s daily_return 更新失败: %s", fund_code, e)
            logger.info("[Scheduler] daily_return 更新完成 — %d 只", dr_updated)

        # ── 更新 weight_pct（组合内权重）──
        # 修复: 之前无更新逻辑，weight_pct 全为 0，导致快照 current_position_pct=0
        try:
            mv_all_result = await session.execute(
                text("SELECT fund_code, market_value FROM user_portfolio")
            )
            mv_rows = mv_all_result.all()
            total_mv = sum(float(r[1] or 0) for r in mv_rows)
            if total_mv > 0:
                wp_updated = 0
                for fund_code, market_value in mv_rows:
                    mv = float(market_value or 0)
                    weight_pct = round(mv / total_mv, 4) if mv > 0 else 0.0
                    await session.execute(
                        text("UPDATE user_portfolio SET weight_pct = :wp WHERE fund_code = :code"),
                        {"wp": weight_pct, "code": fund_code},
                    )
                    wp_updated += 1
                await session.commit()
                logger.info("[Scheduler] weight_pct 更新完成 — %d 只, 总市值=%.2f", wp_updated, total_mv)
            else:
                logger.warning("[Scheduler] 总市值为 0，跳过 weight_pct 更新")
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
        m = re.search(r"jsonpgz\((.*)\\)", raw)
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
                await session.execute(
                    text("UPDATE user_portfolio SET current_nav = :nav WHERE fund_code = :code"),
                    {"nav": nav_val, "code": fund_code}
                )
                mv_row = (await session.execute(
                    text("SELECT market_value FROM user_portfolio WHERE fund_code = :code"),
                    {"code": fund_code}
                )).first()
                if mv_row and mv_row[0]:
                    nav_rows = (await session.execute(
                        text("SELECT nav FROM fund_nav WHERE fund_code = :code ORDER BY nav_date DESC LIMIT 2"),
                        {"code": fund_code}
                    )).all()
                    if len(nav_rows) >= 2:
                        daily_pct = (float(nav_rows[0][0]) - float(nav_rows[1][0])) / float(nav_rows[1][0])
                        dr = round(float(mv_row[0]) * daily_pct, 2)
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
                        inserted += 1

                total_inserted += inserted
                logger.info("[Startup] %s 补填完成: %d条(新增%d条)", fund_code, len(df), inserted)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error("[Startup] %s 补填失败: %s", fund_code, e)

        await session.commit()
        logger.info("[Startup] nav 自检完成: 补填%d只基金, 新增%d条", len(needs_backfill), total_inserted)
