"""
MACD背离因子 — V5.0 Phase 3
检测价格MACD与情绪MACD之间的背离，作为第15个因子注入情绪分数。
顶背离（价格涨+情绪弱）→ fear方向高值 → 反向后低分 → 恐惧
底背离（价格跌+情绪强）→ fear方向低值 → 反向后高分 → 贪婪
"""
from __future__ import annotations

from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import data_source


class DivergenceFactor(BaseFactor):
    """MACD背离因子：价格MACD vs 情绪MACD背离 → fear方向"""
    name = "DIVERGENCE"
    label = "MACD背离"
    direction = "fear"
    weight = 0.03
    sigmoid_c = 0.50
    sigmoid_k = 2.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        计算MACD背离原始值。

        raw_value映射（direction=fear，低值=恐惧）:
          - top (顶背离): 50 + strength*50 (50-100，市场仍贪婪)
          - bottom (底背离): 50 - strength*50 (0-50，市场仍恐惧)
          - none/insufficient: 50 (中性)
        """
        try:
            from app.core.database import get_session_factory
            from app.engine.factor_history import FactorHistoryStore
            from app.engine.sentiment_macd import SentimentMACD
            from app.engine.price_macd import PriceMACD
            from app.engine.divergence_detector import DivergenceDetector

            store = FactorHistoryStore()
            session_factory = get_session_factory()

            async with session_factory() as session:
                # 获取情绪分数历史（不含今日，今日分数尚未计算）
                sentiment_history = await store.get_series(
                    session, index_code, "COMPOSITE", lookback_days=120,
                )
                # 获取价格历史
                price_history = await store.get_series(
                    session, index_code, "CLOSE", lookback_days=120,
                )

            # 追加今日收盘价
            d = await data_source.get_index_data(index_code)
            today_close = d.get("close")
            if today_close:
                price_history.append(float(today_close))

            # 计算MACD历史序列
            sm = SentimentMACD()
            pm = PriceMACD()
            sent_macd_hist = sm.compute_history(sentiment_history)
            price_macd_hist = pm.compute_history(price_history)

            # 背离检测
            det = DivergenceDetector()
            result = det.detect_macd_divergence(
                price_macd_hist, sent_macd_hist, window=20,
            )

            # 映射 raw_value
            div_type = result["type"]
            strength = result["strength"]

            if div_type == "top":
                raw_value = 50.0 + strength * 50.0
            elif div_type == "bottom":
                raw_value = 50.0 - strength * 50.0
            else:
                raw_value = 50.0

            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=round(raw_value, 2),
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"DIVERGENCE fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """默认中性值50"""
        return 50.0

    def validate(self, raw: FactorRawValue) -> bool:
        """raw_value 应在 [0, 100] 范围内"""
        v = raw.raw_value
        if v is None or v < 0.0 or v > 100.0:
            return False
        return True
