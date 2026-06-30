"""
FactorDataService 单元测试
覆盖 get_factor_heatmap / get_sectors / get_sector_detail
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.factor_data_service import FactorDataService
from app.services.sentiment_service import SentimentService


@pytest.fixture
def mock_sentiment_service():
    return MagicMock(spec=SentimentService)


@pytest.fixture
def factor_data_service(mock_sentiment_service):
    return FactorDataService(sentiment_service=mock_sentiment_service)


class TestFactorDataServiceInit:
    def test_init_optional_sentiment(self):
        """不传 sentiment_service 也应该可创建（用于不依赖 pipeline 的方法）"""
        service = FactorDataService()
        assert service.sentiment_service is None

    def test_init_stores_sentiment(self, mock_sentiment_service):
        service = FactorDataService(sentiment_service=mock_sentiment_service)
        assert service.sentiment_service is mock_sentiment_service


class TestGetFactorHeatmap:
    """get_factor_heatmap 单元测试"""

    @pytest.mark.asyncio
    async def test_get_factor_heatmap_returns_404_on_error(self, factor_data_service, mock_sentiment_service):
        """pipeline 返回 error 时返回 404"""
        mock_sentiment_service.run_pipeline = AsyncMock(
            return_value={"error": "no index"}
        )
        result = await factor_data_service.get_factor_heatmap("SH000300")
        assert result["code"] == 404
        assert "no index" in result["message"]

    @pytest.mark.asyncio
    async def test_get_factor_heatmap_requires_sentiment(self):
        """不传 sentiment_service 调用 heatmap 应该抛错"""
        service = FactorDataService()
        with pytest.raises(ValueError, match="sentiment_service is required"):
            await service.get_factor_heatmap("SH000300")

    @pytest.mark.asyncio
    async def test_get_factor_heatmap_returns_factors(self, factor_data_service, mock_sentiment_service):
        """正常返回因子列表"""
        mock_factor = MagicMock()
        mock_factor.factor_name = "VOL"
        mock_factor.percentile = 0.65
        mock_factor.sigmoid_score = 70.0
        mock_factor.c_param = 0.5
        mock_factor.k_param = 3.0

        mock_sentiment_service.run_pipeline = AsyncMock(return_value={
            "composite_score": 65.0,
            "signal_level": "A",
            "factor_details": [mock_factor],
            "updated_at": "2026-06-17T10:00:00",
        })
        result = await factor_data_service.get_factor_heatmap("SH000300")
        assert result["code"] == 0
        assert "factors" in result["data"]
        assert len(result["data"]["factors"]) == 1


class TestGetSectors:
    """get_sectors 单元测试"""

    @pytest.mark.asyncio
    async def test_get_sectors_rejects_invalid_type(self, factor_data_service):
        """sector_type 非法时返回 400"""
        result = await factor_data_service.get_sectors(sector_type="invalid")
        assert result["code"] == 400
        assert "concept" in result["message"] or "industry" in result["message"]

    @pytest.mark.asyncio
    async def test_get_sectors_accepts_concept(self, factor_data_service):
        """concept 类型应该被接受"""
        with patch("app.services.factor_data_service.get_sector_list", AsyncMock(return_value={"items": [], "pagination": {}})):
            result = await factor_data_service.get_sectors(sector_type="concept")
            assert result["code"] == 0

    @pytest.mark.asyncio
    async def test_get_sectors_accepts_industry(self, factor_data_service):
        """industry 类型应该被接受"""
        with patch("app.services.factor_data_service.get_sector_list", AsyncMock(return_value={"items": [], "pagination": {}})):
            result = await factor_data_service.get_sectors(sector_type="industry")
            assert result["code"] == 0

    @pytest.mark.asyncio
    async def test_get_sectors_scores_items(self, factor_data_service):
        """有 items 时应该调用 score_sectors"""
        with patch("app.services.factor_data_service.get_sector_list", AsyncMock(return_value={"items": [{"name": "AI", "change_pct": 5.0}], "pagination": {"page": 1}})):
            with patch("app.services.factor_data_service.score_sectors", AsyncMock(return_value=[{"name": "AI", "score": 85}])) as mock_score:
                result = await factor_data_service.get_sectors()
                mock_score.assert_called_once()
                assert result["code"] == 0
                assert result["data"]["items"][0]["score"] == 85


class TestGetSectorDetail:
    """get_sector_detail 单元测试"""

    @pytest.mark.asyncio
    async def test_get_sector_detail_returns_404_when_none(self, factor_data_service):
        """板块不存在时返回 404"""
        with patch("app.services.factor_data_service.get_sector_detail", AsyncMock(return_value=None)):
            result = await factor_data_service.get_sector_detail("BK0001")
            assert result["code"] == 404

    @pytest.mark.asyncio
    async def test_get_sector_detail_returns_data(self, factor_data_service):
        """正常返回板块详情"""
        with patch("app.services.factor_data_service.get_sector_detail", AsyncMock(return_value={"code": "BK0001", "name": "AI"})):
            result = await factor_data_service.get_sector_detail("BK0001")
            assert result["code"] == 0
            assert result["data"]["name"] == "AI"
