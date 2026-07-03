"""
POS 基金仓位估算因子 — V5.0
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_fund_position


class PosFactor(BaseFactor):
    """POS 基金仓位因子：高仓位 → 贪婪"""
    name = "POS"
    label = "基金仓位"
    direction = "greed"
    weight = 0.08
    sigmoid_c = 0.50
    sigmoid_k = 1.8

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_fund_position()
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"POS fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """POS 默认值：经验值"""
        return 62.0

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < 10.0 or v > 99.0:
            return False
        return True
