"""
分析日报快照表 -- 系统进化4方向的结果持久化

每天 validation-B (17:35) 结束后自动写入4类分析结果:
1. rolling_window: 30/60/90天滚动窗口准确率 (全局)
2. per_fund: 每基金30天准确率
3. factor_correlation: 因子与AI准确率的相关系数
4. data_quality: 各字段NULL率/完整性
"""
from datetime import date
from typing import Optional

from sqlalchemy import (
    String, Date, Integer, Numeric, JSON, Enum,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AnalysisDailySnapshot(Base, TimestampMixin):
    """分析日报快照表"""
    __tablename__ = "analysis_daily_snapshot"

    snapshot_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="快照日期",
    )
    analysis_type: Mapped[str] = mapped_column(
        Enum("rolling_window", "per_fund", "factor_correlation", "data_quality"),
        nullable=False, comment="分析类型",
    )
    fund_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="基金代码(per_fund时填, 全局分析为NULL)",
    )
    metric_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="指标名",
    )
    metric_value: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="指标值",
    )
    sample_size: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="样本量",
    )
    p_value: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 6), nullable=True, comment="p值(因子相关性专用)",
    )
    is_significant: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="是否显著(0/1, 因子相关性专用)",
    )
    extra: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="补充信息JSON",
    )

    __table_args__ = (
        UniqueConstraint("snapshot_date", "analysis_type", "fund_code", "metric_name",
                         name="uk_date_type_fund_metric"),
        Index("idx_type_date", "analysis_type", "snapshot_date"),
        Index("idx_fund_date", "fund_code", "snapshot_date"),
        {"comment": "分析日报快照表 -- 系统进化4方向结果持久化"},
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisDailySnapshot(date={self.snapshot_date}, "
            f"type={self.analysis_type}, metric={self.metric_name}, "
            f"value={self.metric_value})>"
        )
