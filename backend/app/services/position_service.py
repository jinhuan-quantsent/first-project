"""
Position Service - V5.0 仓位管理核心业务逻辑
包含仓位建议（5×7 矩阵）、仓位执行（市值变更）、定投建议

V5.2 修复: 板块类基金(801xxx)使用板块自己的 signal/confidence/score，
不再 fallback 到沪深300。宽基类基金保持原有 pipeline 逻辑。
regime（宏观市场体制）始终使用宽基指数，因为宏观环境影响所有板块。
"""
import logging
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.position_v5 import PositionEngineV5
from app.engine.dca_advice import DcaAdviceEngine
from app.services.sentiment_service import SentimentService
from app.utils.code_format import to_display, to_tushare, INDEX_REGISTRY
from app.core.redis_client import cache_get

logger = logging.getLogger(__name__)


class PositionService:
    """
    V5.0 仓位管理 Service（V5.2 修复版）

    职责：
    1. 仓位建议计算（5×7 矩阵 + 置信度修正 + 成本校验）
    2. 仓位执行（市值变更、记录 execution log）
    3. 持仓市值更新（行内编辑）
    4. 定投建议（DcaAdviceEngine）

    V5.2 变更：
    - 板块基金(801xxx) 从 sector sentiment 缓存读取自己的 signal/confidence/score
    - regime 仍用宽基指数（宏观上下文）
    - 宽基基金保持原有 pipeline 逻辑不变
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.position_engine = PositionEngineV5(db_session)
        self.dca_engine = DcaAdviceEngine()
        self.sentiment_service = SentimentService(db_session)

    async def _determine_fund_source(self, fund_code: str) -> dict:
        """
        判断基金的情绪数据来源（板块 or 宽基）

        Returns:
            dict: {
                "source": "sector" | "broad",
                "sector_code": "801180" (if sector),
                "index_code": "SH000300" (if broad),
                "category": "sector" | "theme" | "broad"
            }
        """
        try:
            result = await self.db_session.execute(
                text("SELECT index_code, category FROM fund_mapping WHERE fund_code = :code LIMIT 1"),
                {"code": fund_code},
            )
            row = result.first()
            if row and row[0]:
                raw_code = str(row[0]).split('.')[0]  # 取纯数字部分
                category = row[1] or "sector"
                # 板块代码 (801xxx) → 用板块数据
                if raw_code.startswith('801'):
                    return {
                        "source": "sector",
                        "sector_code": raw_code,
                        "index_code": None,
                        "category": category,
                    }
                # 检查是否为宽基指数
                ts_code = to_tushare(raw_code)
                if ts_code in set(INDEX_REGISTRY.keys()):
                    return {
                        "source": "broad",
                        "sector_code": None,
                        "index_code": to_display(ts_code),
                        "category": "broad",
                    }
                # 其他非宽基指数 → fallback 到沪深300（用宽基 pipeline）
                logger.info(f"基金 {fund_code} 映射到 {ts_code}（非宽基指数），fallback 到 SH000300")
        except Exception as e:
            logger.warning(f"_determine_fund_source 查询失败: {e}")

        # 默认 fallback: 宽基（沪深300）
        return {
            "source": "broad",
            "sector_code": None,
            "index_code": "SH000300",
            "category": "broad",
        }

    async def _get_sector_sentiment(self, sector_code: str) -> dict | None:
        """
        从 Redis 缓存读取板块情绪数据

        Returns:
            dict with keys: signal_level, confidence_stars, sentiment_score,
                           confidence_detail, track, triggered_defenses
            None if not found
        """
        try:
            cache_key = "v5:sector:sentiment"
            cached = await cache_get(cache_key)
            if cached and isinstance(cached, dict):
                data = cached.get("data", cached)
                sectors = data.get("sectors", [])
                for sec in sectors:
                    if str(sec.get("sector_code", "")) == sector_code:
                        return {
                            "signal_level": sec.get("signal_level", "B"),
                            "confidence_stars": sec.get("confidence_stars", 2),
                            "sentiment_score": sec.get("sentiment_score", 50.0),
                            "confidence_detail": sec.get("confidence_detail", {}),
                            "track": sec.get("track", "excluded"),
                            "triggered_defenses": sec.get("triggered_defenses", []),
                            "sector_name": sec.get("sector_name", ""),
                        }
        except Exception as e:
            logger.warning(f"_get_sector_sentiment 缓存读取失败: {e}")
        return None

    async def _get_broad_regime(self) -> str:
        """
        获取宽基市场的 regime（宏观市场体制）

        优先从缓存读取沪深300的 regime；缓存失败则跑 pipeline。
        regime 是宏观上下文，影响所有板块基金的仓位调整幅度。
        """
        try:
            # 先尝试从缓存读取
            cache_key = "fsa:sentiment:SH000300"
            cached = await cache_get(cache_key)
            if cached and isinstance(cached, dict):
                regime = cached.get("regime")
                if regime:
                    return regime
        except Exception:
            pass

        # 缓存失败 → 跑沪深300 pipeline（只取 regime）
        try:
            result = await self.sentiment_service.run_pipeline("SH000300")
            return result.get("regime", "sideways")
        except Exception as e:
            logger.warning(f"_get_broad_regime 沪深300 pipeline 失败: {e}")

        return "sideways"  # 兜底

    async def get_position_advice(
        self,
        user_id: str,
        fund_code: str,
        current_position_pct: float,
        cash_amount: float = 0.0,       # V5.1: 用户可用现金
        total_assets: float = 0.0,      # V5.1: 用户总资产
    ) -> dict:
        """
        获取 V5.0 仓位调整建议（V5.2 修复版）

        V5.2 变更: 板块基金用板块自己的 signal/confidence/score，
        宽基基金用宽基 pipeline。regime 均来自沪深300（宏观上下文）。

        输入：fund_code + current_position_pct
        输出：PositionAdvice（5×7 矩阵 + 置信度修正 + 成本校验）
        """
        # Step 1: 判断基金的情绪数据来源
        fund_source = await self._determine_fund_source(fund_code)

        signal_level = "B"
        confidence_stars = 2
        composite_score = 50.0
        regime = "sideways"
        confidence_detail = {}
        triggered_defenses = []

        if fund_source["source"] == "sector":
            # Step 2a: 板块基金 → 从 Redis 缓存读取板块情绪
            sector_data = await self._get_sector_sentiment(fund_source["sector_code"])
            if sector_data:
                signal_level = sector_data["signal_level"]
                confidence_stars = sector_data["confidence_stars"]
                composite_score = sector_data["sentiment_score"]
                confidence_detail = sector_data.get("confidence_detail", {})
                triggered_defenses = sector_data.get("triggered_defenses", [])
                logger.info(
                    f"[V5.2] 基金 {fund_code} → 板块 {fund_source['sector_code']} "
                    f"({sector_data.get('sector_name', '')}): "
                    f"signal={signal_level}, confidence={confidence_stars}星, "
                    f"score={composite_score}"
                )
            else:
                # 板块缓存不存在 → fallback 到宽基 pipeline
                logger.warning(
                    f"[V5.2] 基金 {fund_code} → 板块 {fund_source['sector_code']} "
                    f"缓存数据缺失，fallback 到沪深300 pipeline"
                )
                broad_result = await self.sentiment_service.run_pipeline("SH000300")
                if "error" not in broad_result:
                    signal_level = broad_result["signal_level"]
                    confidence_stars = broad_result["confidence_stars"]
                    composite_score = broad_result["composite_score"]
                    confidence_detail = broad_result.get("confidence_detail", {})
                    triggered_defenses = broad_result.get("defenses_triggered", [])

            # regime 始终用宽基宏观上下文
            regime = await self._get_broad_regime()

        else:
            # Step 2b: 宽基基金 → 跑宽基 pipeline
            index_code = fund_source["index_code"] or "SH000300"
            result = await self.sentiment_service.run_pipeline(index_code)

            if "error" in result:
                return {"code": 500, "data": None, "message": "无法获取市场信号"}

            signal_level = result["signal_level"]
            confidence_stars = result["confidence_stars"]
            composite_score = result["composite_score"]
            regime = result.get("regime", "sideways")
            confidence_detail = result.get("confidence_detail", {})
            triggered_defenses = result.get("defenses_triggered", [])

        # Step 3: 计算仓位建议
        advice = await self.position_engine.calculate(
            user_id=user_id,
            fund_code=fund_code,
            current_position_pct=current_position_pct,
            signal_level=signal_level,
            confidence_stars=confidence_stars,
            regime=regime,
            cash_amount=cash_amount,
            total_assets=total_assets,
        )

        # 组装市场现状描述
        regime_cn = {
            "bull": "牛市", "bear": "熊市",
            "sideways": "震荡", "extreme_volatility": "极端波动",
        }.get(regime, "震荡")

        signal_label_map = {
            "S+": "极度恐惧", "S": "恐惧", "A": "谨慎",
            "B": "中性", "C": "乐观", "D": "极度乐观", "E": "极度贪婪",
        }
        signal_label = signal_label_map.get(signal_level, "中性")

        # 区分板块和宽基的描述文案
        if fund_source["source"] == "sector":
            sector_name = ""
            if sector_data:
                sector_name = sector_data.get("sector_name", fund_source["sector_code"])
            market_status = (
                f"大盘{regime_cn}，{sector_name}板块情绪{signal_label}（{signal_level}），"
                f"综合评分{composite_score:.1f}"
            )
        else:
            market_status = (
                f"大盘{regime_cn}，情绪{signal_label}（{signal_level}），"
                f"综合评分{composite_score:.1f}"
            )

        advice["market_status"] = market_status
        advice["regime"] = regime
        advice["composite_score"] = composite_score
        advice["sentiment_source"] = fund_source["source"]  # "sector" or "broad"
        advice["confidence_detail"] = confidence_detail
        advice["triggered_defenses"] = triggered_defenses

        # 注入 track_type 到顶层
        tg_gates = advice.get("trend_guard", {})
        if isinstance(tg_gates, dict) and "gates" in advice:
            tg_gates = advice.get("gates", {})
        if isinstance(tg_gates, dict) and "sector_track" in tg_gates:
            advice["track_type"] = tg_gates.get("sector_track")
        elif isinstance(tg_gates, dict):
            inner_tg = tg_gates.get("trend_guard", {})
            if isinstance(inner_tg, dict):
                advice["track_type"] = inner_tg.get("sector_track")
            else:
                advice["track_type"] = None
        else:
            advice["track_type"] = None

        # 确保 trend_guard_text 字段存在
        if "trend_guard_text" not in advice:
            tg = advice.get("trend_guard", {})
            if tg:
                advice["trend_guard_text"] = tg.get("trend_narrative", "") or tg.get("operation_suggestion", "")
            else:
                advice["trend_guard_text"] = ""

        # A1修复：检测数据不可用情况
        tg_data = advice.get("trend_guard", {})
        if tg_data and tg_data.get("oscillation_silence") and "数据不足" in tg_data.get("operation_suggestion", ""):
            advice["data_warning"] = "数据源暂时不可用，净值历史数据不足，趋势卫士建议仅供参考"
            advice["trend_guard_text"] = "⚠️ " + advice.get("data_warning", "")

        # 确保 reason 字段存在
        if not advice.get("reason"):
            advice["reason"] = "暂无操作建议"

        # 确保 track_type 最终在 advice 里
        if advice.get("track_type") is None:
            tg = advice.get("trend_guard", {})
            if isinstance(tg, dict):
                advice["track_type"] = tg.get("sector_track")
                if "gate_1" in tg and "gates" not in advice:
                    advice["gates"] = tg

        return {"code": 0, "data": advice, "message": "ok"}

    async def execute_position(
        self,
        user_id: str,
        fund_code: str,
        target_position_pct: float,
        signal_level: str,
        confidence_stars: int,
    ) -> dict:
        """
        执行 V5.0 仓位调整
        """
        from app.models.position_execution import PositionExecution
        from app.models.user_portfolio import UserPortfolio

        from_position_pct = 0.0
        try:
            stmt = (
                select(UserPortfolio)
                .where(
                    UserPortfolio.user_id == user_id,
                    UserPortfolio.fund_code == fund_code,
                )
                .limit(1)
            )
            result = await self.db_session.execute(stmt)
            portfolio = result.scalar_one_or_none()
            if portfolio and portfolio.market_value and portfolio.holding_shares > 0:
                from_position_pct = round(
                    portfolio.market_value / max(portfolio.holding_shares * portfolio.current_nav, 1.0),
                    4,
                )
        except Exception:
            pass

        execution = PositionExecution(
            user_id=user_id,
            fund_code=fund_code,
            execute_date=date.today(),
            from_position_pct=from_position_pct,
            to_position_pct=target_position_pct,
            signal_level=signal_level,
            confidence_stars=confidence_stars,
        )
        self.db_session.add(execution)
        await self.db_session.commit()

        return {
            "code": 0,
            "data": {
                "execution_id": execution.id,
                "message": "执行成功",
            },
            "message": "ok",
        }

    async def update_market_value(
        self,
        item_id: int,
        user_id: str,
        new_market_value: float,
    ) -> dict:
        """
        更新持仓市值（行内编辑用）
        """
        from app.models.user_portfolio import UserPortfolio

        if new_market_value is None or float(new_market_value) <= 0:
            return {"code": 400, "data": None, "message": "市值必须大于0"}

        stmt = select(UserPortfolio).where(
            UserPortfolio.id == item_id, UserPortfolio.user_id == user_id
        )
        result = await self.db_session.execute(stmt)
        existing = result.scalar_one_or_none()

        if not existing:
            return {"code": 404, "data": None, "message": f"持仓 {item_id} 不存在"}

        existing.market_value = round(float(new_market_value), 2)

        # 重算收益
        if existing.holding_shares > 0 and existing.cost_nav > 0:
            existing.current_nav = round(existing.market_value / existing.holding_shares, 4)
            existing.total_return = round(
                existing.market_value - existing.cost_nav * existing.holding_shares, 2
            )
            existing.return_rate = round(
                (existing.current_nav / existing.cost_nav - 1) * 100, 2
            ) if existing.cost_nav > 0 else 0

        await self.db_session.commit()

        # 失效持仓缓存
        from app.core.redis_client import cache_delete
        await cache_delete(f"fsa:portfolio:{user_id}")

        return {
            "code": 0,
            "data": {
                "id": existing.id,
                "market_value": existing.market_value,
                "current_nav": existing.current_nav,
                "total_return": existing.total_return,
                "return_rate": existing.return_rate,
            },
            "message": "更新成功",
        }

    async def get_dca_advice(self, index_code: str) -> dict:
        """
        获取 V5.0 定投调整建议
        """
        result = await self.sentiment_service.run_pipeline(index_code)
        if "error" in result:
            return {"code": 404, "data": None, "message": result["error"]}

        signal_level = result["signal_level"]

        # 生成定投建议
        advice = self.dca_engine.get_advice(signal_level)

        return {
            "code": 0,
            "data": {
                "index_code": index_code,
                "index_name": result.get("index_name", index_code),
                "composite_score": result["composite_score"],
                "signal_level": signal_level,
                "confidence_stars": result["confidence_stars"],
                "regime": result.get("regime", "sideways"),
                "dca": advice.to_dict(),
                "updated_at": result.get("updated_at"),
            },
            "message": "ok",
        }
