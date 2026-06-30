"""
基金基本信息模型
"""
from datetime import date

from sqlalchemy import String, Date, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FundBasic(Base, TimestampMixin):
    """基金基本信息表"""
    __tablename__ = "fund_basic"

    fund_code: Mapped[str] = mapped_column(String(10), unique=True, index=True, comment="基金代码")
    fund_name: Mapped[str] = mapped_column(String(100), comment="基金全称")
    fund_short_name: Mapped[str] = mapped_column(String(50), default="", comment="基金简称")
    fund_type: Mapped[str] = mapped_column(String(20), default="", comment="基金类型: 股票型/混合型/指数型/债券型/货币型")
    manager: Mapped[str] = mapped_column(String(50), default="", comment="基金经理")
    company: Mapped[str] = mapped_column(String(100), default="", comment="基金公司")
    inception_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="成立日期")
    nav: Mapped[float] = mapped_column(Float, default=0.0, comment="最新净值")
    accumulated_nav: Mapped[float] = mapped_column(Float, default=0.0, comment="累计净值")
    fund_size: Mapped[float] = mapped_column(Float, default=0.0, comment="基金规模（亿元）")
    benchmark: Mapped[str] = mapped_column(String(100), default="", comment="业绩基准")
    tracking_index: Mapped[str] = mapped_column(String(20), default="", comment="跟踪指数代码")
    risk_level: Mapped[str] = mapped_column(String(10), default="R3", comment="风险等级: R1-R5")
    description: Mapped[str] = mapped_column(Text, default="", comment="基金简介")

    def __repr__(self) -> str:
        return f"<FundBasic(code={self.fund_code}, name={self.fund_name})>"
