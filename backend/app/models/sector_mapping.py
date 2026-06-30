"""
板块映射模型（大板块 28 个）
"""
from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SectorMapping(Base, TimestampMixin):
    """板块映射表（大板块 28 个）"""
    __tablename__ = "sector_mapping"

    sector_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, comment="板块代码")
    sector_name: Mapped[str] = mapped_column(String(50), comment="板块名称")
    sector_group: Mapped[str] = mapped_column(String(20), default="", comment="板块大类: 科技/消费/金融/周期/制造/医药/地产/能源")
    index_code: Mapped[str] = mapped_column(String(20), default="", comment="关联指数")
    weight: Mapped[float] = mapped_column(Float, default=0.0, comment="在指数中的权重(%)")
    description: Mapped[str] = mapped_column(String(200), default="", comment="板块描述")

    def __repr__(self) -> str:
        return f"<SectorMapping(name={self.sector_name}, group={self.sector_group})>"
