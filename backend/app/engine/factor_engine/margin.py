"""
MARGIN 融资融券因子 — V5.0
融资余额变化反映市场杠杆水平：高杠杆 → 贪婪（风险积累）
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import data_source


class MarginFactor(BaseFactor):
    """MARGIN 融资融券因子：融资净流入 → 贪婪"""
    name = "MARGIN"
    label = "融资融券"
    direction = "greed"
    weight = 0.04
    sigmoid_c = 0.50
    sigmoid_k = 2.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        获取融资融券净流入(亿元)
        正值=融资净流入(加杠杆) → 贪婪
        """
        try:
            margin_data = None
            # 优先 Tushare
            try:
                margin_data = data_source._fetch_tushare_margin()
            except Exception:
                pass
            # 降级 AKShare
            if margin_data is None:
                try:
                    margin_data = data_source._fetch_akshare_margin()
                except Exception:
                    pass
            # 降级 Mock
            if margin_data is None:
                margin_data = data_source._mock_margin_data()

            net_flow = float(margin_data.get("net_margin_flow", 0.0))
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=net_flow,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"MARGIN fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """MARGIN 默认值：中性净流入"""
        return 0.0

    def validate(self, raw: FactorRawValue) -> bool:
        """融资净流入应在 [-500, 500] 亿元范围内"""
        v = raw.raw_value
        if v is None or v < -500.0 or v > 500.0:
            return False
        return True
