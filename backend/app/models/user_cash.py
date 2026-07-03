"""
用户现金模型
"""
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserCash(Base):
    """用户现金余额表"""
    __tablename__ = "user_cash"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, comment="用户ID")
    cash_amount: Mapped[float] = mapped_column(Numeric(15, 2), default=0, comment="可用现金")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<UserCash(user={self.user_id}, amount={self.cash_amount})>"
