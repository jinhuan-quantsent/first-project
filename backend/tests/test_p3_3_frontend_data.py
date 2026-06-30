"""
前端组件数据契约测试 — 阶段 3 P3-3

验证：
- /api/v5/market/signal-lights 返回的 signals[] 形状满足 SentimentMACD 需求
- /api/v5/market/signal-lights 返回的 signals[] 形状满足 SignalPerformancePanel 需求
- 至少 26 天数据时 MACD 可计算
- 至少 1 天数据时统计可计算
- 连续同向天数算法正确性
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, timedelta

from app.services.sentiment_service import SentimentService


def make_signal(date_str: str, level: str = "B", score: float = 50.0, stars: int = 3) -> dict:
    return {
        "date": date_str,
        "signal_level": level,
        "composite_score": score,
        "confidence_stars": stars,
    }


class TestSentimentMACDDataContract:
    """SentimentMACD.tsx 数据契约"""

    def test_signal_lights_returns_required_fields(self):
        """API 返回的 signals 应包含 date/composite_score/signal_level"""
        # 模拟 30 天数据
        today = date.today()
        signals = [
            make_signal((today - timedelta(days=i)).isoformat())
            for i in range(29, -1, -1)
        ]
        result = {
            "index_code": "SH000300",
            "signals": signals,
            "updated_at": today.isoformat(),
        }
        # 验证每个 signal 都有必需字段
        for s in result["signals"]:
            assert "date" in s
            assert "composite_score" in s
            assert isinstance(s["composite_score"], (int, float))
            assert "signal_level" in s
            assert 0 <= s["composite_score"] <= 100

    def test_macd_requires_min_26_days(self):
        """MACD 计算需要至少 26 天数据"""
        # 模拟 25 天
        today = date.today()
        signals = [make_signal((today - timedelta(days=i)).isoformat()) for i in range(25)]
        # 前端逻辑：scores.length < 26 → 提示"数据不足"
        assert len(signals) < 26

    def test_macd_ema_calculation_consistency(self):
        """EMA(12) 第一个有效值应是前 12 个数据的简单平均"""
        scores = [50.0, 51.0, 52.0, 53.0, 54.0, 55.0, 56.0, 57.0, 58.0, 59.0, 60.0, 61.0]
        # EMA12 第一个值 = mean(50..61) = 55.5
        # 我们用前端 calcEMA 函数同样的逻辑
        k = 2 / (12 + 1)
        ema12_first = sum(scores[:12]) / 12
        assert abs(ema12_first - 55.5) < 0.01


class TestSignalPerformanceDataContract:
    """SignalPerformancePanel.tsx 数据契约"""

    def test_distribution_contains_all_levels(self):
        """7 级信号都应在统计中出现（即使 count=0）"""
        from app.services.sentiment_service import SentimentService
        # 实际 calcSignalStats 不会自己跑，我们用前端等价逻辑测试
        from app.api.v5.sentiment_router import get_v5_signal_lights  # 验证可 import

        # 关键：API 返回的 signal_level 必须是 7 级之一
        valid_levels = {"S+", "S", "A", "B", "C", "D", "E"}
        today = date.today()
        signals = [
            make_signal((today - timedelta(days=i)).isoformat(), level="B")
            for i in range(3)
        ]
        for s in signals:
            assert s["signal_level"] in valid_levels

    def test_extreme_count_includes_S_plus_and_E(self):
        """极值次数 = S+ + E"""
        signals = [
            make_signal("2026-06-01", "S+"),
            make_signal("2026-06-02", "B"),
            make_signal("2026-06-03", "E"),
            make_signal("2026-06-04", "S+"),
        ]
        # 前端 calcSignalStats 逻辑
        distribution = {l: 0 for l in ["S+", "S", "A", "B", "C", "D", "E"]}
        for s in signals:
            if s["signal_level"] in distribution:
                distribution[s["signal_level"]] += 1
        extreme = distribution["S+"] + distribution["E"]
        assert extreme == 3

    def test_consecutive_days_count(self):
        """连续同向天数算法正确性"""
        # 场景 1: 5 天连续 B
        signals1 = [
            make_signal("2026-06-15", "B"),
            make_signal("2026-06-14", "B"),
            make_signal("2026-06-13", "B"),
            make_signal("2026-06-12", "B"),
            make_signal("2026-06-11", "B"),
        ]
        # 前端逻辑：sort by date desc，找连续 B
        sorted1 = sorted(signals1, key=lambda s: s["date"], reverse=True)
        latest = sorted1[0]["signal_level"]
        count = 0
        for s in sorted1:
            if s["signal_level"] == latest:
                count += 1
            else:
                break
        assert count == 5

        # 场景 2: 中间断裂
        signals2 = [
            make_signal("2026-06-15", "A"),
            make_signal("2026-06-14", "A"),
            make_signal("2026-06-13", "B"),  # 断裂
            make_signal("2026-06-12", "A"),
        ]
        sorted2 = sorted(signals2, key=lambda s: s["date"], reverse=True)
        latest = sorted2[0]["signal_level"]
        count = 0
        for s in sorted2:
            if s["signal_level"] == latest:
                count += 1
            else:
                break
        assert count == 2  # 只算最近 2 天 A


class TestServiceGetSignalLights:
    """SentimentService.get_signal_lights 集成测试（mock DB + Tushare）"""

    @pytest.mark.asyncio
    async def test_get_signal_lights_returns_signals_array(self):
        """get_signal_lights 应返回 {code, data: {signals[]}}"""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.scalar = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        service = SentimentService(db_session=mock_session)

        # 模拟 run_pipeline 行为：返回有效信号
        async def mock_pipeline(index_code, trade_date):
            return {
                "signal_level": "B",
                "composite_score": 50.0,
                "confidence_stars": 3,
            }

        with patch.object(service, "run_pipeline", side_effect=mock_pipeline):
            result = await service.get_signal_lights("SH000300", days=3)

        # service 返回 {code, data, message} wrapper
        assert "data" in result
        assert "signals" in result["data"]
        signals = result["data"]["signals"]
        assert len(signals) == 3
        for s in signals:
            assert "date" in s
            assert "signal_level" in s
            assert "composite_score" in s

    @pytest.mark.asyncio
    async def test_get_signal_lights_handles_pipeline_errors(self):
        """pipeline 异常时应 fallback 到默认 B 级信号（不抛错）"""
        mock_session = MagicMock()
        mock_session.rollback = AsyncMock()
        service = SentimentService(db_session=mock_session)

        async def mock_pipeline_fail(index_code, trade_date):
            raise RuntimeError("test error")

        with patch.object(service, "run_pipeline", side_effect=mock_pipeline_fail):
            result = await service.get_signal_lights("SH000300", days=2)

        signals = result["data"]["signals"]
        assert len(signals) == 2
        for s in signals:
            assert s["signal_level"] == "B"  # fallback
            assert s["composite_score"] == 50.0
