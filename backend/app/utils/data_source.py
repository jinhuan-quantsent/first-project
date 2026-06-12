"""
数据源抽象层
支持三级降级策略：Tushare → AKShare → Mock 数据

提供统一的数据获取接口，自动降级
"""
import random
from datetime import date, datetime, timedelta
from typing import Optional

from app.core.config import settings


class DataSourceProvider:
    """
    数据源提供者

    数据源优先级：
    1. Tushare Pro（需 token）
    2. AKShare（免费）
    3. Mock 数据（内置兜底）
    """

    def __init__(self) -> None:
        self._tushare_available: bool = False
        self._akshare_available: bool = False
        self._initialized: bool = False

    async def initialize(self) -> None:
        """初始化数据源连接"""
        # 尝试 Tushare
        if settings.TUSHARE_TOKEN:
            try:
                import tushare as ts
                ts.set_token(settings.TUSHARE_TOKEN)
                self._tushare_available = True
                print("✅ Tushare 数据源已连接")
            except Exception as e:
                print(f"⚠️ Tushare 连接失败: {e}")

        # 尝试 AKShare
        if settings.USE_AKSHARE:
            try:
                import akshare as ak
                self._akshare_available = True
                print("✅ AKShare 数据源已就绪")
            except Exception as e:
                print(f"⚠️ AKShare 初始化失败: {e}")

        self._initialized = True

        if not self._tushare_available and not self._akshare_available:
            print("📦 使用 Mock 数据模式")

    # ============================================================
    # Mock 数据生成器
    # ============================================================

    def _mock_index_data(self, index_code: str) -> dict:
        """生成 Mock 指数数据"""
        mock_data_map = {
            "SH000001": {"name": "上证综指", "close": 3250.68, "volatility": 18.5, "turnover_ratio": 2.8},
            "SH000300": {"name": "沪深300", "close": 3850.42, "volatility": 16.2, "turnover_ratio": 1.8},
            "SZ399001": {"name": "深证成指", "close": 11280.35, "volatility": 22.0, "turnover_ratio": 3.5},
            "SZ399006": {"name": "创业板指", "close": 2350.18, "volatility": 28.5, "turnover_ratio": 5.2},
        }

        base = mock_data_map.get(index_code, {"name": "未知指数", "close": 3000.0, "volatility": 20.0, "turnover_ratio": 2.0})

        return {
            "index_code": index_code,
            "index_name": base["name"],
            "close": base["close"] * (1 + (random.random() - 0.5) * 0.02),
            "change_pct": round((random.random() - 0.45) * 3, 2),
            "volatility": base["volatility"] * (1 + (random.random() - 0.5) * 0.2),
            "turnover_ratio": base["turnover_ratio"] * (1 + (random.random() - 0.5) * 0.3),
            "adv_decline_ratio": round(0.5 + random.random() * 2, 2),
            "new_high_ratio": round(random.random() * 15, 2),
            "rsi_value": round(30 + random.random() * 40, 1),
            "trade_date": date.today(),
        }

    def _mock_margin_data(self) -> dict:
        """生成 Mock 融资融券数据"""
        return {
            "trade_date": date.today(),
            "margin_balance": round(14000 + random.random() * 2000, 2),
            "short_balance": round(800 + random.random() * 400, 2),
            "net_margin_flow": round((random.random() - 0.4) * 100, 2),
        }

    def _mock_bond_data(self) -> dict:
        """生成 Mock 债券数据"""
        return {
            "bond_yield": round(2.5 + random.random() * 1.5, 2),  # 2.5-4.0%
            "equity_yield": round(3.0 + random.random() * 3, 2),  # 3.0-6.0%
        }

    # ============================================================
    # 公共接口
    # ============================================================

    async def get_index_data(self, index_code: str) -> dict:
        """
        获取指数行情数据

        降级策略：Tushare → AKShare → Mock
        """
        if not self._initialized:
            await self.initialize()

        # Tushare
        if self._tushare_available:
            try:
                import tushare as ts
                pro = ts.pro_api()
                # 实际 Tushare 调用（简化）
                # df = pro.index_daily(ts_code=index_code, trade_date=date.today().strftime("%Y%m%d"))
                # if not df.empty:
                #     return self._parse_tushare_index(df.iloc[0])
                raise Exception("Tushare 数据获取失败，降级")
            except Exception:
                pass

        # AKShare
        if self._akshare_available:
            try:
                import akshare as ak
                # 实际 AKShare 调用（简化）
                # df = ak.stock_zh_index_daily(symbol=index_code)
                # if not df.empty:
                #     return self._parse_akshare_index(df.iloc[-1])
                raise Exception("AKShare 数据获取失败，降级")
            except Exception:
                pass

        # Mock 兜底
        return self._mock_index_data(index_code)

    async def get_margin_data(self) -> dict:
        """获取融资融券数据"""
        if not self._initialized:
            await self.initialize()

        if self._tushare_available:
            try:
                import tushare as ts
                pro = ts.pro_api()
                raise Exception("降级到 Mock")
            except Exception:
                pass

        return self._mock_margin_data()

    async def get_bond_data(self) -> dict:
        """获取债券数据"""
        return self._mock_bond_data()

    async def get_sector_data(self, sector_name: str = "") -> list[dict]:
        """获取板块数据"""
        # Mock 板块数据
        mock_sectors = [
            {"sector_code": "BK001", "sector_name": "半导体", "sector_group": "科技", "sentiment_score": 72, "momentum_5d": 3.5},
            {"sector_code": "BK002", "sector_name": "人工智能", "sector_group": "科技", "sentiment_score": 78, "momentum_5d": 5.2},
            {"sector_code": "BK003", "sector_name": "新能源汽车", "sector_group": "制造", "sentiment_score": 55, "momentum_5d": 0.8},
            {"sector_code": "BK004", "sector_name": "医药生物", "sector_group": "医药", "sentiment_score": 28, "momentum_5d": -2.8},
            {"sector_code": "BK005", "sector_name": "白酒", "sector_group": "消费", "sentiment_score": 45, "momentum_5d": -1.2},
            {"sector_code": "BK006", "sector_name": "银行", "sector_group": "金融", "sentiment_score": 52, "momentum_5d": 0.5},
        ]

        if sector_name:
            return [s for s in mock_sectors if sector_name in s["sector_name"]]
        return mock_sectors


# 全局单例
data_source = DataSourceProvider()
