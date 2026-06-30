"""
Position Service - V5.0 仓位管理核心业务逻辑
包含仓位建议（5×7 矩阵）、仓位执行（市值变更）、定投建议
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.position_v5 import PositionEngineV5
from app.engine.dca_advice import DcaAdviceEngine
from app.services.sentiment_service import SentimentService

logger = logging.getLogger(__name__)


class PositionService:
    """
    V5.0 仓位管理 Service

    职责：
    1. 仓位建议计算（5×7 矩阵 + 置信度修正 + 成本校验）
    2. 仓位执行（市值变更、记录 execution log）
    3. 持仓市值更新（行内编辑）
    4. 定投建议（DcaAdviceEngine）
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.position_engine = PositionEngineV5(db_session)
        self.dca_engine = DcaAdviceEngine()
        self.sentiment_service = SentimentService(db_session)

    async def get_position_advice(
        self,
        user_id: str,
        fund_code: str,
        current_position_pct: float,
    ) -> dict:
        """
        获取 V5.0 仓位调整建议

        输入：fund_code + current_position_pct
        输出：PositionAdvice（5×7 矩阵 + 置信度修正 + 成本校验）
        """
        # 获取市场信号（默认用 SH000300 沪深300）
        index_code = "SH000300"
        result = await self.sentiment_service.run_pipeline(index_code)

        if "error" in result:
            return {"code": 500, "data": None, "message": "无法获取市场信号"}

        signal_level = result["signal_level"]
        confidence_stars = result["confidence_stars"]
        regime = result.get("regime", "sideways")

        # 计算仓位建议
        advice = await self.position_engine.calculate(
            user_id=user_id,
            fund_code=fund_code,
            current_position_pct=current_position_pct,
            signal_level=signal_level,
            confidence_stars=confidence_stars,
            regime=regime,
        )

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

        记录执行日志，更新用户持仓
        """
        from app.models.position_execution import PositionExecution
        from app.models.user_portfolio import UserPortfolio

        # 从 DB 查询用户实际持仓占比
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

        仅更新 market_value 字段，自动重算 total_return / return_rate
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

        基于信号等级生成定投倍数和操作建议：
        - S+ → 3倍定投（极度恐慌，加速建仓）
        - S  → 2倍定投（恐慌，加码定投）
        - A  → 1.5倍定投（偏恐慌，适度加仓）
        - B  → 1倍标准定投（中性）
        - C  → 0.5倍定投（偏贪婪，减半）
        - D  → 暂停定投（贪婪，等待回调）
        - E  → 建议赎回（极度贪婪，崩盘风险）
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
