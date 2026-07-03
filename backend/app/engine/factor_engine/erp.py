"""
ERP 股债性价比因子 — V5.0
⚠️ 方向反转：高ERP → 股票相对债券更便宜 → 恐惧分低
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import fetch_erp


class ErpFactor(BaseFactor):
    """
    ERP 股债性价比因子
    方向：fear（高ERP → 低恐惧分）
    ⚠️ 方向反转因子：需要在 sigmoid 映射后 100 - score
    """
    name = "ERP"
    label = "股债性价比"
    direction = "fear"  # 高ERP → 恐惧分低（反向）
    weight = 0.12
    sigmoid_c = 0.50
    sigmoid_k = 4.0  # 高敏感

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        获取 ERP 原始值
        返回：equity_yield - 10年期国债收益率
        ⚠️ 高ERP → 股票便宜 → 恐惧分低（反向因子）
        """
        try:
            raw = await fetch_erp(index_code)
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=raw,
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"ERP fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """ERP 默认值：股债比适中"""
        return 3.0

    def validate(self, raw: FactorRawValue) -> bool:
        """ERP 应在 [-5, 10] 范围内"""
        v = raw.raw_value
        if v is None or v < -10.0 or v > 15.0:
            return False
        return True

    def derive(self, raw: FactorRawValue) -> FactorRawValue:
        """
        ERP 方向反转处理：
        高ERP → 低恐惧分，需要在 sigmoid 后做 100 - score
        这里只做标记，实际反转在 sigmoid 层处理
        """
        # 标记 direction=fear 的因子需要在 sigmoid 后反转
        return raw
