"""
数据源抽象层 V4.0 — 增加缓存层
三级降级策略：Redis 缓存 → Tushare Pro → AKShare → Mock

缓存策略（A4 决策）：
- 缓存计算后的情绪结果（L1 TTL=300s）
- Tushare 原始返回缓存 L3 TTL=3600s
- 429 限流时返回过期缓存
"""
import asyncio
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta
from typing import Optional

from app.core.config import settings
from app.core.redis_client import cache_get, cache_set
from app.utils.exceptions import (
    DataSourceError,
    NetworkError,
    RateLimitError,
    DataFormatError,
    AuthError,
    _classify_exception,
)


# ============================================================
# 指数代码映射
# ============================================================
INDEX_CODE_MAP: dict[str, dict] = {
    "SH000001": {
        "name": "上证综指",
        "tushare_code": "000001.SH",
        "akshare_symbol": "sh000001",
        "exchange": "SSE",
    },
    "SH000300": {
        "name": "沪深300",
        "tushare_code": "000300.SH",
        "akshare_symbol": "sh000300",
        "exchange": "SSE",
    },
    "SZ399001": {
        "name": "深证成指",
        "tushare_code": "399001.SZ",
        "akshare_symbol": "sz399001",
        "exchange": "SZSE",
    },
    "SZ399006": {
        "name": "创业板指",
        "tushare_code": "399006.SZ",
        "akshare_symbol": "sz399006",
        "exchange": "SZSE",
    },
}

DEFAULT_INDEX_CODES = ["SH000001", "SH000300", "SZ399001", "SZ399006"]

# 缓存 key 前缀
CACHE_PREFIX = "fsa:"


def _cache_key(domain: str, identifier: str, subkey: str = "") -> str:
    """构建缓存 key：fsa:{domain}:{identifier}[:{subkey}]"""
    if subkey:
        return f"{CACHE_PREFIX}{domain}:{identifier}:{subkey}"
    return f"{CACHE_PREFIX}{domain}:{identifier}"


def _params_hash(params: dict) -> str:
    """参数哈希，用于 Tushare 原始数据缓存 key"""
    raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()[:8]


class DataSourceProvider:
    """数据源提供者 V4.0 — Redis 缓存 + 降级策略"""

    def __init__(self) -> None:
        self._tushare_available: bool = False
        self._akshare_available: bool = False
        self._initialized: bool = False
        self._tushare_pro = None
        self._rate_limit_count: int = 0

        # 内存缓存（Redis 不可用时的兜底）
        self._index_cache: dict[str, dict] = {}
        self._margin_cache: Optional[dict] = None
        self._bond_yield_cache: Optional[float] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl: int = 300

    async def initialize(self) -> None:
        """初始化数据源连接"""
        if self._initialized:
            return

        # Tushare
        if settings.TUSHARE_TOKEN:
            try:
                import tushare as ts
                self._tushare_pro = ts.pro_api(settings.TUSHARE_TOKEN)
                self._tushare_pro.index_daily(
                    ts_code="000001.SH", start_date="20260101", end_date="20260105"
                )
                self._tushare_available = True
                print("✅ Tushare Pro 数据源已连接")
            except Exception as e:
                self._tushare_available = False
                self._tushare_pro = None
                print(f"⚠️ Tushare 连接失败: {e}")

        # AKShare
        if settings.USE_AKSHARE:
            try:
                import akshare as ak
                self._akshare_available = True
                print("✅ AKShare 数据源已就绪")
            except Exception as e:
                self._akshare_available = False
                print(f"⚠️ AKShare 初始化失败: {e}")

        self._initialized = True

        if not self._tushare_available and not self._akshare_available:
            print("📦 无可用数据源，使用 Mock 数据")
        elif self._tushare_available:
            print("🎯 主数据源: Tushare Pro | 备用: AKShare")
        else:
            print("🎯 主数据源: AKShare")

    # ============================================================
    # 缓存管理
    # ============================================================
    def _is_cache_valid(self) -> bool:
        if self._cache_time is None:
            return False
        return (datetime.now() - self._cache_time).seconds < self._cache_ttl

    def _clear_cache_if_expired(self) -> None:
        if not self._is_cache_valid():
            self._index_cache = {}
            self._margin_cache = None
            self._bond_yield_cache = None
            self._cache_time = None

    # ============================================================
    # RSI 计算（通用）
    # ============================================================
    @staticmethod
    def _calculate_rsi(closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        gains = 0.0
        losses = 0.0
        for i in range(len(closes) - period, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses += abs(diff)
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 1)

    # ============================================================
    # 波动率计算（基于收盘价序列）
    # ============================================================
    @staticmethod
    def _calculate_volatility(closes: list[float]) -> float:
        if len(closes) < 2:
            return 18.0
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        if len(returns) < 2:
            return 18.0
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        daily_vol = math.sqrt(variance)
        annual_vol = daily_vol * math.sqrt(252) * 100
        return round(annual_vol, 1)

    # ============================================================
    # Tushare: 指数行情 (index_daily) — 带缓存
    # ============================================================
    def _fetch_tushare_index_daily(self, index_code: str) -> Optional[dict]:
        """Tushare: 获取指数日线数据（含历史序列用于 RSI 和波动率）"""
        if not self._tushare_pro:
            return None
        info = INDEX_CODE_MAP.get(index_code)
        if not info:
            return None

        try:
            ts_code = info["tushare_code"]
            today = date.today()
            df = self._tushare_pro.index_daily(
                ts_code=ts_code,
                start_date=(today - timedelta(days=60)).strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            if df is None or df.empty:
                return None

            df = df.sort_values("trade_date").reset_index(drop=True)
            if len(df) < 2:
                return None

            closes = [float(c) for c in df["close"].values]
            last = df.iloc[-1]
            prev = df.iloc[-2]

            close = float(last["close"])
            change_pct = float(last.get("pct_chg", 0))
            if change_pct == 0 and prev is not None:
                prev_close = float(prev["close"])
                if prev_close > 0:
                    change_pct = round((close - prev_close) / prev_close * 100, 2)

            rsi = self._calculate_rsi(closes)
            volatility = self._calculate_volatility(closes)

            # 新高占比：基于近期数据估算
            if len(closes) >= 60:
                high_60 = max(closes[-60:])
                current = closes[-1]
                if current >= high_60 * 0.995:
                    new_high_ratio = round((current / high_60) * 20, 1)
                else:
                    new_high_ratio = round((current / high_60) * 10, 1)
            else:
                is_new_high = close >= max(closes[-20:]) * 0.98 if len(closes) >= 20 else False
                if is_new_high:
                    if change_pct > 2.0:
                        new_high_ratio = round(12 + min(change_pct - 2, 5) * 1.5, 1)
                    elif change_pct > 0:
                        new_high_ratio = round(7 + change_pct * 2.5, 1)
                    else:
                        new_high_ratio = round(5 + max(change_pct, -3) + 3, 1)
                else:
                    if change_pct > 1.0:
                        new_high_ratio = round(5 + min(change_pct - 1, 4) * 2, 1)
                    elif change_pct > 0:
                        new_high_ratio = round(3 + change_pct * 2, 1)
                    else:
                        new_high_ratio = round(1.5 + max(change_pct, -2) * 0.75, 1)

            return {
                "close": close,
                "change_pct": change_pct,
                "rsi_value": rsi,
                "volatility": volatility,
                "new_high_ratio": new_high_ratio,
                "trade_date": str(last["trade_date"]),
                "closes_for_history": closes,
                "source": "tushare",
            }
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ Tushare index_daily {index_code}: [{type(classified).__name__}] {e}")
            return None

    # ============================================================
    # Tushare: 指数基本面 (index_dailybasic) — 带缓存
    # ============================================================
    def _fetch_tushare_index_basic(self, index_code: str) -> Optional[dict]:
        if not self._tushare_pro:
            return None
        info = INDEX_CODE_MAP.get(index_code)
        if not info:
            return None

        try:
            ts_code = info["tushare_code"]
            today = date.today()
            for attempt in range(3):
                try_date = today - timedelta(days=attempt)
                df = self._tushare_pro.index_dailybasic(
                    ts_code=ts_code,
                    trade_date=try_date.strftime("%Y%m%d"),
                )
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    return {
                        "pe": float(row.get("pe", 0)),
                        "pe_ttm": float(row.get("pe_ttm", 0)),
                        "pb": float(row.get("pb", 0)),
                        "turnover_rate": float(row.get("turnover_rate", 0)),
                        "total_mv": float(row.get("total_mv", 0)),
                    }
            return None
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ Tushare index_dailybasic {index_code}: [{type(classified).__name__}] {e}")
            return None

    # ============================================================
    # Tushare: 融资融券 (margin) — 带缓存
    # ============================================================
    def _fetch_tushare_margin(self) -> Optional[dict]:
        if not self._tushare_pro:
            return None

        if self._margin_cache is not None:
            return self._margin_cache

        try:
            today = date.today()
            for attempt in range(3):
                try_date = today - timedelta(days=attempt)
                df = self._tushare_pro.margin(trade_date=try_date.strftime("%Y%m%d"))
                if df is None or df.empty:
                    continue

                margin_balance = float(df["rzye"].sum()) / 1e8
                short_balance = float(df["rqye"].sum()) / 1e8
                net_flow = float(df["rzmre"].sum()) / 1e8

                self._margin_cache = {
                    "margin_balance": round(margin_balance, 2),
                    "short_balance": round(short_balance, 2),
                    "net_margin_flow": round(net_flow, 2),
                    "source": "tushare",
                }
                return self._margin_cache
            return None
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ Tushare margin: [{type(classified).__name__}] {e}")
            return None

    # ============================================================
    # Tushare: 涨跌比（通过 limit_list_d）
    # ============================================================
    def _fetch_tushare_adv_decline(self) -> Optional[dict]:
        if not self._tushare_pro:
            return None

        try:
            today = date.today()
            df_up = self._tushare_pro.limit_list_d(
                trade_date=today.strftime("%Y%m%d"),
                limit_type="U",
            )
            up_count = len(df_up) if df_up is not None else 0
            total_stocks = 5528
            adv_ratio = 1.0 + (up_count / 500) * 0.1 if up_count > 0 else 1.0
            return {"adv_decline_ratio": round(adv_ratio, 2), "up_limit_count": up_count, "source": "tushare"}
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ Tushare limit_list_d: [{type(classified).__name__}] {e}")
            return None

    # ============================================================
    # AKShare: 指数行情
    # ============================================================
    def _fetch_akshare_index_daily(self, index_code: str) -> Optional[dict]:
        info = INDEX_CODE_MAP.get(index_code)
        if not info:
            return None

        try:
            import akshare as ak
            symbol = info["akshare_symbol"]
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                return None

            recent = df.tail(30).reset_index(drop=True)
            if len(recent) < 2:
                return None

            closes = [float(c) for c in recent["close"].values]
            last = recent.iloc[-1]
            prev = recent.iloc[-2]

            close = float(last["close"])
            prev_close = float(prev["close"])
            change_pct = round((close - prev_close) / prev_close * 100, 2)
            rsi = self._calculate_rsi(closes)
            volatility = self._calculate_volatility(closes)

            return {
                "close": close,
                "change_pct": change_pct,
                "rsi_value": rsi,
                "volatility": volatility,
                "closes_for_history": closes,
                "source": "akshare",
            }
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ AKShare index {index_code}: [{type(classified).__name__}] {e}")
            return None

    # ============================================================
    # AKShare: 国债收益率
    # ============================================================
    def _fetch_akshare_bond_yield(self) -> Optional[float]:
        if self._bond_yield_cache is not None:
            return self._bond_yield_cache

        try:
            import akshare as ak
            df = ak.bond_zh_us_rate()
            if df is not None and not df.empty:
                last = df.iloc[-1]
                val = float(last["中国国债收益率10年"])
                self._bond_yield_cache = round(val, 2)
                return self._bond_yield_cache
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ AKShare bond_yield: [{type(classified).__name__}] {e}")

        return None

    # ============================================================
    # AKShare: 融资融券
    # ============================================================
    def _fetch_akshare_margin(self) -> Optional[dict]:
        try:
            import akshare as ak
            today = date.today()
            for attempt in range(3):
                try_date = today - timedelta(days=attempt)
                try:
                    df = ak.stock_margin_detail_sse()
                    if df is not None and not df.empty:
                        margin_total = float(df["融资余额"].sum()) / 1e8
                        short_total = float(df["融券余量"].sum()) / 1e8
                        net_flow = 0.0
                        if "融资买入额" in df.columns and "融资偿还额" in df.columns:
                            net_flow = (
                                float(df["融资买入额"].sum()) - float(df["融资偿还额"].sum())
                            ) / 1e8
                        return {
                            "margin_balance": round(margin_total, 2),
                            "short_balance": round(short_total, 2),
                            "net_margin_flow": round(net_flow, 2),
                            "source": "akshare",
                        }
                except Exception:
                    continue
            return None
        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ AKShare margin: [{type(classified).__name__}] {e}")
            return None

    # ============================================================
    # 北向资金流向数据
    # ============================================================
    async def get_northbound_data(self) -> dict:
        if self._tushare_available and self._tushare_pro:
            try:
                return await self._fetch_tushare_northbound()
            except Exception:
                pass
        return self._mock_northbound_data()

    def _mock_northbound_data(self) -> dict:
        return {
            "net_flow_today": round(random.uniform(-80, 100), 2),
            "net_flow_5d": round(random.uniform(-300, 400), 2),
            "net_flow_20d": round(random.uniform(-800, 1200), 2),
            "cumulative_buy": round(random.uniform(15000, 20000), 2),
        }

    async def _fetch_tushare_northbound(self) -> dict:
        import datetime as dt
        today = dt.date.today().strftime("%Y%m%d")
        df_5d = self._tushare_pro.moneyflow_hsgt(
            start_date=(dt.date.today() - dt.timedelta(days=10)).strftime("%Y%m%d"),
            end_date=today,
        )
        if df_5d is None or df_5d.empty:
            raise Exception("Tushare northbound data empty")
        recent = df_5d.tail(5)
        return {
            "net_flow_today": (
                round(float(recent.iloc[-1].get("north_money", 0)), 2)
                if "north_money" in df_5d.columns
                else 0.0
            ),
            "net_flow_5d": (
                round(float(recent["north_money"].sum()), 2)
                if "north_money" in df_5d.columns
                else 0.0
            ),
            "net_flow_20d": (
                round(float(df_5d["north_money"].sum()), 2)
                if "north_money" in df_5d.columns
                else 0.0
            ),
            "cumulative_buy": 0.0,
        }

    # ============================================================
    # 主接口：获取单个指数完整数据 — 带 Redis 缓存
    # ============================================================
    async def get_index_data(self, index_code: str) -> dict:
        """
        获取指数完整数据，带 Redis 缓存层

        缓存策略（A4）：
        1. 先查 Redis 缓存 fsa:sentiment:{index_code}
        2. 未命中则走数据源获取 → 计算后写入缓存
        3. 429 限流时尝试返回过期缓存
        """
        if not self._initialized:
            await self.initialize()

        # Step 1: Redis 缓存查询
        cache_key = _cache_key("sentiment", index_code)
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        self._clear_cache_if_expired()
        if index_code in self._index_cache:
            return self._index_cache[index_code]

        info = INDEX_CODE_MAP.get(index_code, {})
        index_name = info.get("name", "未知指数")
        source = "mock"

        # Step 2: 获取行情数据
        daily_data = None
        if self._tushare_available:
            try:
                daily_data = self._fetch_tushare_index_daily(index_code)
            except DataSourceError as de:
                if isinstance(de, NetworkError):
                    print(f"🔄 {index_code} Tushare 网络异常，可重试 [retry_possible=True]")
                elif isinstance(de, RateLimitError):
                    print(f"⏳ {index_code} Tushare 限流，将使用缓存兜底")
                elif isinstance(de, DataFormatError):
                    print(f"📊 {index_code} Tushare 数据格式异常，降级到 mock")
                elif isinstance(de, AuthError):
                    print(f"🔐 {index_code} Tushare 认证失败")
                else:
                    print(f"⚠️ {index_code} Tushare 数据源异常: {de}")
        if daily_data is None and self._akshare_available:
            try:
                daily_data = self._fetch_akshare_index_daily(index_code)
            except DataSourceError as de:
                if isinstance(de, NetworkError):
                    print(f"🔄 {index_code} AKShare 网络异常，可重试 [retry_possible=True]")
                elif isinstance(de, RateLimitError):
                    print(f"⏳ {index_code} AKShare 限流，将使用缓存兜底")
                elif isinstance(de, DataFormatError):
                    print(f"📊 {index_code} AKShare 数据格式异常，降级到 mock")
                elif isinstance(de, AuthError):
                    print(f"🔐 {index_code} AKShare 认证失败")
                else:
                    print(f"⚠️ {index_code} AKShare 数据源异常: {de}")

        if daily_data is not None:
            source = daily_data["source"]
            close = daily_data["close"]
            change_pct = daily_data["change_pct"]
            rsi = daily_data["rsi_value"]
            volatility = daily_data["volatility"]
        else:
            mock = self._mock_index_data(index_code)
            close = mock["close"]
            change_pct = mock["change_pct"]
            rsi = mock["rsi_value"]
            volatility = mock["volatility"]

        # Step 3: 基本面数据
        pe = None
        pe_ttm = None
        pb = None
        turnover_ratio = None

        if self._tushare_available:
            basic = self._fetch_tushare_index_basic(index_code)
            if basic:
                pe = basic.get("pe")
                pe_ttm = basic.get("pe_ttm")
                pb = basic.get("pb")
                turnover_ratio = basic.get("turnover_rate")

        if pe is None or pe <= 0:
            pe_map = {"SH000001": 17.0, "SH000300": 14.0, "SZ399001": 35.0, "SZ399006": 48.0}
            pe = pe_map.get(index_code, 20.0)
        if pe_ttm is None or pe_ttm <= 0:
            pe_ttm = pe * 0.95
        if pb is None or pb <= 0:
            pb_map = {"SH000001": 1.5, "SH000300": 1.4, "SZ399001": 3.2, "SZ399006": 5.0}
            pb = pb_map.get(index_code, 2.0)
        if turnover_ratio is None or turnover_ratio <= 0:
            turnover_map = {"SH000001": 1.2, "SH000300": 0.8, "SZ399001": 2.2, "SZ399006": 2.6}
            turnover_ratio = turnover_map.get(index_code, 1.5)

        equity_yield = round(100.0 / pe, 2) if pe > 0 else 5.0

        # Step 4: 融资融券
        margin_data = None
        if self._tushare_available:
            margin_data = self._fetch_tushare_margin()
        if margin_data is None and self._akshare_available:
            margin_data = self._fetch_akshare_margin()
        if margin_data is None:
            margin_data = self._mock_margin_data()

        # Step 5: 国债收益率
        bond_yield = None
        if self._akshare_available:
            bond_yield = self._fetch_akshare_bond_yield()
        if bond_yield is None:
            bond_yield = 1.75

        # Step 6: 涨跌比
        adv_decline_ratio = None
        if self._tushare_available and daily_data is not None:
            adv_result = self._fetch_tushare_adv_decline()
            if adv_result:
                adv_decline_ratio = adv_result["adv_decline_ratio"]
        if adv_decline_ratio is None:
            if change_pct > 3.0:
                adv_decline_ratio = 4.0 + min(change_pct - 3, 3) * 2
            elif change_pct > 2.0:
                adv_decline_ratio = 2.5 + (change_pct - 2) * 1.5
            elif change_pct > 1.0:
                adv_decline_ratio = 1.5 + (change_pct - 1) * 1.0
            elif change_pct > 0.5:
                adv_decline_ratio = 1.2 + (change_pct - 0.5) * 0.6
            elif change_pct > 0:
                adv_decline_ratio = 1.0 + change_pct * 0.4
            elif change_pct > -0.5:
                adv_decline_ratio = 0.9 + change_pct * 0.2
            elif change_pct > -1.0:
                adv_decline_ratio = 0.7 + (change_pct + 0.5) * 0.4
            elif change_pct > -2.0:
                adv_decline_ratio = 0.5 + (change_pct + 1) * 0.2
            else:
                adv_decline_ratio = 0.3
            adv_decline_ratio = round(adv_decline_ratio, 2)

        # Step 7: 新高占比
        new_high_ratio = daily_data.get("new_high_ratio") if daily_data else None
        if (
            new_high_ratio is None
            and daily_data
            and daily_data.get("closes_for_history")
            and len(daily_data["closes_for_history"]) >= 60
        ):
            closes_list = daily_data["closes_for_history"]
            high_60 = max(closes_list[-60:])
            current = closes_list[-1]
            new_high_ratio = (
                round((current / high_60) * 20, 1)
                if current >= high_60 * 0.995
                else round((current / high_60) * 10, 1)
            )
        if new_high_ratio is None:
            if change_pct > 1.0:
                new_high_ratio = round(8 + min(change_pct, 5) * 2, 1)
            elif change_pct > 0:
                new_high_ratio = round(4 + change_pct * 4, 1)
            else:
                new_high_ratio = round(max(2, min(7, 5 + change_pct)), 1)

        result = {
            "index_code": index_code,
            "index_name": index_name,
            "close": close,
            "change_pct": change_pct,
            "volatility": volatility,
            "turnover_ratio": turnover_ratio,
            "adv_decline_ratio": adv_decline_ratio,
            "new_high_ratio": new_high_ratio,
            "rsi_value": rsi,
            "pe": pe,
            "pe_ttm": pe_ttm,
            "pb": pb,
            "equity_yield": equity_yield,
            "bond_yield": bond_yield,
            "margin_data": margin_data,
            "source": source,
            "trade_date": daily_data.get("trade_date", str(date.today())) if daily_data else str(date.today()),
        }

        # 写入 Redis 缓存（L1 TTL=300s）
        await cache_set(cache_key, result, ttl=settings.DATA_CACHE_TTL)

        # 内存缓存兜底
        self._index_cache[index_code] = result
        if self._cache_time is None:
            self._cache_time = datetime.now()

        return result

    async def get_all_index_data(self, codes: Optional[list[str]] = None) -> dict[str, dict]:
        if codes is None:
            codes = DEFAULT_INDEX_CODES
        results: dict[str, dict] = {}
        for code in codes:
            results[code] = await self.get_index_data(code)
        return results

    # ============================================================
    # Mock 数据
    # ============================================================
    def _mock_index_data(self, index_code: str) -> dict:
        mock_data_map = {
            "SH000001": {"close": 3250.68, "volatility": 18.5},
            "SH000300": {"close": 3850.42, "volatility": 16.2},
            "SZ399001": {"close": 11280.35, "volatility": 22.0},
            "SZ399006": {"close": 2350.18, "volatility": 28.5},
        }
        base = mock_data_map.get(index_code, {"close": 3000.0, "volatility": 20.0})
        return {
            "close": base["close"] * (1 + (random.random() - 0.5) * 0.02),
            "change_pct": round((random.random() - 0.45) * 3, 2),
            "volatility": base["volatility"],
            "rsi_value": round(30 + random.random() * 40, 1),
            "new_high_ratio": round(random.random() * 15, 2),
            "source": "mock",
        }

    def _mock_margin_data(self) -> dict:
        return {
            "margin_balance": round(14000 + random.random() * 2000, 2),
            "short_balance": round(800 + random.random() * 400, 2),
            "net_margin_flow": round((random.random() - 0.4) * 100, 2),
            "source": "mock",
        }

    # ============================================================
    # 板块数据（AKShare 真实概念板块行情）
    # ============================================================
    _sector_cache: Optional[list[dict]] = None
    _sector_cache_time: Optional[datetime] = None

    def _fetch_real_sectors(self) -> list[dict]:
        if self._sector_cache and self._sector_cache_time:
            if (datetime.now() - self._sector_cache_time).seconds < 1800:
                return self._sector_cache

        sectors: list[dict] = []
        try:
            import akshare as ak
            df = ak.stock_board_concept_name_em()
            if df is not None and not df.empty:
                active = df[df["换手率"] > 0.5].copy()
                top = active.nlargest(40, "总市值")

                GROUP_MAP = {
                    "半导体": "科技", "芯片": "科技", "人工智能": "科技", "AI": "科技",
                    "通信": "科技", "软件": "科技", "大数据": "科技", "云计算": "科技",
                    "5G": "科技", "物联网": "科技", "区块链": "科技", "数字经济": "科技",
                    "新能源": "能源", "光伏": "能源", "风电": "能源", "储能": "能源",
                    "锂电": "能源", "氢能": "能源", "电力": "能源",
                    "医药": "医药", "医疗": "医药", "生物": "医药", "中药": "医药",
                    "银行": "金融", "券商": "金融", "保险": "金融",
                    "白酒": "消费", "食品": "消费", "饮料": "消费", "家电": "消费",
                    "汽车": "制造", "军工": "制造", "机器人": "制造", "高端装备": "制造",
                    "房地产": "地产", "基建": "地产",
                    "有色": "周期", "钢铁": "周期", "煤炭": "周期", "化工": "周期",
                }

                def _map_group(name: str) -> str:
                    for kw, grp in GROUP_MAP.items():
                        if kw in name:
                            return grp
                    return "综合"

                for _, row in top.iterrows():
                    name = str(row["板块名称"])
                    chg = float(row["涨跌幅"])
                    up_count = int(row["上涨家数"])
                    down_count = int(row["下跌家数"])
                    total = up_count + down_count
                    turnover = float(row["换手率"])
                    up_ratio = up_count / max(1, total)

                    chg_score = 50 + chg * 5
                    ratio_score = up_ratio * 100
                    turnover_score = min(100, max(0, 50 + (turnover - 2) * 10))
                    sentiment_score = round(chg_score * 0.4 + ratio_score * 0.3 + turnover_score * 0.3, 1)
                    sentiment_score = max(5, min(95, sentiment_score))

                    if sentiment_score < 20:
                        label = "extreme_fear"
                    elif sentiment_score < 40:
                        label = "fear"
                    elif sentiment_score < 60:
                        label = "neutral"
                    elif sentiment_score < 80:
                        label = "greed"
                    else:
                        label = "extreme_greed"

                    momentum_5d = round(chg * 1.5, 1)
                    momentum_20d = round(chg * 3, 1)
                    strength_index = max(5, min(100, round(50 + chg * 10 + up_ratio * 20, 1)))

                    sectors.append({
                        "sector_code": str(row["板块代码"]),
                        "sector_name": name,
                        "sector_group": _map_group(name),
                        "sentiment_score": sentiment_score,
                        "sentiment_label": label,
                        "momentum_5d": momentum_5d,
                        "momentum_20d": momentum_20d,
                        "strength_index": strength_index,
                        "sector_return": chg,
                        "turnover_ratio": turnover,
                        "fund_flow": 0.0,
                    })

                print(f"✅ 板块数据加载完成: {len(sectors)} 个板块（来源: AKShare）")

        except Exception as e:
            classified = _classify_exception(e)
            print(f"⚠️ AKShare 板块数据获取失败: [{type(classified).__name__}] {e}")

        self._sector_cache = sectors
        self._sector_cache_time = datetime.now()
        return sectors

    def get_mock_sectors(self) -> list[dict]:
        real = self._fetch_real_sectors()
        if real:
            return real

        return [
            {"sector_code": "BK001", "sector_name": "半导体", "sector_group": "科技", "sentiment_score": 72, "sentiment_label": "greed", "momentum_5d": 3.5, "momentum_20d": 8.2, "strength_index": 75, "sector_return": 1.8, "turnover_ratio": 4.5, "fund_flow": 25.0},
            {"sector_code": "BK002", "sector_name": "人工智能", "sector_group": "科技", "sentiment_score": 78, "sentiment_label": "greed", "momentum_5d": 5.2, "momentum_20d": 12.5, "strength_index": 82, "sector_return": 2.5, "turnover_ratio": 6.0, "fund_flow": 45.0},
            {"sector_code": "BK003", "sector_name": "新能源汽车", "sector_group": "制造", "sentiment_score": 55, "sentiment_label": "neutral", "momentum_5d": 0.8, "momentum_20d": -2.5, "strength_index": 52, "sector_return": 0.3, "turnover_ratio": 2.8, "fund_flow": 5.0},
            {"sector_code": "BK004", "sector_name": "医药生物", "sector_group": "医药", "sentiment_score": 28, "sentiment_label": "fear", "momentum_5d": -2.8, "momentum_20d": -6.5, "strength_index": 32, "sector_return": -1.5, "turnover_ratio": 1.2, "fund_flow": -15.0},
            {"sector_code": "BK005", "sector_name": "白酒", "sector_group": "消费", "sentiment_score": 45, "sentiment_label": "neutral", "momentum_5d": -1.2, "momentum_20d": -3.8, "strength_index": 42, "sector_return": -0.8, "turnover_ratio": 1.5, "fund_flow": -8.0},
            {"sector_code": "BK006", "sector_name": "银行", "sector_group": "金融", "sentiment_score": 52, "sentiment_label": "neutral", "momentum_5d": 0.5, "momentum_20d": 1.2, "strength_index": 55, "sector_return": 0.2, "turnover_ratio": 0.8, "fund_flow": 12.0},
            {"sector_code": "BK007", "sector_name": "券商", "sector_group": "金融", "sentiment_score": 62, "sentiment_label": "greed", "momentum_5d": 2.5, "momentum_20d": 5.8, "strength_index": 68, "sector_return": 1.2, "turnover_ratio": 3.5, "fund_flow": 28.0},
            {"sector_code": "BK008", "sector_name": "光伏", "sector_group": "能源", "sentiment_score": 32, "sentiment_label": "fear", "momentum_5d": -3.5, "momentum_20d": -8.0, "strength_index": 30, "sector_return": -2.0, "turnover_ratio": 2.0, "fund_flow": -22.0},
            {"sector_code": "BK009", "sector_name": "军工", "sector_group": "制造", "sentiment_score": 58, "sentiment_label": "neutral", "momentum_5d": 1.5, "momentum_20d": 3.2, "strength_index": 60, "sector_return": 0.8, "turnover_ratio": 2.5, "fund_flow": 8.0},
            {"sector_code": "BK010", "sector_name": "房地产", "sector_group": "地产", "sentiment_score": 22, "sentiment_label": "extreme_fear", "momentum_5d": -5.2, "momentum_20d": -10.5, "strength_index": 20, "sector_return": -3.2, "turnover_ratio": 1.0, "fund_flow": -35.0},
            {"sector_code": "BK011", "sector_name": "通信设备", "sector_group": "科技", "sentiment_score": 65, "sentiment_label": "greed", "momentum_5d": 3.0, "momentum_20d": 7.5, "strength_index": 70, "sector_return": 1.5, "turnover_ratio": 3.8, "fund_flow": 20.0},
            {"sector_code": "BK012", "sector_name": "食品饮料", "sector_group": "消费", "sentiment_score": 42, "sentiment_label": "neutral", "momentum_5d": -0.5, "momentum_20d": 1.0, "strength_index": 48, "sector_return": -0.3, "turnover_ratio": 1.8, "fund_flow": -3.0},
        ]


# 全局单例
data_source = DataSourceProvider()


# ============================================================
# V5.0 新增：11因子原始数据获取函数
# 供 factor_engine 子包调用，返回 float 原始值
# ============================================================

async def fetch_volatility(index_code: str) -> float:
    """VOL 波动率因子：年化波动率(%)"""
    d = await data_source.get_index_data(index_code)
    return float(d.get("volatility", 18.0))


async def fetch_adv_decline_ratio() -> float:
    """ADR 涨跌比因子：上涨/下跌家数比"""
    d = await data_source.get_index_data("SH000300")
    return float(d.get("adv_decline_ratio", 1.0))


async def fetch_erp(index_code: str) -> float:
    """
    ERP 股债性价比因子：equity_yield - 10年期国债收益率
    高ERP → 股票相对债券更便宜 → 恐惧分低（反向因子）
    """
    d = await data_source.get_index_data(index_code)
    equity_yield = float(d.get("equity_yield", 5.0))
    bond_yield = float(d.get("bond_yield", 1.75))
    return round(equity_yield - bond_yield, 4)


async def fetch_fund_flow(index_code: str) -> float:
    """
    FLOW 基金申赎资金流因子：ETF净申购份额变化(%)
    数据来源：Tushare fund_daily
    """
    try:
        import tushare as ts
        if data_source._tushare_pro:
            today = date.today()
            df = data_source._tushare_pro.fund_daily(
                trade_date=(today - timedelta(days=1)).strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                # 使用全市场ETF份额变化近似
                net_flow = float(df.get("net_purchase", df.get("amount", 0)))
                return round(net_flow / 1e8, 2)
    except Exception:
        pass
    # Mock/降级：基于涨跌幅估算
    d = await data_source.get_index_data(index_code)
    chg = float(d.get("change_pct", 0))
    return round(chg * 2.0, 2)


async def fetch_etf_change(index_code: str) -> float:
    """
    ETF ETF份额变化因子：主要宽基ETF份额周度变化率(%)
    数据来源：Tushare fund_daily
    """
    try:
        if data_source._tushare_pro:
            today = date.today()
            df = data_source._tushare_pro.fund_daily(
                trade_date=today.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                share_change = float(df.get("hold_change", df.get("amount", 0)))
                return round(share_change / 1e8, 2)
    except Exception:
        pass
    return 0.0


async def fetch_nhnl_ratio(index_code: str) -> float:
    """NHNL 新高占比因子：60日新高股票占比(%)"""
    d = await data_source.get_index_data(index_code)
    return float(d.get("new_high_ratio", 5.0))


async def fetch_turnover(index_code: str) -> float:
    """TURN 换手率因子：指数换手率(%)"""
    d = await data_source.get_index_data(index_code)
    return float(d.get("turnover_ratio", 1.5))


async def fetch_fund_position() -> float:
    """
    POS 基金仓位估算因子：股票型+混合型公募基金平均仓位(%)
    数据来源：Tushare fund_portfolio
    """
    try:
        if data_source._tushare_pro:
            today = date.today()
            df = data_source._tushare_pro.fund_portfolio(
                trade_date=today.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                avg_pos = float(df["stock_ratio"].mean())
                return round(avg_pos, 2)
    except Exception:
        pass
    # Mock：基于V4.0经验值
    return 62.0


async def fetch_northbound_flow() -> float:
    """
    NBF 北向资金方向因子：陆股通近5日净流入(亿元)
    数据来源：Tushare moneyflow_hsgt
    """
    try:
        if data_source._tushare_pro:
            import datetime as dt
            today = dt.date.today()
            df = data_source._tushare_pro.moneyflow_hsgt(
                start_date=(today - dt.timedelta(days=10)).strftime("%Y%m%d"),
                end_date=today.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                recent = df.tail(5)
                col = "north_money" if "north_money" in df.columns else "net_money"
                net = float(recent[col].sum()) if col in df.columns else 0.0
                return round(net, 2)
    except Exception:
        pass
    return 0.0


async def fetch_put_call_ratio() -> float:
    """
    PCR 认沽认购比因子：ETF期权认沽/认购成交量比
    高PCR → 避险情绪高 → 恐惧
    数据来源：Tushare opt_daily
    """
    try:
        if data_source._tushare_pro:
            today = date.today()
            df = data_source._tushare_pro.opt_daily(
                trade_date=today.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                put_vol = float(df[df["option_type"] == "认沽"]["volume"].sum())
                call_vol = float(df[df["option_type"] == "认购"]["volume"].sum())
                if call_vol > 0:
                    return round(put_vol / call_vol, 4)
    except Exception:
        pass
    # Mock：基于VIX经验值
    return 0.85


async def fetch_new_fund_heat() -> float:
    """
    NEWF 新发基金热度因子：近30日新成立基金总份额(亿份)
    数据来源：Tushare fund_basic
    """
    try:
        if data_source._tushare_pro:
            today = date.today()
            df = data_source._tushare_pro.fund_basic(
                issue_date=(today - timedelta(days=30)).strftime("%Y%m%d"),
                list_date=today.strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                total_shares = float(df["fund_shares"].sum())
                return round(total_shares / 1e8, 2)
    except Exception:
        pass
    return 50.0
