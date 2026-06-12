"""
板块情绪模型
"""
from datetime import date

from sqlalchemy import String, Date, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SectorSentiment(Base, TimestampMixin):
    """板块情绪表"""
    __tablename__ = "sector_sentiment"

    sector_code: Mapped[str] = mapped_column(String(20), index=True, comment="板块代码")
    sector_name: Mapped[str] = mapped_column(String(50), comment="板块名称")
    trade_date: Mapped[date] = mapped_column(Date, index=True, comment="交易日期")

    # 板块指标
    sector_return: Mapped[float] = mapped_column(Float, default=0.0, comment="板块涨跌幅(%)")
    turnover_ratio: Mapped[float] = mapped_column(Float, default=0.0, comment="板块换手率(%)")
    fund_flow: Mapped[float] = mapped_column(Float, default=0.0, comment="资金净流入(亿)")
    strength_index: Mapped[float] = mapped_column(Float, default=50.0, comment="强度指数(0-100)")

    # 情绪评分
    sentiment_score: Mapped[float] = mapped_column(Float, default=50.0, comment="板块情绪评分(0-100)")
    sentiment_label: Mapped[str] = mapped_column(String(10), default="neutral", comment="情绪标签")
    rank: Mapped[int] = mapped_column(default=0, comment="当日排名")

    # 动量
    momentum_5d: Mapped[float] = mapped_column(Float, default=0.0, comment="5日动量")
    momentum_20d: Mapped[float] = mapped_column(Float, default=0.0, comment="20日动量")

    def __repr__(self) -> str:
        return f"<SectorSentiment(name={self.sector_name}, date={self.trade_date})>"
