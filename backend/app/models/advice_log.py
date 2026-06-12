"""
操作建议日志模型
"""
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, Text, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdviceLog(Base):
    """操作建议日志表"""
    __tablename__ = "advice_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), index=True, comment="用户ID")
    index_code: Mapped[str] = mapped_column(String(20), default="", comment="指数代码")
    trade_date: Mapped[datetime] = mapped_column(DateTime, default=func.now(), comment="建议日期")

    # 建议内容
    sentiment_score: Mapped[float] = mapped_column(Float, default=50.0, comment="情绪评分")
    sentiment_label: Mapped[str] = mapped_column(String(10), default="neutral", comment="情绪标签")
    advice_type: Mapped[str] = mapped_column(String(20), default="", comment="建议类型: buy/hold/reduce/watch")
    advice_content: Mapped[str] = mapped_column(Text, default="", comment="建议内容")
    suggested_position: Mapped[float] = mapped_column(Float, default=50.0, comment="建议仓位(%)")

    # 执行状态
    is_executed: Mapped[int] = mapped_column(Integer, default=0, comment="是否执行: 0=否 1=是")
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="执行时间")
    execution_note: Mapped[str] = mapped_column(String(500), default="", comment="执行备注")

    # 回溯验证
    is_verified: Mapped[int] = mapped_column(Integer, default=0, comment="是否验证: 0=否 1=是")
    actual_result: Mapped[float] = mapped_column(Float, default=0.0, comment="实际结果(%)")
    accuracy_score: Mapped[float] = mapped_column(Float, default=0.0, comment="准确度评分")

    def __repr__(self) -> str:
        return f"<AdviceLog(user={self.user_id}, date={self.trade_date})>"
