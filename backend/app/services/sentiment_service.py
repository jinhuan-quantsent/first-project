"""
Sentiment Service - V5.0 情绪分析核心业务逻辑
包含完整 pipeline 运行（Layer 1+2+3）、信号灯查询、多指数情绪、雷达图数据、背离检测
"""
import asyncio
import json
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import cache_get, cache_set
from app.utils.code_format import to_tushare, to_display
from app.utils.data_source import data_source, DEFAULT_INDEX_CODES
from app.engine.factor_engine import FACTOR_NAMES, FACTOR_CLASSES
from app.engine.factor_engine.base import FactorSigmoidResult
from app.engine.quantile import QuantileNorm
from app.engine.sigmoid import SigmoidMapper
from app.engine.aggregator_v5 import AggregatorV5
from app.engine.signal_mapper import SignalMapper
from app.engine.confidence import ConfidenceEngine
from app.engine.sentiment_macd import SentimentMACD
from app.engine.factor_history import FactorHistoryStore
from app.engine.divergence_detector import DivergenceDetector
from app.models.market_sentiment import MarketSentiment

logger = logging.getLogger(__name__)


# 默认指数权重（市值加权）
WEIGHT_MAP = {
    "SH000001": 0.25,   # 上证指数
    "SH000300": 0.30,   # 沪深300
    "SZ399001": 0.25,   # 深证成指
    "SZ399006": 0.20,   # 创业板指
}


class SentimentService:
    """
    V5.0 情绪分析 Service

    职责：
    1. 完整 pipeline 运行（fetch → quantile → sigmoid → aggregate → signal）
    2. 防跳变逻辑（前一日信号查询）
    3. MACD 计算 + 背离检测
    4. 置信度计算（4 防线）
    5. 落库（market_sentiment 表）
    6. Redis 缓存（5 分钟）
    """

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.quantile = QuantileNorm(session=db_session)
        self.sigmoid_mapper = SigmoidMapper()
        self.aggregator = AggregatorV5()
        self.signal_mapper = SignalMapper()
        self.confidence_engine = ConfidenceEngine()
        self.history_store = FactorHistoryStore()
        self.macd_engine = SentimentMACD()
        self.divergence_detector = DivergenceDetector()

    async def run_pipeline(
        self,
        index_code: str,
        trade_date: Optional[str] = None,
    ) -> dict:
        """
        运行 V5.0 完整流水线（带 Redis 缓存）

        Returns:
            dict: 包含 index_code / composite_score / signal_level / confidence_stars /
                  factor_details / regime / defenses_triggered 等字段
        """
        if trade_date is None:
            trade_date = date.today().isoformat()

        # 尝试从缓存获取（仅当天日期的实时数据缓存 5 分钟）
        cache_key = f"fsa:sentiment:{index_code}:{trade_date}"
        if trade_date == date.today().isoformat():
            cached = await cache_get(cache_key)
            if cached:
                return cached

        # 获取指数数据
        index_data = await data_source.get_index_data(index_code)
        if not index_data or index_data.get("index_name") == "未知指数":
            return {"error": f"指数 {index_code} 不存在"}

        # Layer 1+2：14 因子流水
        sigmoid_results = await self._run_factor_pipeline(index_code, trade_date)

        # Layer 3：加权聚合
        composite = self.aggregator.aggregate(sigmoid_results)

        # 防跳变 + 信号映射
        prev_level, prev_score, consecutive_same = await self._load_prev_signal(
            index_code, composite.score
        )
        score_diff = (composite.score - prev_score) if prev_score is not None else None
        signal_level, jump_blocked = self.signal_mapper.map(
            composite.score,
            prev_level=prev_level,
            score_diff=score_diff,
            consecutive_same=consecutive_same,
        )

        # MACD + 价格历史
        macd_data, sentiment_history, price_history, macd_history, price_macd_data, price_macd_history, divergence_data = await self._compute_macd_and_history(
            db_session=self.db_session,
            index_code=index_code,
            trade_date=trade_date,
            composite_score=composite.score,
            index_data=index_data,
        )

        # 存储今日 composite_score + 收盘价
        await self._store_history(index_code, trade_date, composite.score, index_data)

        # 置信度计算
        confidence_stars, confidence_detail, defenses = self.confidence_engine.calculate(
            sigmoid_results, signal_level, composite.divergence.regime,
            macd_data=macd_data,
            price_series=price_history if len(price_history) >= 5 else None,
            sentiment_series=sentiment_history + [composite.score] if len(sentiment_history) >= 4 else None,
        )

        # 落库 market_sentiment
        await self._save_market_sentiment(
            index_code=index_code,
            index_name=index_data.get("index_name", ""),
            trade_date=trade_date,
            composite_score=composite.score,
            signal_level=signal_level,
            confidence_stars=confidence_stars,
            confidence_detail=confidence_detail,
            defenses=defenses,
            factor_std=composite.divergence.factor_std,
            penalty_factor=composite.divergence.penalty_factor,
            regime=composite.divergence.regime,
        )

        # 组装结果
        result = {
            "index_code": index_code,
            "index_name": index_data.get("index_name", index_code),
            "composite_score": round(composite.score, 2),
            "score_std": round(composite.divergence.factor_std, 4),
            "divergence_penalty": round(composite.divergence.penalty_factor, 4),
            "regime": composite.divergence.regime,
            "signal_level": signal_level,
            "signal_jump_blocked": jump_blocked,
            "confidence_stars": confidence_stars,
            "confidence_detail": confidence_detail,
            "defenses_triggered": defenses,
            "macd": macd_data,
            "macd_history": macd_history,
            "price_macd": price_macd_data,
            "price_macd_history": price_macd_history,
            "divergence": divergence_data,
            "factor_details": [r.to_dict() for r in sigmoid_results],
            "updated_at": datetime.now().isoformat(),
        }

        # 缓存当天数据 5 分钟
        if trade_date == date.today().isoformat():
            try:
                await cache_set(cache_key, result, ttl=86400)
            except Exception:
                pass  # 缓存失败不影响主流程

        return result

    async def run_multi_index(
        self,
        codes: list[str],
        timeout_per_index: float = 15.0,
    ) -> dict:
        """
        多指数并行 pipeline + 加权综合

        Returns:
            dict: indexes / composite / position_advice
        """
        cache_key = f"fsa:multi-index:{','.join(codes)}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        # 并行调用各指数 pipeline
        # P0-1 Fix: 每个并行任务使用独立 session，避免并发共享 session 报错
        from app.core.database import get_session_factory

        async def _safe_pipeline(code: str) -> dict | None:
            try:
                session_factory = get_session_factory()
                async with session_factory() as _session:
                    _svc = SentimentService(_session)
                    return await asyncio.wait_for(
                        _svc.run_pipeline(code),
                        timeout=timeout_per_index,
                    )
            except asyncio.TimeoutError:
                return None
            except Exception:
                return None

        results = await asyncio.gather(*[_safe_pipeline(code) for code in codes])

        items = []
        for code, result in zip(codes, results):
            if result is None or "error" in result:
                # 降级：尝试读单个指数缓存
                single_cache = await cache_get(f"fsa:sentiment:{code}")
                if single_cache and "data" in single_cache:
                    d = single_cache["data"]
                    items.append({
                        "index_code": code,
                        "index_name": d.get("index_name", code),
                        "composite_score": d.get("composite_score", 50.0),
                        "signal_level": d.get("signal_level", "B"),
                        "confidence_stars": d.get("confidence_stars", 2),
                        "regime": d.get("regime", "sideways"),
                    })
                continue

            items.append({
                "index_code": result["index_code"],
                "index_name": result["index_name"],
                "composite_score": result["composite_score"],
                "signal_level": result["signal_level"],
                "confidence_stars": result["confidence_stars"],
                "regime": result["regime"],
            })

        # 综合情绪（市值加权）
        weighted_score = 0.0
        total_weight = 0.0
        regime_counts: dict[str, int] = {}
        for item in items:
            w = WEIGHT_MAP.get(item["index_code"], 0.0)
            if w > 0:
                weighted_score += item["composite_score"] * w
                total_weight += w
            r = item.get("regime", "sideways")
            regime_counts[r] = regime_counts.get(r, 0) + 1

        composite_score = round(weighted_score / total_weight, 2) if total_weight > 0 else 50.0
        composite_signal = self.signal_mapper.map(composite_score)[0] if total_weight > 0 else "B"
        composite_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "sideways"

        # 仓位建议
        from app.engine.position import calculate_position
        position_advice = calculate_position(composite_score, composite_signal)

        response = {
            "code": 0,
            "data": {
                "indexes": items,
                "composite": {
                    "composite_score": composite_score,
                    "signal_level": composite_signal,
                    "regime": composite_regime,
                },
                "position_advice": {
                    "suggested_position": position_advice.suggested_position,
                    "cash_reserve": position_advice.cash_reserve,
                    "action": position_advice.action,
                    "reason": position_advice.reason,
                    "risk_level": position_advice.risk_level,
                },
                "updated_at": datetime.now().isoformat(),
            },
            "message": "ok",
        }

        await cache_set(cache_key, response, ttl=86400)
        return response

    async def get_signal_lights(
        self,
        index_code: str,
        days: int = 3,
    ) -> dict:
        """
        获取 V5.0 信号灯数据（三周期）
        """
        today = date.today()
        signals = []

        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            trade_date = d.isoformat()

            try:
                result = await self.run_pipeline(index_code, trade_date)
            except Exception:
                await self.db_session.rollback()
                result = {"error": "pipeline exception"}

            if "error" in result:
                signals.append({
                    "date": trade_date,
                    "signal_level": "B",
                    "composite_score": 50.0,
                })
            else:
                signals.append({
                    "date": trade_date,
                    "signal_level": result["signal_level"],
                    "composite_score": result["composite_score"],
                    "confidence_stars": result["confidence_stars"],
                })

        return {
            "code": 0,
            "data": {
                "index_code": index_code,
                "signals": signals,
                "updated_at": datetime.now().isoformat(),
            },
            "message": "ok",
        }

    async def get_market_snapshot(self) -> dict:
        """
        市场快照（顶部状态条数据）

        优化：并行调用 + Redis 缓存 + 降级策略
        """
        cache_key = "fsa:market-snapshot"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        index_data = await data_source.get_all_index_data()

        # 并行调用 V5 pipeline
        # P0-1 Fix: 每个并行任务使用独立 session，避免并发共享 session 报错
        from app.core.database import get_session_factory

        async def _safe_pipeline(code: str) -> dict | None:
            try:
                session_factory = get_session_factory()
                async with session_factory() as _session:
                    _svc = SentimentService(_session)
                    return await asyncio.wait_for(
                        _svc.run_pipeline(code),
                        timeout=15.0,
                    )
            except asyncio.TimeoutError:
                return None
            except Exception:
                return None

        pipeline_results = await asyncio.gather(
            *[_safe_pipeline(code) for code in DEFAULT_INDEX_CODES]
        )

        items = []
        for code, result in zip(DEFAULT_INDEX_CODES, pipeline_results):
            data = index_data.get(code, {})
            if code not in index_data:
                continue

            if result and "error" not in result:
                items.append({
                    "index_code": code,
                    "index_name": data.get("index_name", code),
                    "close": data.get("close"),
                    "change_pct": data.get("change_pct"),
                    "composite_score": result.get("composite_score", 50.0),
                    "sentiment_label": result.get("signal_level", "B"),
                    "signal_level": result.get("signal_level", "B"),
                    "confidence_stars": result.get("confidence_stars", 2),
                    "regime": result.get("regime", "sideways"),
                })
            else:
                # 降级
                items.append({
                    "index_code": code,
                    "index_name": data.get("index_name", code),
                    "close": data.get("close"),
                    "change_pct": data.get("change_pct"),
                    "composite_score": 50.0,
                    "sentiment_label": "B",
                    "signal_level": "B",
                    "confidence_stars": 2,
                    "regime": "sideways",
                })

        # 综合情绪（加权）
        weighted_score = 0.0
        weighted_confidence = 0.0
        total_weight = 0.0
        regime_counts: dict[str, int] = {}
        for item in items:
            w = WEIGHT_MAP.get(item["index_code"], 0.0)
            if w > 0:
                weighted_score += item["composite_score"] * w
                weighted_confidence += item["confidence_stars"] * w
                total_weight += w
            r = item.get("regime", "sideways")
            regime_counts[r] = regime_counts.get(r, 0) + 1

        composite_score = round(weighted_score / total_weight, 2) if total_weight > 0 else 50.0
        composite_confidence = round(weighted_confidence / total_weight) if total_weight > 0 else 2
        composite_regime = max(regime_counts, key=regime_counts.get) if regime_counts else "sideways"
        composite_signal = self.signal_mapper.map(composite_score)[0] if total_weight > 0 else "B"

        response = {
            "code": 0,
            "data": {
                "indexes": items,
                "global_sentiment": composite_signal,
                "global_score": composite_score,
                "composite_score": composite_score,
                "signal_level": composite_signal,
                "confidence_stars": int(composite_confidence),
                "regime": composite_regime,
                "conclusion": self.signal_mapper.get_conclusion(composite_signal),
                "updated_at": datetime.now().isoformat(),
            },
            "message": "ok",
        }

        await cache_set(cache_key, response, ttl=86400)
        return response

    async def get_factor_radar(self, index_code: str = "SH000300") -> dict:
        """
        因子雷达图数据（14 因子的当前分位数值）
        """
        from app.utils.code_format import to_tushare as _to_tushare
        ts_code = _to_tushare(index_code)
        cache_key = f"fsa:factor-radar:{ts_code}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        trade_date = date.today().isoformat()
        quantile = QuantileNorm(session=self.db_session)

        factors = []
        for name in FACTOR_NAMES:
            factor_cls = FACTOR_CLASSES.get(name)
            if not factor_cls:
                continue
            factor = factor_cls()
            try:
                raw_value_obj = await factor.fetch_raw(index_code, trade_date)
                raw_value = raw_value_obj.raw_value
            except Exception:
                raw_value = factor._get_default_raw_value(index_code)

            percentile = await quantile.calc_percentile(raw_value, index_code, name)

            factors.append({
                "name": name,
                "label": factor.label,
                "direction": factor.direction,
                "percentile": round(percentile * 100, 1) if percentile else 50.0,
                "weight": factor.weight,
            })

        response = {
            "code": 0,
            "data": {
                "index_code": index_code,
                "factors": factors,
                "trade_date": trade_date,
            },
            "message": "ok",
        }

        await cache_set(cache_key, response, ttl=86400)
        return response

    async def get_divergence_alert(self) -> dict:
        """
        全指数背离检测（Dashboard 顶部预警横幅数据源）
        """
        cache_key = "fsa:divergence-alert"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        alerts = []
        all_clear = True

        for code in DEFAULT_INDEX_CODES:
            try:
                price_history = await self.history_store.get_series(
                    self.db_session, code, "CLOSE", lookback_days=30,
                )
                sentiment_history = await self.history_store.get_series(
                    self.db_session, code, "COMPOSITE", lookback_days=30,
                )

                if len(price_history) < 5 or len(sentiment_history) < 5:
                    continue

                result = self.divergence_detector.detect(price_history, sentiment_history)
                if result["divergence_type"]:
                    all_clear = False
                    from app.utils.code_format import INDEX_REGISTRY
                    index_name = INDEX_REGISTRY.get(to_tushare(code), code)
                    alerts.append({
                        "index_code": to_display(code),
                        "index_name": index_name,
                        "divergence_type": result["divergence_type"],
                        "strength": result["strength"],
                        "description": result["description"],
                        "price_trend": result["price_trend"],
                        "sentiment_trend": result["sentiment_trend"],
                    })
            except Exception as e:
                logger.warning(f"背离检测异常 {code}: {e}")

        response = {
            "code": 0,
            "data": {
                "all_clear": all_clear,
                "alerts": sorted(alerts, key=lambda x: x["strength"], reverse=True),
                "checked_at": datetime.now().isoformat(),
            },
            "message": "ok",
        }

        await cache_set(cache_key, response, ttl=86400)
        return response

    # ===== Private helpers =====

    async def _run_factor_pipeline(
        self,
        index_code: str,
        trade_date: str,
    ) -> list[FactorSigmoidResult]:
        """
        Layer 1+2：14 因子 fetch → quantile → sigmoid

        P2-2 优化：asyncio.gather 并发执行，单因子失败不影响其他
        """
        # 收集所有因子实例
        factors = []
        for name in FACTOR_NAMES:
            factor_cls = FACTOR_CLASSES.get(name)
            if not factor_cls:
                continue
            factors.append((name, factor_cls()))

        # 顺序执行每个因子的 fetch -> quantile -> sigmoid
        # P0-1 Fix: 避免同一 session 的并发访问导致 concurrent operations not permitted
        results = []
        for name, factor in factors:
            r = await self._process_single_factor(name, factor, index_code, trade_date)
            if r is not None:
                results.append(r)
        return results

    async def _process_single_factor(
        self,
        name: str,
        factor,
        index_code: str,
        trade_date: str,
    ) -> Optional[FactorSigmoidResult]:
        """
        处理单个因子：fetch_raw → quantile → sigmoid

        P2-2：单因子失败时返回 None（不影响其他因子）
        """
        try:
            try:
                raw_value_obj = await factor.fetch_raw(index_code, trade_date)
                raw_value = raw_value_obj.raw_value
            except Exception:
                raw_value = factor._get_default_raw_value(index_code)

            # 存储 raw_value 到 factor_history（所有14个因子）
            try:
                await self.history_store.insert(
                    self.db_session, index_code, name, trade_date, float(raw_value),
                )
            except Exception:
                pass  # 存储失败不影响流水线

            percentile = await self.quantile.calc_percentile(raw_value, index_code, name)
            x = percentile if percentile is not None else 0.50
            sigmoid_score = self.sigmoid_mapper.apply_sigmoid(x, factor.sigmoid_c, factor.sigmoid_k)

            if factor.direction == "fear":
                sigmoid_score = 100.0 - sigmoid_score

            return FactorSigmoidResult(
                factor_name=name,
                percentile=percentile if percentile is not None else 0.50,
                sigmoid_score=sigmoid_score,
                c_param=factor.sigmoid_c,
                k_param=factor.sigmoid_k,
                slope_at_midpoint=0.0,
            )
        except Exception as e:
            logger.warning(f"[V5 Pipeline] 因子 {name} 处理失败: {e}")
            return None

    async def _load_prev_signal(
        self,
        index_code: str,
        current_score: float,
    ) -> tuple[Optional[str], Optional[float], int]:
        """
        读取前一日信号（用于防跳变）

        Returns:
            (prev_level, prev_score, consecutive_same)
        """
        prev_level = None
        prev_score = None
        consecutive_same = 0
        try:
            ts_code = to_tushare(index_code)
            stmt = (
                select(MarketSentiment)
                .where(
                    MarketSentiment.index_code == ts_code,
                    MarketSentiment.signal_level.isnot(None),
                )
                .order_by(MarketSentiment.trade_date.desc())
                .limit(1)
            )
            prev_result = await self.db_session.execute(stmt)
            prev_row = prev_result.scalar_one_or_none()
            if prev_row:
                prev_level = prev_row.signal_level
                prev_score = prev_row.composite_score
                if prev_level in self.signal_mapper.LEVELS:
                    current_idx = self.signal_mapper.LEVELS.index(
                        self.signal_mapper._score_to_level(current_score)
                    )
                    prev_idx = self.signal_mapper.LEVELS.index(prev_level)
                    if (current_idx > 2 and prev_idx > 2) or (current_idx < 2 and prev_idx < 2):
                        stmt2 = (
                            select(MarketSentiment.signal_level)
                            .where(
                                MarketSentiment.index_code == ts_code,
                                MarketSentiment.signal_level.isnot(None),
                            )
                            .order_by(MarketSentiment.trade_date.desc())
                            .limit(5)
                        )
                        recent_result = await self.db_session.execute(stmt2)
                        recent_levels = [r[0] for r in recent_result]
                        for rl in recent_levels:
                            if rl in self.signal_mapper.LEVELS:
                                rl_idx = self.signal_mapper.LEVELS.index(rl)
                                if (current_idx > 2 and rl_idx > 2) or (current_idx < 2 and rl_idx < 2):
                                    consecutive_same += 1
                                else:
                                    break
        except Exception:
            pass
        return prev_level, prev_score, consecutive_same

    async def _compute_macd_and_history(
        self,
        db_session: AsyncSession,
        index_code: str,
        trade_date: str,
        composite_score: float,
        index_data: dict,
    ) -> tuple[Optional[dict], list, list, list[dict], Optional[dict], list[dict], Optional[dict]]:
        """
        计算 MACD + 加载价格/情绪历史 + MACD 历史序列
        """
        macd_data = None
        sentiment_history = []
        price_history = []
        macd_history = []
        price_macd_data = None
        price_macd_history: list[dict] = []
        divergence_data = None
        try:
            # 获取情绪历史（含日期），用于 MACD 计算和历史序列对齐
            sentiment_history_with_dates = await self.history_store.get_series_with_dates(
                db_session, index_code, "COMPOSITE", lookback_days=120,
            )
            sentiment_history = [v for _, v in sentiment_history_with_dates]
            sentiment_dates = [d for d, _ in sentiment_history_with_dates]

            score_series_for_macd = sentiment_history + [composite_score]
            macd_data = self.macd_engine.compute(score_series_for_macd)

            # 计算 MACD 历史序列（DIF/DEA/HIST）供前端可视化
            macd_history_raw = self.macd_engine.compute_history(score_series_for_macd)

            # 对齐日期：MACD 历史序列对应 score_series 的尾部
            all_dates = sentiment_dates + [trade_date]
            total_len = len(score_series_for_macd)
            macd_hist_len = len(macd_history_raw)
            if macd_hist_len > 0 and len(all_dates) == total_len:
                offset = total_len - macd_hist_len
                macd_history = [
                    {"date": all_dates[offset + i], **macd_history_raw[i]}
                    for i in range(macd_hist_len)
                ]
                # 去重：因子流水线已存储今日 COMPOSITE，导致 sentiment_history
                # 末尾可能已包含 trade_date，追加后产生重复日期。
                # 保留最后一条（与 macd 快照一致），移除倒数第二条重复项。
                if (
                    len(macd_history) >= 2
                    and macd_history[-1]["date"] == macd_history[-2]["date"]
                ):
                    macd_history.pop(-2)

            close_history_with_dates = await self.history_store.get_series_with_dates(
                db_session, index_code, "CLOSE", lookback_days=120,
            )
            price_history = [v for _, v in close_history_with_dates]
            close_dates = [d for d, _ in close_history_with_dates]
            today_close = index_data.get("close")
            if today_close:
                price_history.append(float(today_close))
                close_dates.append(trade_date)

            # 价格MACD计算（12/26/9经典参数）
            from app.engine.price_macd import PriceMACD
            price_macd_engine = PriceMACD()
            price_macd_data = price_macd_engine.compute(price_history)
            price_macd_history_raw = price_macd_engine.compute_history(price_history)

            # 对齐日期：使用 CLOSE 自己的日期序列
            total_len_price = len(price_history)
            pm_hist_len = len(price_macd_history_raw)
            if pm_hist_len > 0 and len(close_dates) == total_len_price:
                offset = total_len_price - pm_hist_len
                price_macd_history = [
                    {"date": close_dates[offset + i], **price_macd_history_raw[i]}
                    for i in range(pm_hist_len)
                ]
                if (
                    len(price_macd_history) >= 2
                    and price_macd_history[-1]["date"] == price_macd_history[-2]["date"]
                ):
                    price_macd_history.pop(-2)

            # MACD背离检测（价格MACD vs 情绪MACD）
            divergence_data = self.divergence_detector.detect_macd_divergence(
                price_macd_history=price_macd_history,
                sentiment_macd_history=macd_history,
                window=20,
            )
        except Exception:
            macd_data = None
            price_macd_data = None
            price_macd_history = []
            divergence_data = None
        return macd_data, sentiment_history, price_history, macd_history, price_macd_data, price_macd_history, divergence_data

    async def _store_history(
        self,
        index_code: str,
        trade_date: str,
        composite_score: float,
        index_data: dict,
    ) -> None:
        """
        存储今日 composite_score 和收盘价到 factor_history
        """
        try:
            # COMPOSITE 已由 _process_single_factor 存储，这里不再重复
            # CLOSE 也由因子引擎存储，这里保留降级存储
            today_close = index_data.get("close")
            if today_close:
                await self.history_store.insert(
                    self.db_session, index_code, "CLOSE", trade_date, float(today_close),
                )
        except Exception:
            pass

    async def _save_market_sentiment(
        self,
        index_code: str,
        index_name: str,
        trade_date: str,
        composite_score: float,
        signal_level: str,
        confidence_stars: int,
        confidence_detail: dict,
        defenses: list,
        factor_std: float,
        penalty_factor: float,
        regime: str,
    ) -> None:
        """
        写入/更新 market_sentiment 表
        """
        try:
            ts_code = to_tushare(index_code)
            td_date = date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date

            stmt = (
                select(MarketSentiment)
                .where(
                    MarketSentiment.index_code == ts_code,
                    MarketSentiment.trade_date == td_date,
                )
            )
            existing = await self.db_session.execute(stmt)
            row = existing.scalar_one_or_none()

            if row is None:
                row = MarketSentiment(
                    index_code=ts_code,
                    index_name=index_name,
                    trade_date=td_date,
                )
                self.db_session.add(row)

            row.composite_score = round(composite_score, 2)
            row.signal_level = signal_level
            row.confidence_stars = confidence_stars
            row.confidence_detail = json.dumps(confidence_detail, ensure_ascii=False) if confidence_detail else None
            row.factor_std = round(factor_std, 4)
            row.triggered_defenses = json.dumps(defenses, ensure_ascii=False) if defenses else None
            row.divergence_index = round(penalty_factor, 4)
            row.trend_direction = regime
            row.record_time = datetime.now()

            await self.db_session.commit()
        except Exception as e:
            logger.error(
                "[V5 Pipeline] market_sentiment 落库失败: index=%s, date=%s, error=%s",
                index_code, trade_date, e,
            )


# 解决循环引用：在方法内部导入 timedelta
from datetime import timedelta
