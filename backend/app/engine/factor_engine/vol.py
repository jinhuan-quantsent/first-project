"""
VOL 波动率因子 — V5.0
迁移自 scoring.py + 分位数映射
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_volatility


class VolFactor(BaseFactor):
    """VOL 波动率因子：高波动 → 恐惧"""
    name = "VOL"
    label = "波动率"
    direction = "fear"
    weight = 0.12
    sigmoid_c = 0.50
    sigmoid_k = 3.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        获取波动率原始值
        返回：年化波动率(%)
        """
        try:
            raw = await fetch_volatility(index_code)
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"VOL fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """VOL 默认值：中等波动率"""
        return 20.0

    def validate(self, raw: FactorRawValue) -> bool:
        """波动率应在 [5, 60] 范围内"""
        v = raw.raw_value
        if v is None or v < 3.0 or v > 80.0:
            return False
        return True
