"""
建仓评级基金映射模型
板块-基金映射表，支持一级(active)和二级(reserved/unavailable)基金
"""
from sqlalchemy import String, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PositionRatingFundMap(Base, TimestampMixin):
    """建仓评级基金映射表"""
    __tablename__ = "position_rating_fund_map"

    sw_sector_code: Mapped[str] = mapped_column(String(10), index=True, comment="申万板块代码")
    sw_sector_name: Mapped[str] = mapped_column(String(20), comment="申万板块名称")
    fund_code: Mapped[str] = mapped_column(String(10), unique=True, comment="基金代码")
    fund_name: Mapped[str] = mapped_column(String(100), comment="基金名称")
    track_index: Mapped[str] = mapped_column(String(100), default="", comment="跟踪指数名称")
    fit_degree: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0, comment="拟合度(%)")
    fund_level: Mapped[int] = mapped_column(SmallInteger, default=1, index=True, comment="基金层级: 1=一级 2=二级")
    parent_sector_name: Mapped[str] = mapped_column(String(20), default="", comment="父板块名称(二级用)")
    sub_sector_name: Mapped[str] = mapped_column(String(50), default="", comment="子赛道名称(二级用)")
    track_index_code: Mapped[str] = mapped_column(String(20), default="", comment="跟踪指数代码(二级用)")
    status: Mapped[str] = mapped_column(String(20), default="active", comment="状态: active/reserved/unavailable")

    def __repr__(self) -> str:
        return f"<PositionRatingFundMap({self.sw_sector_code}/{self.fund_code}/{self.status})>"
