"""
用户自选基金模型
"""
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserWatchlist(Base):
    """用户自选基金表"""
    __tablename__ = "user_watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True, comment="用户ID")
    fund_code: Mapped[str] = mapped_column(String(10), index=True, comment="基金代码")
    fund_name: Mapped[str] = mapped_column(String(100), default="", comment="基金名称")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), comment="添加时间")
    notes: Mapped[str] = mapped_column(String(500), default="", comment="备注")
    alert_threshold: Mapped[float] = mapped_column(Float, default=0.0, comment="提醒阈值(%)")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序序号")

    def __repr__(self) -> str:
        return f"<UserWatchlist(user={self.user_id}, fund={self.fund_code})>"
