"""
TURN 换手率因子 — V5.0
迁移自 scoring.py
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_turnover


class TurnFactor(BaseFactor):
    """TURN 换手率因子：高换手 → 恐慌"""
    name = "TURN"
    label = "换手率"
    direction = "fear"
    weight = 0.08
    sigmoid_c = 0.40  # 左移中点
    sigmoid_k = 3.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        try:
            raw = await fetch_turnover(index_code)
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"TURN fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """TURN 默认值：中等换手率"""
        return 1.5

    def validate(self, raw: FactorRawValue) -> bool:
        v = raw.raw_value
        if v is None or v < 0.1 or v > 15.0:
            return False
        return True
