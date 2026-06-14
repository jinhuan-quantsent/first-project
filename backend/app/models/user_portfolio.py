"""
用户持仓组合模型
"""
from datetime import date, datetime

from sqlalchemy import String, Date, DateTime, Integer, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserPortfolio(Base):
    """用户持仓组合表"""
    __tablename__ = "user_portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True, comment="用户ID")
    fund_code: Mapped[str] = mapped_column(String(10), index=True, comment="基金代码")
    fund_name: Mapped[str] = mapped_column(String(100), default="", comment="基金名称")
    fund_type: Mapped[str] = mapped_column(String(20), default="", comment="基金类型")

    # 持仓信息
    holding_shares: Mapped[float] = mapped_column(Float, default=0.0, comment="持有份额")
    cost_nav: Mapped[float] = mapped_column(Float, default=0.0, comment="成本净值")
    current_nav: Mapped[float] = mapped_column(Float, default=0.0, comment="当前净值")
    market_value: Mapped[float] = mapped_column(Float, default=0.0, comment="持仓市值")

    # 收益
    total_return: Mapped[float] = mapped_column(Float, default=0.0, comment="累计收益")
    return_rate: Mapped[float] = mapped_column(Float, default=0.0, comment="收益率(%)")
    daily_return: Mapped[float] = mapped_column(Float, default=0.0, comment="日收益")

    # 时间
    buy_date: Mapped[date] = mapped_column(Date, nullable=True, comment="买入日期")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # 标签
    portfolio_tag: Mapped[str] = mapped_column(String(20), default="", comment="组合标签: core/satellite/trading")
    weight_pct: Mapped[float] = mapped_column(Float, default=0.0, comment="组合内权重(%)")

    # --- V5.0 新增字段 ---
    last_advice_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="V5.0最后建议日期")
    current_position_level: Mapped[str] = mapped_column(String(20), default="mid", comment="V5.0当前仓位等级: empty/light/mid/heavy/full")

    def __repr__(self) -> str:
        return f"<UserPortfolio(user={self.user_id}, fund={self.fund_code})>"
