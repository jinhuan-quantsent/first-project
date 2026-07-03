"""
每日决策快照表 — 固化每天系统给出的最终信号、评级、仓位建议和风控状态

每天每个标的(宽基/板块/基金)一条记录，永久留存，供后续策略验证和复盘分析。
没有未来函数，比纯历史回测更靠谱。
V5.2: 新增 nav（最新净值）字段
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import String, Date, DateTime, Float, Integer, Text, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DailySignalSnapshot(Base, TimestampMixin):
    """每日决策快照表"""
    __tablename__ = "daily_signal_snapshot"

    # ── 主键维度 ──
    snapshot_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="快照交易日",
    )
    target_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="标的代码(801180/000300.SH/021201)",
    )
    target_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="标的名称",
    )
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="标的类型: broad/sector/fund",
    )

    # ── 核心必选字段 ──
    composite_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="当日综合情绪分(0-100)",
    )
    signal_level: Mapped[Optional[str]] = mapped_column(
        String(4), nullable=True, comment="当日信号等级(S+/S/A/B/C/D/E)",
    )
    confidence_stars: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="当日置信度星级(1-4)",
    )
    track_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="轨道类型: trend_follow/contrarian/excluded",
    )
    position_rating: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="建仓评级: strong/cautious/watch/forbidden",
    )
    target_position_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="建议目标仓位比例(0.05=5%)",
    )
    # V5.2: 最新净值
    nav: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="最新基金净值",
    )
    # V5.2: 情绪数据来源
    sentiment_source: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="情绪数据来源: broad/sector",
    )
    action_advice: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="操作建议: increase/hold/decrease/sell",
    )
    overall_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="风控总状态: normal/warning/stop_loss/panic",
    )

    # Gate 触发状态
    gate_1_triggered: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, comment="Gate1是否触发(0=否 1=是)",
    )
    gate_2_triggered: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, comment="Gate2是否触发(0=否 1=是)",
    )
    gate_e_triggered: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, comment="Gate-E是否触发(0=否 1=是)",
    )

    # ── 扩展字段 ──
    factor_std: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="因子分歧度(标准差)",
    )
    regime: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="市场体制: bull/bear/sideways/extreme_volatility",
    )
    triggered_defenses: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="当日触发的假信号防线(JSON数组)",
    )
    gate_1_distance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="距Gate1触发的距离百分比",
    )
    gate_2_distance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="距Gate2触发的距离百分比",
    )
    drawdown_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 4), nullable=True, comment="当日阶段回撤比例",
    )
    confidence_detail: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="置信度明细(JSON)",
    )
    macd_state: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="MACD 6状态",
    )
    advice_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="操作建议原因文字",
    )
    frequency_block_direction: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="频率限制方向: increase/decrease",
    )

    __table_args__ = (
        {"comment": "每日决策快照表 — 固化系统最终输出，供策略验证和复盘"},
    )

    def __repr__(self) -> str:
        return f"<DailySignalSnapshot(date={self.snapshot_date}, code={self.target_code}, signal={self.signal_level}, action={self.action_advice})>"
