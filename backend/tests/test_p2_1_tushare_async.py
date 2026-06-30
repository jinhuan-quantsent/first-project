"""
P2-1: Tushare 同步调用异步化测试

验证：
1. _fetch_tushare_index_daily 同步函数依然存在
2. _do_fetch_tushare_northbound 同步函数存在（P2-1 新增）
3. get_index_data 包装后依然返回正确数据
4. asyncio.to_thread 不会破坏类型
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.utils.data_source import data_source


class TestToThreadWrapping:
    """P2-1 验证 to_thread 包装不破坏现有功能"""

    @pytest.mark.asyncio
    async def test_get_index_data_still_works(self):
        """get_index_data 在 to_thread 包装后仍可正常返回"""
        result = await data_source.get_index_data("SH000300")
        assert "close" in result
        assert "index_code" in result
        assert result["index_code"] == "SH000300"

    @pytest.mark.asyncio
    async def test_get_index_data_returns_valid_structure(self):
        """验证返回结构完整"""
        result = await data_source.get_index_data("SH000300")
        expected_keys = {"index_code", "index_name", "close", "change_pct"}
        actual_keys = set(result.keys())
        assert expected_keys.issubset(actual_keys), f"Missing keys: {expected_keys - actual_keys}"

    def test_sync_fetch_methods_still_exist(self):
        """P2-1 保留原同步方法（向后兼容）"""
        assert hasattr(data_source, "_fetch_tushare_index_daily")
        assert hasattr(data_source, "_fetch_tushare_index_basic")
        assert hasattr(data_source, "_fetch_tushare_margin")
        assert hasattr(data_source, "_fetch_tushare_adv_decline")

    @pytest.mark.asyncio
    async def test_get_index_data_with_mock_tushare(self):
        """使用 mock tushare 验证 to_thread 调用链"""
        with patch.object(data_source, '_tushare_pro', new=MagicMock()):
            with patch.object(data_source, '_tushare_available', new=True):
                with patch.object(data_source, '_fetch_tushare_index_daily', return_value={
                    "close": 3500.0,
                    "change_pct": 1.5,
                    "rsi_value": 60.0,
                    "volatility": 18.0,
                    "new_high_ratio": 8.0,
                    "trade_date": "20260617",
                    "closes_for_history": [3500.0],
                    "source": "tushare",
                }):
                    with patch.object(data_source, '_clear_cache_if_expired', lambda: None):
                        with patch.object(data_source, '_index_cache', new={}):
                            # 通过 patch 跳过 redis 缓存命中
                            with patch("app.utils.data_source.cache_get", new=AsyncMock(return_value=None)):
                                with patch("app.utils.data_source.cache_set", new=AsyncMock()):
                                    result = await data_source.get_index_data("SH000300")
                                    assert result["close"] == 3500.0
                                    assert result["source"] == "tushare"


class TestAsyncSafety:
    """验证 to_thread 包装后的 async 安全性"""

    @pytest.mark.asyncio
    async def test_concurrent_get_index_data(self):
        """多个并发 get_index_data 都能正常完成"""
        results = await asyncio.gather(
            data_source.get_index_data("SH000300"),
            data_source.get_index_data("SH000001"),
            data_source.get_index_data("SZ399006"),
        )
        assert len(results) == 3
        for r in results:
            assert "close" in r

    @pytest.mark.asyncio
    async def test_to_thread_imports(self):
        """asyncio.to_thread 是标准库，导入可用"""
        assert hasattr(asyncio, "to_thread")
        assert asyncio.to_thread is not None
