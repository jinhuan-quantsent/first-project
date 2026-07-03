"""
回测方案模型
V5.0 新增：保存用户的回测参数方案
"""
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BacktestStrategy(Base):
    """回测方案表"""
    __tablename__ = "backtest_strategy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True, comment="用户ID")
    name: Mapped[str] = mapped_column(String(100), comment="方案名称")
    params_json: Mapped[str] = mapped_column(Text, comment="回测参数(JSON字符串)")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否激活")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<BacktestStrategy(id={self.id}, name={self.name})>"
