"""
策略验证分析日志表 -- 统一快照+预演+T+1回验的持久化分析表

每基金每交易日1行，57列，9组(G1-G9)。
14:50任务A写入G1-G5/G3b/G4b/G7.system_advice_text，
14:52任务C写入G8,
17:35任务B(T+1)回填G6/G7回验评分/G8.deepseek_advice_correct。
积累1-2个月后可分析系统参数/闸门/趋势/建议是否正确。
"""
from datetime import date
from typing import Optional

from sqlalchemy import (
    String, Date, Integer, Text, Numeric, JSON,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class StrategyValidationLog(Base, TimestampMixin):
    """策略验证分析日志表"""
    __tablename__ = "strategy_validation_log"

    # ── G1: 标识 (6列) ──
    trade_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="交易日",
    )
    fund_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="基金代码",
    )
    fund_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="基金名称",
    )
    sector_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True, comment="板块代码",
    )
    sector_name: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="板块名称(冗余,方便AI识别)",
    )
    user_id: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="用户ID",
    )

    # ── G2: 昨日基线 (6列) ──
    yesterday_signal: Mapped[Optional[str]] = mapped_column(
        String(4), nullable=True, comment="昨日信号(S+/S/A/B/C/D/E)",
    )
    yesterday_confidence: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="昨日置信度星级(1-4)",
    )
    yesterday_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="昨日情绪分(0-100)",
    )
    yesterday_position: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="昨日仓位比例(0.05=5%)",
    )
    yesterday_nav: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="昨日净值",
    )
    yesterday_track_type: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="昨日轨道(trend_follow/contrarian/excluded)",
    )

    # ── G3: 盘中预演 (12列) ──
    preview_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="盘中估算情绪分",
    )
    preview_signal: Mapped[Optional[str]] = mapped_column(
        String(4), nullable=True, comment="盘中估算信号(S+/S/A/B/C/D/E)",
    )
    preview_confidence: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="盘中置信度(1-3, 尾盘=3)",
    )
    gszzl: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="盘中估值涨跌幅(%)",
    )
    gszzl_source: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="估值来源(fundgz/unavailable)",
    )
    elasticity: Mapped[Optional[float]] = mapped_column(
        Numeric(4, 2), nullable=True, comment="弹性系数",
    )
    score_delta: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="情绪分变化量(预演-昨日)",
    )
    effective_stars: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="有效星级(考虑时段降级后)",
    )
    intraday_high_gszzl: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="盘中最高估值(%)",
    )
    intraday_low_gszzl: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="盘中最低估值(%)",
    )
    preview_summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="预演摘要文字(_build_preview_summary输出)",
    )
    anomaly_flags: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, comment="异常标记JSON数组(JSON_CONTAINS查询)",
    )

    # ── G3b: 市场上下文 (2列) ──
    market_index_chg_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="大盘涨跌幅(%)",
    )
    sector_chg_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="板块涨跌幅(%)",
    )

    # ── G4: 当日决策 (4列) ──
    actual_action: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="当日操作(increase/hold/decrease)",
    )
    actual_target_position: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True, comment="当日目标仓位比例",
    )
    actual_nav: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="当日实际净值",
    )
    actual_signal: Mapped[Optional[str]] = mapped_column(
        String(4), nullable=True, comment="当日实际信号",
    )

    # ── G4b: 持仓盈亏 (4列) ──
    cost_basis: Mapped[Optional[float]] = mapped_column(
        Numeric(8, 4), nullable=True, comment="成本净值",
    )
    unrealized_pnl_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="浮盈亏比例(%)",
    )
    holding_shares: Mapped[Optional[float]] = mapped_column(
        Numeric(15, 4), nullable=True, comment="持有份额",
    )
    holding_market_value: Mapped[Optional[float]] = mapped_column(
        Numeric(15, 2), nullable=True, comment="持仓市值(元)",
    )

    # ── G5: Gate风控 (8列) ──
    gate_1_triggered: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, comment="Gate1是否触发(0=否 1=是)",
    )
    gate_2_triggered: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, comment="Gate2是否触发(0=否 1=是)",
    )
    gate_e_triggered: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=0, comment="Gate-E是否触发(0=否 1=是)",
    )
    gate_1_distance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="距Gate1触发百分比(正=安全 负=已突破)",
    )
    gate_2_distance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="距Gate2触发百分比(正=安全 负=已突破)",
    )
    gate_e_distance_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="距Gate-E触发百分比(正=安全 负=已突破)",
    )
    frequency_block_direction: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="频率限制方向(increase/decrease)",
    )
    overall_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="总状态(normal/warning/stop_loss)",
    )

    # ── G6: 次日实际 (4列) -- T+1回验填充 ──
    actual_trend: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, comment="实际趋势(up/down/flat)",
    )
    actual_nav_change_pct: Mapped[Optional[float]] = mapped_column(
        Numeric(6, 2), nullable=True, comment="实际净值变化(%)",
    )
    actual_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="实际情绪分",
    )
    actual_signal_level: Mapped[Optional[str]] = mapped_column(
        String(4), nullable=True, comment="实际信号等级",
    )

    # ── G7: 回验评分 + 系统建议 (6列) ──
    validation_score: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="综合验证评分(0-100)",
    )
    signal_accuracy: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="信号准确度(0-1)",
    )
    advice_accuracy: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="建议准确度(0-1, 0.5=部分正确)",
    )
    gate_accuracy: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Gate准确度(0-1)",
    )
    system_advice_text: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="系统建议文本(7段300-500字, 14:50生成)",
    )
    system_advice_action: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="系统建议方向(increase/hold/decrease)",
    )
    advice_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="引擎原始建议原因",
    )

    # ── G8: AI建议 (3列) ──
    deepseek_advice: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="DeepSeek AI完整建议(14:52生成)",
    )
    deepseek_advice_action: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="AI建议方向(increase/hold/decrease)",
    )
    deepseek_advice_correct: Mapped[Optional[float]] = mapped_column(
        Integer, nullable=True, index=True, comment="AI建议准确度(0/1, T+1回填)",
    )

    # ── G9: 扩展 (4列) ──
    consecutive_signal_days: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="连续信号天数(仅交易日连续)",
    )
    ext_num1: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="扩展数字1(预留)",
    )
    ext_num2: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="扩展数字2(预留)",
    )
    ext_text1: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="扩展文本1(预留)",
    )

    __table_args__ = (
        UniqueConstraint("fund_code", "trade_date", "user_id", name="uq_validation_fund_date_user"),
        Index("idx_validation_trade_date", "trade_date"),
        Index("idx_validation_fund_code", "fund_code"),
        Index("idx_validation_sector_code", "sector_code"),
        Index("idx_validation_deepseek_correct", "deepseek_advice_correct"),
        {"comment": "策略验证分析日志表 -- 统一快照+预演+T+1回验, 供策略复盘分析"},
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyValidationLog(date={self.trade_date}, "
            f"code={self.fund_code}, signal={self.preview_signal}, "
            f"status={self.overall_status})>"
        )
