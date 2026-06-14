"""
PCR 认沽认购比因子 — V5.0
⚠️ 左移中点 + 高敏感
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_put_call_ratio


class PcrFactor(BaseFactor):
    """PCR 认沽认购比因子：高PCR → 恐慌"""
    name = "PCR"
    label = "认沽认购比"
    direction = "fear"
    weight = 0.04
    sigmoid_c = 0.30  # 左移中点
    sigmoid_k = 4.0   # 高敏感

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_put_call_ratio()
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"PCR fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """PCR 默认值：经验值"""
        return 0.85

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < 0.1 or v > 5.0:
            return False
        return True
