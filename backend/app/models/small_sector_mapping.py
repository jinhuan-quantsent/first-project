"""
小板块映射模型（60 个细分板块）
"""
from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SmallSectorMapping(Base, TimestampMixin):
    """小板块映射表（60 个细分板块）"""
    __tablename__ = "small_sector_mapping"

    sector_code: Mapped[str] = mapped_column(String(20), unique=True, index=True, comment="小板块代码")
    sector_name: Mapped[str] = mapped_column(String(50), comment="小板块名称")
    parent_code: Mapped[str] = mapped_column(String(20), index=True, comment="父板块代码")
    parent_name: Mapped[str] = mapped_column(String(50), default="", comment="父板块名称")
    sector_group: Mapped[str] = mapped_column(String(20), default="", comment="板块大类")
    weight: Mapped[float] = mapped_column(Float, default=0.0, comment="在父板块中权重(%)")
    description: Mapped[str] = mapped_column(String(200), default="", comment="描述")

    def __repr__(self) -> str:
        return f"<SmallSectorMapping(name={self.sector_name}, parent={self.parent_name})>"
