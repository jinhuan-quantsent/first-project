"""
NBF 北向资金方向因子 — V5.0
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_northbound_flow


class NbfFactor(BaseFactor):
    """NBF 北向资金因子：净流入 → 贪婪"""
    name = "NBF"
    label = "北向资金"
    direction = "greed"
    weight = 0.06
    sigmoid_c = 0.50
    sigmoid_k = 2.5

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_northbound_flow()
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"NBF fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """NBF 默认值：中性"""
        return 0.0

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < -200.0 or v > 200.0:
            return False
        return True
