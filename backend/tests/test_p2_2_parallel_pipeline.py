"""
P2-2: Pipeline 因子获取并行化测试

验证：
1. _process_single_factor 失败时返回 None（不影响其他）
2. asyncio.gather 并发执行 14 因子
3. 并发版本相对串行版本性能提升（模拟）
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.engine.factor_engine.base import FactorSigmoidResult


class TestParallelPipeline:
    """P2-2 并发 Pipeline 测试"""

    @pytest.mark.asyncio
    async def test_process_single_factor_returns_result(self):
        """单因子处理返回 FactorSigmoidResult"""
        from app.services.sentiment_service import SentimentService

        mock_session = MagicMock()
        service = SentimentService(db_session=mock_session)

        # 构造 mock factor
        mock_factor = MagicMock()
        mock_factor.fetch_raw = AsyncMock(return_value=MagicMock(raw_value=18.0))
        mock_factor._get_default_raw_value = MagicMock(return_value=50.0)
        mock_factor.sigmoid_c = 0.5
        mock_factor.sigmoid_k = 3.0
        mock_factor.direction = "fear"

        service.quantile.calc_percentile = AsyncMock(return_value=0.6)

        result = await service._process_single_factor(
            "VOL", mock_factor, "SH000300", "2026-06-17"
        )
        assert result is not None
        assert result.factor_name == "VOL"
        assert isinstance(result, FactorSigmoidResult)

    @pytest.mark.asyncio
    async def test_process_single_factor_handles_exception(self):
        """fetch_raw 抛异常时使用 default 值（不抛）"""
        from app.services.sentiment_service import SentimentService

        mock_session = MagicMock()
        service = SentimentService(db_session=mock_session)

        mock_factor = MagicMock()
        mock_factor.fetch_raw = AsyncMock(side_effect=Exception("network"))
        mock_factor._get_default_raw_value = MagicMock(return_value=50.0)
        mock_factor.sigmoid_c = 0.5
        mock_factor.sigmoid_k = 3.0
        mock_factor.direction = "fear"

        service.quantile.calc_percentile = AsyncMock(return_value=0.5)

        result = await service._process_single_factor(
            "VOL", mock_factor, "SH000300", "2026-06-17"
        )
        assert result is not None
        assert result.factor_name == "VOL"

    @pytest.mark.asyncio
    async def test_process_single_factor_returns_none_on_catastrophic_error(self):
        """极端错误（quantile 抛错）时返回 None 而非抛异常"""
        from app.services.sentiment_service import SentimentService

        mock_session = MagicMock()
        service = SentimentService(db_session=mock_session)

        mock_factor = MagicMock()
        mock_factor.fetch_raw = AsyncMock(side_effect=Exception("network"))
        # _get_default_raw_value 也抛错
        mock_factor._get_default_raw_value = MagicMock(side_effect=Exception("catastrophic"))
        mock_factor.sigmoid_c = 0.5
        mock_factor.sigmoid_k = 3.0
        mock_factor.direction = "fear"

        service.quantile.calc_percentile = AsyncMock(side_effect=Exception("quantile fail"))

        result = await service._process_single_factor(
            "VOL", mock_factor, "SH000300", "2026-06-17"
        )
        assert result is None  # 失败被捕获

    @pytest.mark.asyncio
    async def test_pipeline_executes_concurrently(self):
        """验证 14 因子并发执行（gather 调用）"""
        from app.services.sentiment_service import SentimentService

        mock_session = MagicMock()
        service = SentimentService(db_session=mock_session)

        # Mock 所有因子类
        factor_classes = {}
        for name in ["VOL", "ADR", "ERP", "FLOW", "ETF", "NHNL", "TURN", "POS",
                     "NBF", "PCR", "NEWF", "MARGIN", "RSI", "INDUSTRY_DIVERGENCE"]:
            mock_cls = MagicMock()
            mock_factor = MagicMock()
            mock_factor.fetch_raw = AsyncMock(return_value=MagicMock(raw_value=50.0))
            mock_factor._get_default_raw_value = MagicMock(return_value=50.0)
            mock_factor.sigmoid_c = 0.5
            mock_factor.sigmoid_k = 3.0
            mock_factor.direction = "greed"
            mock_cls.return_value = mock_factor
            factor_classes[name] = mock_cls

        service.quantile.calc_percentile = AsyncMock(return_value=0.5)

        with patch("app.services.sentiment_service.FACTOR_NAMES", list(factor_classes.keys())):
            with patch("app.services.sentiment_service.FACTOR_CLASSES", factor_classes):
                start = time.time()
                results = await service._run_factor_pipeline("SH000300", "2026-06-17")
                elapsed = time.time() - start

        # 14 因子应该全部处理完
        assert len(results) == 14
        # 因为每个 fetch_raw 是 0 延迟 mock，并发执行应该 < 1s
        assert elapsed < 1.0, f"Pipeline took {elapsed:.2f}s, expected < 1s"

    @pytest.mark.asyncio
    async def test_pipeline_isolates_single_factor_failure(self):
        """单因子失败不应影响其他因子"""
        from app.services.sentiment_service import SentimentService

        mock_session = MagicMock()
        service = SentimentService(db_session=mock_session)

        # 构造 3 个因子：2 个正常 + 1 个完全失败
        factor_classes = {}
        for i, name in enumerate(["VOL", "ADR", "ERP"]):
            mock_cls = MagicMock()
            mock_factor = MagicMock()
            if i == 1:  # ADR 完全失败
                mock_factor.fetch_raw = AsyncMock(side_effect=Exception("boom"))
                mock_factor._get_default_raw_value = MagicMock(side_effect=Exception("boom"))
            else:
                mock_factor.fetch_raw = AsyncMock(return_value=MagicMock(raw_value=50.0))
                mock_factor._get_default_raw_value = MagicMock(return_value=50.0)
            mock_factor.sigmoid_c = 0.5
            mock_factor.sigmoid_k = 3.0
            mock_factor.direction = "greed"
            mock_cls.return_value = mock_factor
            factor_classes[name] = mock_cls

        service.quantile.calc_percentile = AsyncMock(return_value=0.5)

        with patch("app.services.sentiment_service.FACTOR_NAMES", list(factor_classes.keys())):
            with patch("app.services.sentiment_service.FACTOR_CLASSES", factor_classes):
                results = await service._run_factor_pipeline("SH000300", "2026-06-17")

        # 3 个因子里 2 个成功，1 个失败
        assert len(results) == 2, f"Expected 2 results, got {len(results)}"
        factor_names = {r.factor_name for r in results}
        assert "VOL" in factor_names
        assert "ERP" in factor_names
        assert "ADR" not in factor_names  # 失败被过滤


class TestParallelPerformance:
    """P2-2 性能测试"""

    @pytest.mark.asyncio
    async def test_concurrent_execution_faster_than_serial(self):
        """并发执行 14 因子（含 0.05s 模拟延迟）应比串行快"""
        from app.services.sentiment_service import SentimentService

        mock_session = MagicMock()
        service = SentimentService(db_session=mock_session)

        # 模拟每个 fetch_raw 耗时 50ms
        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(0.05)
            return MagicMock(raw_value=50.0)

        factor_classes = {}
        for name in ["VOL", "ADR", "ERP", "FLOW", "ETF", "NHNL", "TURN", "POS",
                     "NBF", "PCR", "NEWF", "MARGIN", "RSI", "INDUSTRY_DIVERGENCE"]:
            mock_cls = MagicMock()
            mock_factor = MagicMock()
            mock_factor.fetch_raw = slow_fetch
            mock_factor._get_default_raw_value = MagicMock(return_value=50.0)
            mock_factor.sigmoid_c = 0.5
            mock_factor.sigmoid_k = 3.0
            mock_factor.direction = "greed"
            mock_cls.return_value = mock_factor
            factor_classes[name] = mock_cls

        service.quantile.calc_percentile = AsyncMock(return_value=0.5)

        with patch("app.services.sentiment_service.FACTOR_NAMES", list(factor_classes.keys())):
            with patch("app.services.sentiment_service.FACTOR_CLASSES", factor_classes):
                start = time.time()
                results = await service._run_factor_pipeline("SH000300", "2026-06-17")
                parallel_elapsed = time.time() - start

        # 串行预期 14 * 0.05s = 0.7s
        # 并发预期 ≈ 0.05s ~ 0.1s（受 GIL + to_thread 限制）
        # 容差设为串行的 30%
        assert parallel_elapsed < 0.7 * 0.5, (
            f"Expected < {0.7*0.5:.2f}s (parallel), got {parallel_elapsed:.2f}s. "
            f"Concurrency may not be working."
        )
        assert len(results) == 14
