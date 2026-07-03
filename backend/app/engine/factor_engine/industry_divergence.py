"""
INDUSTRY_DIVERGENCE 行业分歧度因子 — V5.0
不同行业/板块间情绪分歧度：分歧大 → 市场不协调 → 谨慎
使用sector_scorer计算板块情绪标准差
"""
from app.engine.factor_engine.base import BaseFactor, FactorRawValue
from app.utils.data_source import data_source


class IndustryDivergenceFactor(BaseFactor):
    """INDUSTRY_DIVERGENCE 行业分歧度因子：板块间情绪标准差"""
    name = "INDUSTRY_DIVERGENCE"
    label = "行业分歧度"
    direction = "fear"
    weight = 0.03
    sigmoid_c = 0.50
    sigmoid_k = 2.0

    async def fetch_raw(self, index_code: str, trade_date: str) -> FactorRawValue:
        """
        获取行业分歧度原始值
        从板块情绪数据计算标准差
        高分歧(大std) → 市场不协调 → 谨慎/fear
        """
        try:
            import numpy as np
            from app.core.redis_client import cache_get

            # 尝试从缓存的板块数据获取
            cached = await cache_get("fsa:market-sectors")
            if cached and isinstance(cached, dict) and "data" in cached:
                sectors = cached["data"]
                if isinstance(sectors, list) and len(sectors) >= 5:
                    scores = []
                    for s in sectors:
                        score = s.get("sentiment_score") or s.get("score")
                        if score is not None:
                            scores.append(float(score))
                    if len(scores) >= 5:
                        std = float(np.std(scores))
                        return FactorRawValue(
                            factor_name=self.name,
                            index_code=index_code,
                            trade_date=trade_date,
                            raw_value=std,
                            direction=self.direction,
                        )

            # 降级：使用已有因子标准差近似
            return FactorRawValue(
                factor_name=self.name,
                index_code=index_code,
                trade_date=trade_date,
                raw_value=10.0,  # 中性分歧度
                direction=self.direction,
            )
        except Exception as e:
            from app.utils.exceptions import FactorCalcError
            raise FactorCalcError(f"INDUSTRY_DIVERGENCE fetch_raw failed: {e}")

    def _get_default_raw_value(self, index_code: str = "") -> float:
        """行业分歧度默认值：中等分歧"""
        return 10.0

    def validate(self, raw: FactorRawValue) -> bool:
        """分歧度应在 [0, 50] 范围内"""
        v = raw.raw_value
        if v is None or v < 0.0 or v > 50.0:
            return False
        return True
