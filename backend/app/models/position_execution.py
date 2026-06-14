"""
仓位执行记录模型
V5.0 新增：记录用户每次仓位调整的执行情况
"""
from datetime import date, datetime

from sqlalchemy import String, Date, DateTime, Float, Integer, Text, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PositionExecution(Base):
    """仓位执行记录表"""
    __tablename__ = "position_execution"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True, comment="用户ID")
    fund_code: Mapped[str] = mapped_column(String(20), index=True, comment="基金代码")
    execute_date: Mapped[date] = mapped_column(Date, comment="执行日期(Asia/Shanghai)")
    from_position_pct: Mapped[float] = mapped_column(Float, comment="调整前仓位%")
    to_position_pct: Mapped[float] = mapped_column(Float, comment="调整后仓位%")
    amount: Mapped[float | None] = mapped_column(Float, default=None, comment="调整金额(可选)")
    signal_level: Mapped[str] = mapped_column(String(2), comment="执行时信号等级")
    confidence_stars: Mapped[int] = mapped_column(Integer, comment="执行时置信度星级")
    reason: Mapped[str] = mapped_column(Text, default="", comment="建议原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "fund_code", "execute_date", name="uq_position_execution_daily"),
    )

    def __repr__(self) -> str:
        return f"<PositionExecution(user={self.user_id}, fund={self.fund_code}, date={self.execute_date})>"
