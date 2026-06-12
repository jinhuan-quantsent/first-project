"""
融资融券数据模型
"""
from datetime import date

from sqlalchemy import String, Date, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MarketMargin(Base, TimestampMixin):
    """融资融券数据表"""
    __tablename__ = "market_margin"

    trade_date: Mapped[date] = mapped_column(Date, index=True, comment="交易日期")
    market: Mapped[str] = mapped_column(String(10), default="SH", comment="市场: SH/SZ")

    # 融资
    margin_buy: Mapped[float] = mapped_column(Float, default=0.0, comment="融资买入额(亿)")
    margin_balance: Mapped[float] = mapped_column(Float, default=0.0, comment="融资余额(亿)")
    margin_repay: Mapped[float] = mapped_column(Float, default=0.0, comment="融资偿还额(亿)")

    # 融券
    short_sell: Mapped[float] = mapped_column(Float, default=0.0, comment="融券卖出量(亿股)")
    short_balance: Mapped[float] = mapped_column(Float, default=0.0, comment="融券余额(亿)")

    # 衍生指标
    margin_ratio: Mapped[float] = mapped_column(Float, default=0.0, comment="融资余额占比(%)")
    short_ratio: Mapped[float] = mapped_column(Float, default=0.0, comment="融券余额占比(%)")
    net_margin_flow: Mapped[float] = mapped_column(Float, default=0.0, comment="融资净流入(亿)")

    def __repr__(self) -> str:
        return f"<MarketMargin(date={self.trade_date}, market={self.market})>"
