"""
板块情绪模型 - 与 DB 表结构对齐（P0-2 修复）

DB 实际表结构（sector_sentiment）：
  id, calc_date, sector_name, sector_level, parent_sector,
  composite_score, volatility_score, turnover_score,
  adv_decline_score, new_high_score, margin_score,
  bond_equity_score, rsi_score, sentiment_label,
  short_trend, mid_trend, long_trend, data_source, created_at
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Date, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SectorSentiment(Base):
    """板块情绪表（大板块+小板块）"""
    __tablename__ = "sector_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 主键维度
    calc_date: Mapped[date] = mapped_column(Date, nullable=False, index=True, comment="计算日期")
    sector_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="板块标准名称")

    # 板块分类
    sector_level: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default="large", comment="板块级别: large-大板块 small-小板块"
    )
    parent_sector: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="所属大板块(小板块时填写)"
    )

    # 因子评分（各 0-100）
    composite_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="综合情绪分(0-100)"
    )
    volatility_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="波动率因子分"
    )
    turnover_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="换手率因子分"
    )
    adv_decline_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="涨跌家数因子分"
    )
    new_high_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="新高因子分"
    )
    margin_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="融资融券因子分"
    )
    bond_equity_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="股债性价比因子分"
    )
    rsi_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="RSI因子分"
    )

    # 情绪标签与趋势
    sentiment_label: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="情绪标签"
    )
    short_trend: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="短期趋势(up/down/flat)"
    )
    mid_trend: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="中期趋势(up/down/flat)"
    )
    long_trend: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="长期趋势(up/down/flat)"
    )

    # 数据来源
    data_source: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, default="tushare", comment="数据来源"
    )

    # 时间戳（DB 默认 CURRENT_TIMESTAMP，ORM 不主动写入）
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, server_default=func.now(), comment="创建时间"
    )

    def __repr__(self) -> str:
        return f"<SectorSentiment(name={self.sector_name}, date={self.calc_date}, score={self.composite_score})>"
