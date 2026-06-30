"""
V5.0 定时任务调度器 (APScheduler)

每日收盘后自动运行情绪计算流水线，将快照写入 market_sentiment 表。
"""
import asyncio
import logging
from typing import Optional
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
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
    from app.api.v5 import _run_v5_pipeline

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
                # 字段名映射（score_sectors() 返回 key 与 SectorSentiment 模型对齐）
                sector_code = item.get("sector_code", item.get("code", ""))
                sector_name = item.get("sector_name", item.get("name", ""))

                if not sector_code:
                    continue

                # 查找已有记录（同板块同日期 → 更新而非插入）
                from sqlalchemy import select
                stmt = select(SectorSentiment).where(
                    SectorSentiment.sector_code == sector_code,
                    SectorSentiment.trade_date == today,
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()

                if row is None:
                    row = SectorSentiment(
                        sector_code=sector_code,
                        sector_name=sector_name,
                        trade_date=today,
                    )
                    session.add(row)

                # 更新字段（兼容两种 key 命名）
                row.sector_return    = item.get("sector_return", item.get("return_pct", 0.0))
                row.turnover_ratio  = item.get("turnover_ratio", item.get("turn_over", 0.0))
                row.fund_flow        = item.get("fund_flow", 0.0)
                row.strength_index    = item.get("strength_index", item.get("strength", 50.0))
                row.sentiment_score  = item.get("sentiment_score", item.get("score", 50.0))
                row.sentiment_label  = item.get("sentiment_label", item.get("label", "neutral"))
                row.momentum_5d     = item.get("momentum_5d", 0.0)
                row.momentum_20d    = item.get("momentum_20d", 0.0)
                row.rank             = item.get("strength_rank", item.get("rank", 0))

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

    scheduler.start()
    logger.info(
        "[Scheduler] 已启动 — 每日 15:30 市场快照 | 15:45 板块快照 | 每周日 22:00 建议验证"
    )
    return scheduler
