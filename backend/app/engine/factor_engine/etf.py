"""
ETF 份额变化因子 — V5.0
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_etf_change


class EtfFactor(BaseFactor):
    """ETF 份额变化因子：份额增加 → 贪婪"""
    name = "ETF"
    label = "ETF份额"
    direction = "greed"
    weight = 0.08
    sigmoid_c = 0.50
    sigmoid_k = 2.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_etf_change(index_code)
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"ETF fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """ETF 默认值：无变化"""
        return 0.0

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < -20.0 or v > 20.0:
            return False
        return True
