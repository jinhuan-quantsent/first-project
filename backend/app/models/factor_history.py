"""
因子历史数据 ORM 模型
V4.0：从纯 SQL DDL 迁移至 SQLAlchemy ORM
"""
from sqlalchemy import String, DateTime, Float, Integer, UniqueConstraint, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FactorHistory(Base):
    """因子历史数据表"""
    __tablename__ = "factor_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="指数代码")
    factor_name: Mapped[str] = mapped_column(String(20), nullable=False, comment="因子名称")
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, comment="交易日期")
    raw_value: Mapped[float] = mapped_column(Float, nullable=False, comment="原始值")
    created_at: Mapped[str] = mapped_column(
        DateTime, default=func.now(), comment="创建时间"
    )

    __table_args__ = (
        UniqueConstraint("index_code", "factor_name", "trade_date", name="uq_factor_history"),
        Index("idx_factor_history_lookup", "index_code", "factor_name", "trade_date"),
    )

    def __repr__(self) -> str:
        return f"<FactorHistory({self.index_code}, {self.factor_name}, {self.trade_date})>"
