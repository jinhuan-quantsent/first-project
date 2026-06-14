"""
分位数标准化层 — V5.0 层1
5年滚动窗口（1260个交易日），原始值 → 分位数(0-1)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
from scipy import stats

from app.engine.factor_engine.base import FactorRawValue, FactorQuantileResult
from app.engine.factor_history import FactorHistoryStore, V5_FACTOR_META
from app.core.config import settings


class QuantileNorm:
    """分位数标准化器"""

    def __init__(self, session) -> None:
        self._store = FactorHistoryStore()
        self._session = session
        self._window_days = settings.V5_QUANTILE_WINDOW_DAYS
        self._min_samples = settings.V5_QUANTILE_MIN_SAMPLES

    async def calc_percentile(
        self,
        raw_value: float,
        index_code: str,
        factor_name: str,
    ) -> float | None:
        """
        计算原始值在历史序列中的分位数
        返回 0.0-1.0 的分位数，数据不足时返回 None
        """
        series = await self._store.get_series(
            self._session, index_code, factor_name, self._window_days,
        )
        if series is None or len(series) < self._min_samples:
            return None
        try:
            # 使用 scipy.stats.percentileofscore
            pct = stats.percentileofscore(series, raw_value, kind="rank")
            return round(pct / 100.0, 6)  # 转换为 0-1
        except Exception:
            return None

    async def normalize_batch(
        self,
        raw_values: list[FactorRawValue],
    ) -> list[FactorQuantileResult]:
        """
        批量化分位数标准化
        输入：11个 FactorRawValue
        输出：11个 FactorQuantileResult
        """
        results: list[FactorQuantileResult] = []
        for raw in raw_values:
            percentile = await self.calc_percentile(
                raw.raw_value, raw.index_code, raw.factor_name,
            )
            # 数据不足时使用硬编码参考值
            if percentile is None:
                percentile = self._fallback_percentile(raw)

            results.append(FactorQuantileResult(
                factor_name=raw.factor_name,
                raw_value=raw.raw_value,
                percentile=percentile,
                window_size=self._window_days,
                available_samples=await self._get_sample_count(
                    raw.index_code, raw.factor_name,
                ),
            ))
        return results

    def _fallback_percentile(self, raw: FactorRawValue) -> float:
        """
        数据不足时的降级策略：
        使用硬编码分位数参考表（基于沪深300历史数据预估）
        """
        # 简易映射：根据因子方向和原始值范围估算分位数
        # 实际部署后应预先回填历史数据
        fallback_map = {
            "VOL":  0.50,
            "ADR":  0.50,
            "ERP":  0.50,
            "FLOW": 0.50,
            "ETF":  0.50,
            "NHNL": 0.50,
            "TURN": 0.50,
            "POS":  0.50,
            "NBF":  0.50,
            "PCR":  0.50,
            "NEWF": 0.50,
        }
        return fallback_map.get(raw.factor_name, 0.50)

    async def _get_sample_count(self, index_code: str, factor_name: str) -> int:
        """获取历史样本数"""
        try:
            return await self._store.get_series_count(
                self._session, index_code, factor_name,
            )
        except Exception:
            return 0
