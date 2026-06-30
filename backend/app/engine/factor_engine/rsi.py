"""
RSI 相对强弱因子 — V5.0
RSI过高→超买→贪婪；RSI过低→超卖→恐惧
使用方向为 fear：RSI低分位→恐惧（买入机会），高分位→贪婪（卖出信号）
注意：RSI在标准情绪框架中是反向因子 - RSI低=超卖=恐惧信号
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import data_source


class RsiFactor(BaseFactor):
    """RSI 相对强弱因子：RSI(14) → fear方向"""
    name = "RSI"
    label = "RSI指标"
    direction = "fear"
    weight = 0.03
    sigmoid_c = 0.50
    sigmoid_k = 2.5

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        获取RSI(14)原始值
        RSI < 30 → 超卖 → 恐惧
        RSI > 70 → 超买 → 贪婪
        direction=fear 表示低RSI对应恐惧
        """
        try:
            d = await data_source.get_index_data(index_code)
            rsi = float(d.get("rsi_value", 50.0))
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=rsi,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"RSI fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """RSI 默认值：中性50"""
        return 50.0

    def validate(self, raw: FactorRawValue) -> bool:
        """RSI应在 [0, 100] 范围内"""
        v = raw.raw_value
        if v is None or v < 0.0 or v > 100.0:
            return False
        return True
