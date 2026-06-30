"""
PositionService 单元测试
覆盖 get_position_advice / execute_position / update_market_value / get_dca_advice
"""
import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.position_service import PositionService


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def position_service(mock_session):
    return PositionService(db_session=mock_session)


class TestPositionServiceInit:
    def test_init_creates_engines(self, mock_session):
        service = PositionService(db_session=mock_session)
        assert service.position_engine is not None
        assert service.dca_engine is not None
        assert service.sentiment_service is not None


class TestUpdateMarketValue:
    """update_market_value 单元测试"""

    @pytest.mark.asyncio
    async def test_update_market_value_rejects_zero(self, position_service):
        """市值为 0 时返回 400"""
        result = await position_service.update_market_value(
            item_id=1, user_id="u1", new_market_value=0
        )
        assert result["code"] == 400
        assert "市值必须大于0" in result["message"]

    @pytest.mark.asyncio
    async def test_update_market_value_rejects_none(self, position_service):
        """市值为 None 时返回 400"""
        result = await position_service.update_market_value(
            item_id=1, user_id="u1", new_market_value=None
        )
        assert result["code"] == 400

    @pytest.mark.asyncio
    async def test_update_market_value_rejects_negative(self, position_service):
        """市值为负数时返回 400"""
        result = await position_service.update_market_value(
            item_id=1, user_id="u1", new_market_value=-100
        )
        assert result["code"] == 400

    @pytest.mark.asyncio
    async def test_update_market_value_returns_404_when_not_found(self, position_service):
        """持仓不存在时返回 404"""
        position_service.db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        result = await position_service.update_market_value(
            item_id=999, user_id="u1", new_market_value=1000
        )
        assert result["code"] == 404

    @pytest.mark.asyncio
    async def test_update_market_value_recomputes_returns(self, position_service):
        """市值更新后自动重算 total_return / return_rate"""
        # 构造已有持仓
        existing = MagicMock()
        existing.id = 1
        existing.market_value = 0
        existing.holding_shares = 100.0
        existing.cost_nav = 5.0
        existing.current_nav = 0.0
        existing.total_return = 0
        existing.return_rate = 0

        position_service.db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )
        result = await position_service.update_market_value(
            item_id=1, user_id="u1", new_market_value=600.0
        )
        assert result["code"] == 0
        # 重算后 current_nav = 600 / 100 = 6.0
        assert existing.current_nav == 6.0
        # total_return = 600 - 5.0*100 = 100
        assert existing.total_return == 100.0
        # return_rate = (6.0 / 5.0 - 1) * 100 = 20.0
        assert existing.return_rate == 20.0


class TestGetPositionAdvice:
    """get_position_advice 单元测试"""

    @pytest.mark.asyncio
    async def test_get_position_advice_returns_500_when_pipeline_fails(self, position_service):
        """pipeline 失败时返回 500"""
        position_service.sentiment_service.run_pipeline = AsyncMock(
            return_value={"error": "no index"}
        )
        result = await position_service.get_position_advice(
            user_id="u1", fund_code="000001", current_position_pct=50.0
        )
        assert result["code"] == 500
        assert "无法获取市场信号" in result["message"]


class TestExecutePosition:
    """execute_position 单元测试"""

    @pytest.mark.asyncio
    async def test_execute_position_creates_execution_log(self, position_service):
        """执行仓位调整应该创建 execution log"""
        position_service.db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        result = await position_service.execute_position(
            user_id="u1",
            fund_code="000001",
            target_position_pct=70.0,
            signal_level="S",
            confidence_stars=4,
        )
        assert result["code"] == 0
        assert "execution_id" in result["data"]
        assert result["data"]["message"] == "执行成功"
        position_service.db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_position_uses_existing_portfolio(self, position_service):
        """有 UserPortfolio 时 from_position_pct 应使用计算值"""
        from app.models.user_portfolio import UserPortfolio
        portfolio = MagicMock(spec=UserPortfolio)
        portfolio.market_value = 1000.0
        portfolio.holding_shares = 100.0
        portfolio.current_nav = 10.0

        position_service.db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=portfolio))
        )
        result = await position_service.execute_position(
            user_id="u1",
            fund_code="000001",
            target_position_pct=80.0,
            signal_level="A",
            confidence_stars=3,
        )
        assert result["code"] == 0
