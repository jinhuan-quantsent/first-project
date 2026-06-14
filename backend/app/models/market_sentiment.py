"""
市场情绪主表模型
"""
from datetime import datetime, date

from sqlalchemy import String, DateTime, Date, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MarketSentiment(Base, TimestampMixin):
    """市场情绪主表"""
    __tablename__ = "market_sentiment"

    index_code: Mapped[str] = mapped_column(String(20), index=True, comment="指数代码: SH000001/SH000300/SZ399001/SZ399006")
    index_name: Mapped[str] = mapped_column(String(50), default="", comment="指数名称")
    trade_date: Mapped[date] = mapped_column(Date, index=True, comment="交易日期")
    record_time: Mapped[datetime] = mapped_column(DateTime, default=None, comment="记录时间")

    # 7大因子原始值
    volatility: Mapped[float] = mapped_column(Float, default=0.0, comment="波动率(%)")
    turnover_ratio: Mapped[float] = mapped_column(Float, default=0.0, comment="换手率(%)")
    adv_decline_ratio: Mapped[float] = mapped_column(Float, default=0.0, comment="涨跌家数比")
    new_high_ratio: Mapped[float] = mapped_column(Float, default=0.0, comment="新高占比(%)")
    margin_balance: Mapped[float] = mapped_column(Float, default=0.0, comment="融资余额(亿)")
    short_balance: Mapped[float] = mapped_column(Float, default=0.0, comment="融券余额(亿)")
    bond_spread: Mapped[float] = mapped_column(Float, default=0.0, comment="债券利差(%)")
    rsi_value: Mapped[float] = mapped_column(Float, default=50.0, comment="RSI(14)")

    # 7大因子评分（0-100）
    score_volatility: Mapped[float] = mapped_column(Float, default=50.0)
    score_turnover: Mapped[float] = mapped_column(Float, default=50.0)
    score_adv_decline: Mapped[float] = mapped_column(Float, default=50.0)
    score_new_high: Mapped[float] = mapped_column(Float, default=50.0)
    score_margin: Mapped[float] = mapped_column(Float, default=50.0)
    score_bond_equity: Mapped[float] = mapped_column(Float, default=50.0)
    score_rsi: Mapped[float] = mapped_column(Float, default=50.0)

    # 综合指标
    composite_score: Mapped[float] = mapped_column(Float, default=50.0, comment="加权综合评分(0-100)")
    sentiment_label: Mapped[str] = mapped_column(String(10), default="neutral", comment="情绪标签: extreme_fear/fear/neutral/greed/extreme_greed")
    divergence_index: Mapped[float] = mapped_column(Float, default=0.0, comment="指数分化度(0-100)")
    trend_direction: Mapped[str] = mapped_column(String(10), default="stable", comment="趋势方向: up/down/stable")
    trend_strength: Mapped[float] = mapped_column(Float, default=0.0, comment="趋势强度(0-100)")

    # Top3 因子
    top3_factors: Mapped[str] = mapped_column(String(200), default="", comment="Top3因子(JSON)")
    conclusion: Mapped[str] = mapped_column(Text, default="", comment="一句结论")
    operation_advice: Mapped[str] = mapped_column(Text, default="", comment="操作建议")

    # 极端标记
    is_extreme: Mapped[int] = mapped_column(Integer, default=0, comment="是否极端: 0=否 1=是")
    abnormal_signals: Mapped[str] = mapped_column(String(500), default="", comment="异常信号(JSON)")

    # --- V5.0 新增字段 ---
    signal_level: Mapped[str | None] = mapped_column(String(2), default=None, comment="V5.0信号等级: S+/S/A/B/C/D/E")
    confidence_stars: Mapped[int | None] = mapped_column(Integer, default=None, comment="V5.0置信度星级: 1-4")
    confidence_detail: Mapped[str | None] = mapped_column(Text, default=None, comment="V5.0置信度明细(JSON)")
    factor_std: Mapped[float | None] = mapped_column(Float, default=None, comment="V5.0因子得分标准差")
    triggered_defenses: Mapped[str | None] = mapped_column(Text, default=None, comment="V5.0触发的防线(JSON数组)")

    def __repr__(self) -> str:
        return f"<MarketSentiment(index={self.index_code}, date={self.trade_date}, score={self.composite_score})>"
