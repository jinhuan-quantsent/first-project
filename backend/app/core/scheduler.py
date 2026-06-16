"""
V5.0 定时任务调度器 (APScheduler)

每日收盘后自动运行情绪计算流水线，将快照写入 market_sentiment 表。
"""
import asyncio
import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from app.utils.data_source import DEFAULT_INDEX_CODES

logger = logging.getLogger(__name__)

# 北京时间 15:30 = UTC 07:30
CRON_HOUR = 7
CRON_MINUTE = 30


async def _run_daily_snapshot() -> None:
    """
    每日快照任务：对全部默认指数运行 V5 pipeline 并入库。
    
    仅 Mon-Fri 执行（APScheduler day_of_week=mon-fri），
    pipeline 内部会判断是否为交易日，非交易日数据源无数据则优雅跳过。
    """
    from app.core.database import get_async_engine
    from app.api.v5 import _run_v5_pipeline

    today_str = date.today().isoformat()
    logger.info(f"[Scheduler] 开始每日快照 — {today_str} — {len(DEFAULT_INDEX_CODES)} 个指数")

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
                        f"[Scheduler] ✅ {result.get('index_name', code)} "
                        f"score={result.get('composite_score', '?')} "
                        f"signal={result.get('signal_level', '?')}"
                    )
                else:
                    fail += 1
                    err_msg = result.get("error", "未知错误") if isinstance(result, dict) else "返回异常"
                    logger.warning(f"[Scheduler] ⚠️ {code} 失败: {err_msg}")
        except asyncio.TimeoutError:
            fail += 1
            logger.error(f"[Scheduler] ❌ {code} 超时 (60s)")
        except Exception as e:
            fail += 1
            logger.error(f"[Scheduler] ❌ {code} 异常: {e}")

    logger.info(f"[Scheduler] 快照完成 — 成功 {success}/{len(DEFAULT_INDEX_CODES)}, 失败 {fail}")


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

    # 每个交易日 15:30 执行（APScheduler 使用本地时区 Asia/Shanghai）
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

    scheduler.start()
    logger.info(
        f"[Scheduler] 已启动 — 每日 15:30 北京时间执行 {len(DEFAULT_INDEX_CODES)} 指数快照"
    )
    return scheduler
