"""
SentimentService 单元测试
覆盖 run_pipeline / run_multi_index / get_signal_lights / get_market_snapshot /
     get_factor_radar / get_divergence_alert
"""
import pytest
import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sentiment_service import SentimentService


@pytest.fixture
def mock_session():
    """Mock AsyncSession"""
    session = MagicMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def sentiment_service(mock_session):
    """构造 SentimentService（注入 mock session）"""
    return SentimentService(db_session=mock_session)


class TestSentimentServiceInit:
    """SentimentService 初始化测试"""

    def test_init_creates_required_engines(self, mock_session):
        """Service 初始化应该创建所有引擎实例"""
        service = SentimentService(db_session=mock_session)
        assert service.quantile is not None
        assert service.sigmoid_mapper is not None
        assert service.aggregator is not None
        assert service.signal_mapper is not None
        assert service.confidence_engine is not None
        assert service.history_store is not None
        assert service.macd_engine is not None
        assert service.divergence_detector is not None

    def test_init_stores_db_session(self, mock_session):
        """Service 应该持有 db_session 引用"""
        service = SentimentService(db_session=mock_session)
        assert service.db_session is mock_session


class TestRunPipelineHelper:
    """_run_factor_pipeline 单元测试（Layer 1+2）"""

    @pytest.mark.asyncio
    async def test_run_factor_pipeline_empty_when_no_factors(self, sentiment_service):
        """无注册因子时返回空列表"""
        with patch("app.services.sentiment_service.FACTOR_NAMES", []):
            result = await sentiment_service._run_factor_pipeline("SH000300", "2026-06-17")
            assert result == []

    @pytest.mark.asyncio
    async def test_run_factor_pipeline_handles_fetch_exception(self, sentiment_service):
        """fetch_raw 抛异常时使用 default 值"""
        with patch("app.services.sentiment_service.FACTOR_NAMES", ["VOL"]):
            with patch("app.services.sentiment_service.FACTOR_CLASSES", {"VOL": MagicMock()}):
                mock_factor_cls = MagicMock()
                mock_factor = MagicMock()
                mock_factor.fetch_raw = AsyncMock(side_effect=Exception("network error"))
                mock_factor._get_default_raw_value = MagicMock(return_value=50.0)
                mock_factor.sigmoid_c = 0.50
                mock_factor.sigmoid_k = 3.0
                mock_factor.direction = "fear"
                mock_factor_cls.return_value = mock_factor

                with patch("app.services.sentiment_service.FACTOR_CLASSES", {"VOL": mock_factor_cls}):
                    # 模拟 quantile 返回 0.5
                    sentiment_service.quantile.calc_percentile = AsyncMock(return_value=0.5)
                    result = await sentiment_service._run_factor_pipeline("SH000300", "2026-06-17")
                    assert len(result) == 1
                    assert result[0].factor_name == "VOL"


class TestLoadPrevSignal:
    """_load_prev_signal 单元测试"""

    @pytest.mark.asyncio
    async def test_load_prev_signal_returns_none_when_no_history(self, sentiment_service):
        """无历史信号时返回 (None, None, 0)"""
        sentiment_service.db_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        prev_level, prev_score, consecutive = await sentiment_service._load_prev_signal(
            "SH000300", 60.0
        )
        assert prev_level is None
        assert prev_score is None
        assert consecutive == 0


class TestRunMultiIndex:
    """run_multi_index 单元测试"""

    @pytest.mark.asyncio
    async def test_run_multi_index_handles_empty_results(self, sentiment_service):
        """所有指数返回 None 时降级到默认值"""
        with patch.object(sentiment_service, "run_pipeline", AsyncMock(return_value=None)):
            result = await sentiment_service.run_multi_index(["SH000300"])
            assert result["code"] == 0
            assert "data" in result
            assert "indexes" in result["data"]


class TestHealthService:
    """HealthService 单元测试"""

    def test_check_returns_healthy(self):
        from app.services.health_service import HealthService
        result = HealthService().check()
        assert result["code"] == 0
        assert result["data"]["status"] == "healthy"
        assert result["data"]["service"] == "fund-sentiment-v5"
        assert result["data"]["version"] == "5.0"
        assert "checked_at" in result["data"]

    def test_check_includes_timestamp(self):
        from app.services.health_service import HealthService
        result = HealthService().check()
        ts = result["data"]["checked_at"]
        # ISO 格式时间戳
        assert "T" in ts
        # 至少有日期 + 时间（YYYY-MM-DDTHH:MM:SS）
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)
