"""
ADR 涨跌比因子 — V5.0
迁移自 scoring.py
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_adv_decline_ratio


class AdrFactor(BaseFactor):
    """ADR 涨跌比因子：高比值 → 贪婪"""
    name = "ADR"
    label = "涨跌比"
    direction = "greed"
    weight = 0.12
    sigmoid_c = 0.50
    sigmoid_k = 2.5

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        获取涨跌比原始值
        返回：上涨家数/下跌家数比
        """
        try:
            raw = await fetch_adv_decline_ratio()
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"ADR fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """ADR 默认值：涨跌各半"""
        return 1.0

    def validate(self, raw: FactorRawValue) -> bool:
        """涨跌比应在 [0.1, 10] 范围内"""
        v = raw.raw_value
        if v is None or v < 0.05 or v > 20.0:
            return False
        return True
