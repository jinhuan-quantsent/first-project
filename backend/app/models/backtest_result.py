"""
回测结果模型
V5.0 新增：存储回测引擎的运行结果
"""
from datetime import date, datetime

from sqlalchemy import String, Date, DateTime, Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BacktestResult(Base):
    """回测结果表"""
    __tablename__ = "backtest_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, index=True, comment="关联方案ID")
    index_code: Mapped[str] = mapped_column(String(20), comment="指数代码")
    start_date: Mapped[date] = mapped_column(Date, comment="开始日期")
    end_date: Mapped[date] = mapped_column(Date, comment="结束日期")
    total_return: Mapped[float] = mapped_column(Float, comment="总收益率(%)")
    annual_return: Mapped[float] = mapped_column(Float, comment="年化收益率(%)")
    max_drawdown: Mapped[float] = mapped_column(Float, comment="最大回撤(%)")
    win_rate: Mapped[float] = mapped_column(Float, comment="胜率(%)")
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, default=None, comment="夏普比率")
    excess_return: Mapped[float | None] = mapped_column(Float, default=None, comment="超额收益(%)")
    total_trades: Mapped[int] = mapped_column(Integer, default=0, comment="总交易次数")
    equity_curve: Mapped[str] = mapped_column(Text, comment="净值曲线(JSON)")
    trades_json: Mapped[str] = mapped_column(Text, comment="交易记录(JSON)")
    run_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    def __repr__(self) -> str:
        return f"<BacktestResult(strategy={self.strategy_id}, return={self.total_return})>"
