"""
基金NAV历史数据缓存模型（方案B依赖）
存储基金净值历史数据，用于趋势卫士计算
"""
from datetime import date

from sqlalchemy import String, Date, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NavHistory(Base, TimestampMixin):
    """基金NAV历史数据缓存表"""
    __tablename__ = "nav_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fund_code: Mapped[str] = mapped_column(String(10), index=True, comment="基金代码")
    nav_date: Mapped[date] = mapped_column(Date, index=True, comment="NAV日期")
    
    # NAV数据
    nav: Mapped[float] = mapped_column(Float, default=0.0, comment="单位净值")
    nav_acc: Mapped[float] = mapped_column(Float, default=0.0, comment="累计净值")
    change_pct: Mapped[float] = mapped_column(Float, default=0.0, comment="日涨跌幅(%)")
    
    def __repr__(self) -> str:
        return f"<NavHistory(code={self.fund_code}, date={self.nav_date})>"
