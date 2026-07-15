"""
基金映射模型
fund_code(PK) → index_code(申万板块代码) + category(broad/sector/theme) + fund_name

注意: fund_mapping表没有id列, fund_code是主键, 不能用TimestampMixin(会加id)
"""
from datetime import datetime

from sqlalchemy import String, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FundMapping(Base):
    """基金-板块映射表（fund_code为主键，无id列）"""
    __tablename__ = "fund_mapping"

    fund_code: Mapped[str] = mapped_column(String(20), primary_key=True, comment="基金代码(PK)")
    index_code: Mapped[str] = mapped_column(String(20), comment="申万板块代码/跟踪指数代码")
    category: Mapped[str] = mapped_column(
        Enum("broad", "sector", "theme", name="fund_category_enum"),
        default="sector",
        comment="基金分类: broad(宽基)/sector(行业)/theme(主题)"
    )
    fund_name: Mapped[str] = mapped_column(String(100), default="", comment="基金名称")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<FundMapping({self.fund_code}/{self.category}/{self.index_code})>"
