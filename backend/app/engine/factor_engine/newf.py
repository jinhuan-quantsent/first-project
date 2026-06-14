"""
NEWF 新发基金热度因子 — V5.0
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_new_fund_heat


class NewfFactor(BaseFactor):
    """NEWF 新发基金热度因子：高热度 → 贪婪"""
    name = "NEWF"
    label = "新发基金热度"
    direction = "greed"
    weight = 0.04
    sigmoid_c = 0.50
    sigmoid_k = 2.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_new_fund_heat()
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"NEWF fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """NEWF 默认值：经验值"""
        return 50.0

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < 0.0 or v > 500.0:
            return False
        return True
