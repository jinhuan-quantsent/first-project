"""
FLOW 基金申赎资金流因子 — V5.0
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_fund_flow


class FlowFactor(BaseFactor):
    """FLOW 资金流因子：净流入 → 贪婪"""
    name = "FLOW"
    label = "资金流"
    direction = "greed"
    weight = 0.10
    sigmoid_c = 0.50
    sigmoid_k = 2.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_fund_flow(index_code)
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"FLOW fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """FLOW 默认值：中性资金流"""
        return 0.0

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < -100.0 or v > 100.0:
            return False
        return True
