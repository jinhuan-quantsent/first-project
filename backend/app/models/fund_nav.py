"""
基金净值历史模型
"""
from datetime import date

from sqlalchemy import String, Date, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FundNav(Base, TimestampMixin):
    """基金净值历史表"""
    __tablename__ = "fund_nav"

    fund_code: Mapped[str] = mapped_column(String(10), index=True, comment="基金代码")
    nav_date: Mapped[date] = mapped_column(Date, index=True, comment="净值日期")
    nav: Mapped[float] = mapped_column(Float, default=0.0, comment="单位净值")
    accumulated_nav: Mapped[float] = mapped_column(Float, default=0.0, comment="累计净值")
    daily_return: Mapped[float] = mapped_column(Float, default=0.0, comment="日收益率(%)")
    week_return: Mapped[float] = mapped_column(Float, default=0.0, comment="周收益率(%)")
    month_return: Mapped[float] = mapped_column(Float, default=0.0, comment="月收益率(%)")

    def __repr__(self) -> str:
        return f"<FundNav(code={self.fund_code}, date={self.nav_date})>"
