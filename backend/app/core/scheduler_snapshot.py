"""
每日决策快照任务 - 固化每天系统给出的最终信号、评级、仓位建议和风控状态

V5.2 更新：
- 持仓基金不再手动拼宽基pipeline，改用 PositionService.get_position_advice()
  自动走板块/宽基双路径
- 新增 nav（最新净值）字段，从 fund_nav 表读取

执行时间：17:05（在因子16:00、净值17:00之后，缓存预热17:30之前）
遍历宽基指数、板块、持仓基金，调用现有计算接口获取最终输出，批量写入 daily_signal_snapshot 表。
"""
import asyncio
import logging
import time
import json
from datetime import date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_engine
from app.models.daily_signal_snapshot import DailySignalSnapshot
from app.models.user_portfolio import UserPortfolio
from app.models.market_sentiment import MarketSentiment

logger = logging.getLogger(__name__)


# ── 中英文翻译映射 ──
TYPE_CN = {"broad": "宽基指数", "sector": "板块", "fund": "基金"}
TRACK_CN = {"contrarian": "逆向轨道", "trend_follow": "趋势轨道", "excluded": "排除轨道"}
RATING_CN = {"watch": "观望", "buy": "可建仓", "strong_buy": "强力建仓", "avoid": "回避"}
ACTION_CN = {"increase": "加仓", "hold": "持有", "decrease": "减仓", "sell": "清仓"}
STATUS_CN = {"normal": "正常", "warning": "预警", "stop_loss": "止损", "forbidden": "禁止建仓"}


async def _run_signal_snapshot() -> None:
    """
    每日决策快照任务：遍历所有宽基、板块、持仓基金，
    调用现有计算接口拿到当日最终输出，批量写入 daily_signal_snapshot 表。

    V5.2: 持仓基金使用 PositionService 双路径（板块→板块缓存，宽基→pipeline）。
    执行时间：17:05（因子16:00、净值17:00已完成，数据已就绪）。
    """
    # 假日智能跳过
    from app.utils.data_source import data_source
    try:
        test_data = await data_source.get_all_index_data()
        if not test_data:
            logger.info("[Snapshot] 今日无交易数据，跳过快照")
            return
    except Exception:
        logger.info("[Snapshot] 数据源检测失败，继续执行")

    today = date.today()
    engine = get_async_engine()
    total_written = 0
    start_time = time.time()

    logger.info("[Snapshot] 开始每日决策快照 - %s", today.isoformat())

    # === Part 1: 宽基指数快照 ===
    # 直接从 market_sentiment 表读取当天已入库的数据
    broad_written = 0
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(MarketSentiment).where(MarketSentiment.trade_date == today)
        )
        rows = result.scalars().all()

        for row in rows:
            existing = await session.execute(
                select(DailySignalSnapshot).where(
                    DailySignalSnapshot.snapshot_date == today,
                    DailySignalSnapshot.target_code == row.index_code,
                )
            )
            snap = existing.scalar_one_or_none()

            if snap is None:
                snap = DailySignalSnapshot(
                    snapshot_date=today,
                    target_code=row.index_code,
                    target_name=row.index_name,
                    target_type="broad",
                )
                session.add(snap)

            # 更新字段
            snap.composite_score = row.composite_score
            snap.signal_level = row.signal_level
            snap.confidence_stars = row.confidence_stars
            snap.factor_std = row.factor_std
            snap.regime = getattr(row, "regime", None) or row.trend_direction
            snap.triggered_defenses = row.triggered_defenses
            # 宽基指数没有持仓相关字段
            snap.track_type = None
            snap.position_rating = None
            snap.target_position_pct = None
            snap.nav = None
            snap.action_advice = None
            snap.overall_status = None
            snap.gate_1_triggered = 0
            snap.gate_2_triggered = 0
            snap.gate_e_triggered = 0

            broad_written += 1

        await session.commit()

    logger.info("[Snapshot]   broad: %d rows", broad_written)
    total_written += broad_written

    # === Part 2: 板块快照（暂跳过，板块数据结构不匹配）===
    # sector_sentiment DB表缺少 signal_level/confidence_stars/regime 等字段，
    # 完整数据在 Redis 缓存 v5:sector:sentiment 中。
    # 板块数据已体现在持仓基金快照中（通过 PositionService 双路径），
    # 后续可单独从缓存提取板块行。
    logger.info("[Snapshot]   sector: skipped (use sector sentiment cache via fund path)")

    # === Part 3: 持仓基金快照 (核心) ===
    # V5.2: 使用 PositionService.get_position_advice() 获取双路径数据
    # - 板块基金(801xxx) → 从 sector sentiment 缓存读取板块 signal/confidence/score
    # - 宽基基金 → 跑宽基 14因子 pipeline
    # - regime 均来自沪深300（宏观上下文）
    fund_written = 0
    fund_failed = 0

    async with AsyncSession(engine) as session:
        # 获取持仓基金列表
        result = await session.execute(
            select(UserPortfolio).where(UserPortfolio.user_id == "demo_user")
        )
        portfolios = result.scalars().all()

        if not portfolios:
            logger.info("[Snapshot] no portfolio funds, skip")
        else:
            # 用户现金和总资产
            from app.models.user_cash import UserCash
            cash_result = await session.execute(
                select(UserCash).where(UserCash.user_id == "demo_user")
            )
            cash_row = cash_result.scalar_one_or_none()
            cash_amount = float(cash_row.cash_amount) if cash_row and cash_row.cash_amount else 0.0
            total_assets = sum(float(p.market_value or 0) for p in portfolios) + cash_amount

            # 初始化 PositionService（双路径逻辑）
            from app.services.position_service import PositionService
            pos_service = PositionService(session)

            for pf in portfolios:
                try:
                    fund_code = pf.fund_code
                    current_pct = float(pf.weight_pct or 0)

                    # ── 调用 PositionService 获取完整双路径数据 ──
                    advice_result = await pos_service.get_position_advice(
                        user_id="demo_user",
                        fund_code=fund_code,
                        current_position_pct=current_pct,
                        cash_amount=cash_amount,
                        total_assets=total_assets,
                    )

                    if advice_result.get("code") != 0 or not advice_result.get("data"):
                        fund_failed += 1
                        logger.error("[Snapshot]   fund %s PositionService failed", fund_code)
                        continue

                    advice = advice_result["data"]

                    # 提取核心字段
                    signal_level = advice.get("signal_level", "B")
                    confidence_stars = advice.get("confidence_stars", 2)
                    composite_score = advice.get("composite_score", 50.0)
                    regime = advice.get("regime", "sideways")
                    sentiment_source = advice.get("sentiment_source", "broad")
                    track_type = advice.get("track_type")
                    position_rating = advice.get("position_rating")
                    target_position_pct = advice.get("target_position_pct")
                    action_advice = advice.get("action")
                    advice_reason = advice.get("reason")
                    overall_status = advice.get("overall_status", "normal")
                    frequency_block_direction = advice.get("frequency_block_direction")

                    # 趋势卫士数据
                    tg = advice.get("trend_guard", {})
                    macd_detail = tg.get("macd_detail", {})
                    macd_state = macd_detail.get("signal")
                    drawdown_pct = tg.get("current_drawdown_pct")
                    gates = advice.get("gates", {})
                    g1 = gates.get("gate_1", {})
                    g2 = gates.get("gate_2", {})
                    ge = gates.get("gate_e", {})
                    gate_1_triggered = 1 if g1.get("triggered", False) else 0
                    gate_2_triggered = 1 if g2.get("triggered", False) else 0
                    gate_e_triggered = 1 if ge.get("triggered", False) else 0
                    gate_1_dist = g1.get("current_distance_pct")
                    gate_2_dist = g2.get("current_distance_pct")

                    # ── 读取最新净值 ──
                    nav_value = None
                    nav_result = await session.execute(
                        text(
                            "SELECT nav FROM fund_nav "
                            "WHERE fund_code = :code AND nav_date <= :today "
                            "ORDER BY nav_date DESC LIMIT 1"
                        ),
                        {"code": fund_code, "today": today},
                    )
                    nav_row = nav_result.first()
                    if nav_row and nav_row[0]:
                        nav_value = float(nav_row[0])

                    # ── 建仓评级 ──
                    if not position_rating:
                        try:
                            from app.engine.position_rating import calculate_position_rating
                            rating_result = calculate_position_rating(
                                fund_code=fund_code,
                                signal_level=signal_level,
                                confidence_stars=confidence_stars,
                                overall_status=overall_status,
                                sector_track=track_type,
                            )
                            position_rating = rating_result.rating if rating_result else "watch"
                        except Exception:
                            position_rating = "watch"

                    # ── 写入快照 ──
                    existing = await session.execute(
                        select(DailySignalSnapshot).where(
                            DailySignalSnapshot.snapshot_date == today,
                            DailySignalSnapshot.target_code == fund_code,
                        )
                    )
                    snap = existing.scalar_one_or_none()

                    if snap is None:
                        snap = DailySignalSnapshot(
                            snapshot_date=today,
                            target_code=fund_code,
                            target_name=pf.fund_name or fund_code,
                            target_type="fund",
                        )
                        session.add(snap)

                    snap.composite_score = composite_score
                    snap.signal_level = signal_level
                    snap.confidence_stars = confidence_stars
                    snap.track_type = track_type
                    snap.position_rating = position_rating
                    snap.target_position_pct = target_position_pct
                    snap.nav = nav_value
                    snap.sentiment_source = sentiment_source
                    snap.action_advice = action_advice
                    snap.overall_status = overall_status
                    snap.gate_1_triggered = gate_1_triggered
                    snap.gate_2_triggered = gate_2_triggered
                    snap.gate_e_triggered = gate_e_triggered
                    snap.gate_1_distance_pct = gate_1_dist
                    snap.gate_2_distance_pct = gate_2_dist
                    snap.drawdown_pct = drawdown_pct
                    snap.factor_std = advice.get("factor_std")
                    snap.regime = regime
                    snap.macd_state = macd_state
                    snap.advice_reason = advice_reason
                    snap.frequency_block_direction = frequency_block_direction
                    snap.confidence_detail = json.dumps(advice.get("confidence_detail", {})) if advice.get("confidence_detail") else None
                    snap.triggered_defenses = json.dumps(advice.get("triggered_defenses", [])) if advice.get("triggered_defenses") else None

                    fund_written += 1
                    logger.info(
                        "[Snapshot]   fund %s: signal=%s conf=%d score=%s source=%s "
                        "action=%s nav=%s gate=%s",
                        fund_code, signal_level, confidence_stars, composite_score,
                        sentiment_source, action_advice, nav_value, overall_status,
                    )

                except Exception as e:
                    fund_failed += 1
                    logger.error("[Snapshot]   fund %s failed: %s", pf.fund_code, e, exc_info=True)

            await session.commit()

    logger.info("[Snapshot]   fund: %d ok, %d fail", fund_written, fund_failed)
    total_written += fund_written

    elapsed = time.time() - start_time
    logger.info("[Snapshot] DONE - %d written, %.1fs elapsed", total_written, elapsed)
