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


def _build_threshold_data(preview_result: dict, meta: dict, gszzl: float | None) -> dict:
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
    up_trigger_pct = None
    for b in boundaries:
        if b > yesterday_score:
            if yesterday_score > 0:
                up_trigger_pct = round((b - yesterday_score) / yesterday_score * 100, 1)
            break
    
    down_trigger_pct = None
    if gate_2.get("current_distance_pct") is not None:
        down_trigger_pct = round(abs(gate_2["current_distance_pct"]), 2)
    
    return {
        "gate_zones": gate_zones,
        "safe_zone_note": safe_zone_note,
        "current_score": yesterday_score,
        "up_trigger_pct": up_trigger_pct,
        "down_trigger_pct": down_trigger_pct,
    }


# ============================================================
# 任务 16：盘中预演计算（交易时段内每5分钟执行）
# ============================================================
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

    # 5. 获取昨日收盘数据（从DailySignalSnapshot）
    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.isoformat()
    
    async with AsyncSession(engine) as session:
        snap_stmt = select(DailySignalSnapshot).where(
            DailySignalSnapshot.snapshot_date == yesterday
        )
        snap_result = await session.execute(snap_stmt)
        yesterday_snapshots = {s.target_code: s for s in snap_result.scalars().all()}

    success = 0
    for user_id, data in user_funds.items():
        total_assets = data["total_mv"]

        for fund_code in data["funds"]:
            try:
                # 5a. 获取基金实时估值
                gszzl = await get_fund_realtime_nav(fund_code)

                # 5b. 从Redis读取元数据
                meta_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:meta:{fund_code}"
                meta = await cache_get(meta_key)
                if not meta:
                    logger.warning("[Scheduler] [preview] %s 元数据缺失，跳过", fund_code)
                    continue

                # 5c. 获取昨日收盘数据
                snap = yesterday_snapshots.get(fund_code)
                if snap:
                    yesterday_score = float(snap.composite_score or 50.0)
                    yesterday_signal = snap.signal_level or "B"
                    yesterday_confidence = snap.confidence_stars or 3
                else:
                    # 无昨日快照（可能是新加入的基金）-- 从Redis缓存读
                    sector_code = meta.get("sector_code")
                    if sector_code and sector_code.startswith("801"):
                        sector_cache = await cache_get(f"v5:sector:sentiment:{sector_code}")
                        if isinstance(sector_cache, dict):
                            yesterday_score = float(sector_cache.get("score", 50.0))
                            yesterday_signal = sector_cache.get("signal", "B")
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
                    pos_engine = PositionEngineV5(session)
                    preview_result = await pos_engine.calculate(
                        user_id=user_id,
                        fund_code=fund_code,
                        current_position_pct=current_pct,
                        signal_level=preview_signal,
                        confidence_stars=preview_confidence,
                        regime=meta.get("regime", "sideways"),
                        cash_amount=0,  # 盘中不查现金
                        total_assets=total_assets,
                    )

                    # 5g. 组装预演结果
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
                        "elasticity": round(elasticity, 2) if elasticity is not None else None,
                        
                        # 预演操作建议
                        "action": preview_result.get("action", "hold"),
                        "target_position_pct": preview_result.get("target_position_pct", 0),
                        "current_position_pct": preview_result.get("current_position_pct", current_pct),
                        "reason": _prefix_preview_reason(preview_result.get("reason", "")),
                        "signal_level": preview_signal,
                        "confidence_stars": preview_confidence,
                        
                        # 预演风控
                        "gates": preview_result.get("gates"),
                        "track_type": preview_result.get("track_type"),
                        "sector_track": preview_result.get("sector_track"),
                        
                        # 阈值数据
                        "thresholds": _build_threshold_data(preview_result, meta, gszzl),
                        
                        # 昨今对比
                        "yesterday_signal": yesterday_signal,
                        "yesterday_confidence": yesterday_confidence,
                        "signal_change": _calc_signal_change(yesterday_signal, preview_signal),
                    }

                    # 5h. 写入Redis
                    cache_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:{fund_code}:{user_id}"
                    await cache_set(cache_key, preview_output, ttl=settings.INTRADAY_PREVIEW_CACHE_TTL)

                    success += 1
                    logger.info("[Scheduler] [preview] %s: score=%.1f->%.1f signal=%s->%s gszzl=%.2f action=%s",
                               fund_code, yesterday_score, preview_score, yesterday_signal, preview_signal,
                               gszzl or 0, preview_result.get("action", "hold"))
            except Exception as e:
                logger.error("[Scheduler] [preview] %s FAIL: %s", fund_code, e)

    logger.info("[Scheduler] 盘中预演计算完成 -- %d 成功", success)

# 任务 14：盘中预演元数据打包（15:40 — 收盘后，在快照15:30+板块价格15:35之后）
# ============================================================
async def _run_intraday_meta_pack() -> None:
    """
    盘中预演元数据打包 -- 收盘后15:40执行

    将 MA20价格/MACD状态/轨道类型/冷却期/regime/矩阵/板块黑名单
    打包写入 Redis intraday_preview:v1:meta:{date}:{fund_code}

    数据来源：
    - MA20价格: fund_nav 计算（需>=60条，使用 trend_guard._calculate_ma20_trend）
    - MACD状态: trend_guard._calculate_macd 纯计算函数
    - 轨道类型: trend_guard._get_sector_track() -- 同步函数，需asyncio.to_thread包装
    - 冷却期: PositionExecution DB表查询
    - regime: 沪深300 fsa:sentiment 缓存
    - 矩阵/置信度映射: config.py 已有
    """
    from app.core.database import get_async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user_portfolio import UserPortfolio
    from app.models.position_execution import PositionExecution
    from app.models.fund_nav import FundNav
    from app.engine.trend_guard import _calculate_ma20_trend, _calculate_macd
    from app.engine.trend_guard import _get_sector_track, _get_fund_sector_code
    from app.core.redis_client import cache_get, cache_set

    if not settings.ENABLE_INTRADAY_PREVIEW:
        logger.info("[Scheduler] 盘中预演全局关闭，跳过元数据打包")
        return

    # 检查Redis全局开关
    redis_switch = await cache_get("intraday_preview:global_switch")
    if redis_switch == "off":
        logger.info("[Scheduler] Redis全局开关关闭，跳过元数据打包")
        return

    today = date.today()
    today_str = today.isoformat()
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
        try:
            async with AsyncSession(engine) as session:
                # 1. MA20价格 -- 从 fund_nav 表获取最近60条
                nav_stmt = select(FundNav.nav, FundNav.nav_date).where(
                    FundNav.fund_code == fund_code
                ).order_by(FundNav.nav_date.desc()).limit(60)
                nav_result = await session.execute(nav_stmt)
                nav_rows = nav_result.all()

                if len(nav_rows) < 20:
                    logger.warning("[Scheduler] %s nav数据不足(%d<20)，跳过MA20", fund_code, len(nav_rows))
                    continue

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
                    "packed_at": datetime.now().isoformat(),
                }

                cache_key = f"{settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{today_str}:meta:{fund_code}"
                await cache_set(cache_key, meta, ttl=86400)  # TTL=1天，次日重新打包

                success += 1
                logger.info("[Scheduler] [meta] %s OK (ma20=%s, track=%s, regime=%s, cooldown=%dd)",
                           fund_code, ma20_trend, sector_track, regime, cooldown_days)
        except Exception as e:
            logger.error("[Scheduler] [meta] %s FAIL: %s", fund_code, e)

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
    from app.models.factor_history import FactorHistory
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
                stmt = select(FactorHistory).where(
                    FactorHistory.fund_code == fund_code,
                    FactorHistory.trade_date >= today - timedelta(days=10)  # 10天窗口确保5个交易日
                ).order_by(FactorHistory.trade_date.desc()).limit(5)
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

                    score_delta = float(today_row.score or 0) - float(yesterday_row.score or 0)

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

    scheduler.start()
    logger.info(
        "[Scheduler] 已启动 — 14:30/14:45/15:00 实时估值 | 15:30 市场快照 | 15:45 板块快照 | 16:00 因子更新 | 16:05 基金净值(crontab) | 17:00 净值更新 | 17:05 决策快照 | 15:35 板块价格 | 15:50 指数情绪映射 | 16:15 融资融券 | 17:30 缓存刷新 | 22:00 净值复查 | 数据就绪检查 16:30/17:00/17:30/18:00 | 9:30-15:00 盘中预演(5min) | 15:40 预演元数据 | 周五17:35 弹性系数周更 | 15:50 对账校准 | 每周日 22:00 建议验证"
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
