"""
板块热度图缓存模型（方案B依赖）
存储板块指数历史数据，用于板块过滤器计算
"""
from datetime import date

from sqlalchemy import String, Date, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SectorHeatmapCache(Base, TimestampMixin):
    """板块热度图缓存表（存储板块指数历史数据）"""
    __tablename__ = "sector_heatmap_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sector_code: Mapped[str] = mapped_column(String(20), index=True, comment="板块代码")
    sector_name: Mapped[str] = mapped_column(String(50), comment="板块名称")
    cache_date: Mapped[date] = mapped_column(Date, index=True, comment="缓存日期")
    
    # 历史数据字段
    close_price: Mapped[float] = mapped_column(Float, default=0.0, comment="收盘价")
    change_pct: Mapped[float] = mapped_column(Float, default=0.0, comment="涨跌幅(%)")
    volume: Mapped[float] = mapped_column(Float, default=0.0, comment="成交量")
    turnover: Mapped[float] = mapped_column(Float, default=0.0, comment="换手率(%)")
    
    # 相对强弱（相对沪深300）
    relative_strength: Mapped[float] = mapped_column(Float, default=0.0, comment="相对强弱（超额收益）")
    
    def __repr__(self) -> str:
        return f"<SectorHeatmapCache(code={self.sector_code}, date={self.cache_date})>"
