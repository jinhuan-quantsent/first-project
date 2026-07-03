"""
NHNL 新高占比因子 — V5.0
迁移自 scoring.py
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_nhnl_ratio


class NhnlFactor(BaseFactor):
    """NHNL 新高占比因子：新高高 → 贪婪"""
    name = "NHNL"
    label = "新高占比"
    direction = "greed"
    weight = 0.08
    sigmoid_c = 0.60  # 右移中点
    sigmoid_k = 2.5

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_nhnl_ratio(index_code)
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"NHNL fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """NHNL 默认值：中性"""
        return 0.5

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < 0.0 or v > 30.0:
            return False
        return True
