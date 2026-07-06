"""
每日决策快照查询 API

V5.2 更新：
- 新增 nav（净值）列
- CSV 和 API 中文化5个字段：类型、赛道类型、建仓评级、操作建议、风控状态
- history 和 stats API 也输出中文名
"""
import urllib.parse
import io
import csv
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.daily_signal_snapshot import DailySignalSnapshot
from app.models.strategy_validation_log import StrategyValidationLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["v5-signal-snapshot"])


# ── 中英文翻译映射 ──
TYPE_CN = {"broad": "宽基指数", "sector": "板块", "fund": "基金"}
TRACK_CN = {"contrarian": "逆向轨道", "trend_follow": "趋势轨道", "excluded": "排除轨道"}
RATING_CN = {"watch": "观望", "buy": "可建仓", "strong_buy": "强力建仓", "avoid": "回避"}
ACTION_CN = {"increase": "加仓", "hold": "持有", "decrease": "减仓", "sell": "清仓"}
STATUS_CN = {"normal": "正常", "warning": "预警", "stop_loss": "止损", "forbidden": "禁止建仓"}


def _cn(field: str, value) -> str:
    """将英文枚举值翻译为中文"""
    if value is None:
        return ""
    v = str(value)
    maps = {
        "target_type": TYPE_CN,
        "track_type": TRACK_CN,
        "position_rating": RATING_CN,
        "action_advice": ACTION_CN,
        "overall_status": STATUS_CN,
    }
    m = maps.get(field)
    if m and v in m:
        return m[v]
    return v


# ── CSV 列定义 ──
CSV_COLUMNS = [
    ("快照日期", "snapshot_date"),
    ("代码", "target_code"),
    ("名称", "target_name"),
    ("类型", "target_type"),
    ("综合评分", "composite_score"),
    ("信号等级", "signal_level"),
    ("置信度星数", "confidence_stars"),
    ("赛道类型", "track_type"),
    ("建仓评级", "position_rating"),
    ("目标仓位%", "target_position_pct"),
    ("净值", "nav"),
    ("操作建议", "action_advice"),
    ("风控状态", "overall_status"),
    ("Gate1触发", "gate_1_triggered"),
    ("Gate2触发", "gate_2_triggered"),
    ("GateE触发", "gate_e_triggered"),
    ("Gate1距离%", "gate_1_distance_pct"),
    ("Gate2距离%", "gate_2_distance_pct"),
    ("因子标准差", "factor_std"),
    ("趋势方向", "regime"),
    ("MACD状态", "macd_state"),
    ("回撤%", "drawdown_pct"),
    ("建议理由", "advice_reason"),
    ("冷却方向", "frequency_block_direction"),
]


def _build_snapshot_conditions(sd: date, ed: date,
                               target_type: Optional[str] = None,
                               signal_level: Optional[str] = None,
                               action_advice: Optional[str] = None):
    """公共条件构建器"""
    conditions = [
        DailySignalSnapshot.snapshot_date >= sd,
        DailySignalSnapshot.snapshot_date <= ed,
    ]
    if target_type:
        conditions.append(DailySignalSnapshot.target_type == target_type)
    if signal_level:
        conditions.append(DailySignalSnapshot.signal_level == signal_level)
    if action_advice:
        # 支持中文和英文筛选
        cn_to_en = {v: k for k, v in ACTION_CN.items()}
        en_val = cn_to_en.get(action_advice, action_advice)
        conditions.append(DailySignalSnapshot.action_advice == en_val)
    return conditions


def _format_csv_value(en: str, val) -> str:
    """统一格式化 CSV 单元格值，中文化5个枚举字段"""
    if val is None:
        return ""

    # 中文化枚举值
    if en in ("target_type", "track_type", "position_rating",
              "action_advice", "overall_status"):
        return _cn(en, val)

    if en == "snapshot_date":
        return val.isoformat() if val else ""
    if en == "nav":
        return f"{float(val):.4f}" if val is not None else ""
    if en in ("composite_score", "target_position_pct", "factor_std",
              "drawdown_pct", "gate_1_distance_pct", "gate_2_distance_pct"):
        return f"{float(val):.2f}" if val is not None else ""
    if en in ("gate_1_triggered", "gate_2_triggered", "gate_e_triggered", "confidence_stars"):
        return str(int(val)) if val is not None else ""
    return str(val) if val is not None else ""


@router.get("/snapshot-download")
async def download_snapshot_csv(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    target_type: Optional[str] = Query(None, description="标的类型: broad/sector/fund 或 宽基指数/板块/基金"),
    signal_level: Optional[str] = Query(None, description="信号等级: S+/S/A/B/C/D/E"),
    action_advice: Optional[str] = Query(None, description="操作建议: 加仓/持有/减仓/清仓 或 increase/hold/decrease/sell"),
    db: AsyncSession = Depends(get_session),
):
    """导出每日决策快照为 CSV 文件（中文化版）"""
    if start_date:
        sd = date.fromisoformat(start_date)
    else:
        sd = date.today() - timedelta(days=30)
    if end_date:
        ed = date.fromisoformat(end_date)
    else:
        ed = date.today()

    # 支持中文类型筛选
    cn_to_type = {v: k for k, v in TYPE_CN.items()}
    effective_type = cn_to_type.get(target_type, target_type)

    conditions = _build_snapshot_conditions(sd, ed, effective_type, signal_level, action_advice)

    stmt = select(DailySignalSnapshot).where(*conditions).order_by(
        DailySignalSnapshot.snapshot_date.desc(),
        DailySignalSnapshot.target_type,
        DailySignalSnapshot.target_code,
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    # 双行表头：中文列名 + 英文字段名
    writer.writerow([col[0] for col in CSV_COLUMNS])
    writer.writerow([col[1] for col in CSV_COLUMNS])

    # 数据行（中文化）
    for r in rows:
        row_data = [_format_csv_value(en, getattr(r, en, None)) for cn, en in CSV_COLUMNS]
        writer.writerow(row_data)

    output.seek(0)

    # UTF-8 + BOM 编码，让 Excel/WPS 正确识别中文
    csv_bytes = b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
    filename_ascii = f"snapshot_{sd.isoformat()}_{ed.isoformat()}.csv"
    filename_utf8 = f"决策快照_{sd.isoformat()}_{ed.isoformat()}.csv"
    filename_encoded = urllib.parse.quote(filename_utf8, safe="")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=\"" + filename_ascii + "\"; filename*=UTF-8''" + filename_encoded,
        },
    )



@router.get("/snapshot-trigger")
async def trigger_snapshot(
    db: AsyncSession = Depends(get_session),
):
    """手动触发每日决策快照任务（调试/补数据用）"""
    from app.core.scheduler_snapshot import _run_signal_snapshot
    try:
        await _run_signal_snapshot()
        return {"code": 0, "data": {"message": "快照任务已执行"}, "message": "ok"}
    except Exception as e:
        logger.error("[Snapshot trigger] failed: %s", e, exc_info=True)
        return {"code": 500, "data": None, "message": f"快照任务失败: {str(e)}"}



@router.get("/snapshot-history")
async def get_snapshot_history(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    target_type: Optional[str] = Query(None, description="标的类型"),
    signal_level: Optional[str] = Query(None, description="信号等级"),
    action_advice: Optional[str] = Query(None, description="操作建议"),
    limit: int = Query(100, description="返回条数上限"),
    db: AsyncSession = Depends(get_session),
):
    """查询每日决策快照历史记录（中文化版）"""
    if start_date:
        sd = date.fromisoformat(start_date)
    else:
        sd = date.today() - timedelta(days=30)
    if end_date:
        ed = date.fromisoformat(end_date)
    else:
        ed = date.today()

    cn_to_type = {v: k for k, v in TYPE_CN.items()}
    effective_type = cn_to_type.get(target_type, target_type)

    conditions = _build_snapshot_conditions(sd, ed, effective_type, signal_level, action_advice)

    stmt = select(DailySignalSnapshot).where(*conditions).order_by(
        DailySignalSnapshot.snapshot_date.desc(),
        DailySignalSnapshot.target_type,
        DailySignalSnapshot.target_code,
    ).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    # 统计概要
    summary_stmt = select(
        DailySignalSnapshot.target_type,
        DailySignalSnapshot.signal_level,
        func.count(DailySignalSnapshot.id),
    ).where(*conditions).group_by(
        DailySignalSnapshot.target_type,
        DailySignalSnapshot.signal_level,
    )
    summary_result = await db.execute(summary_stmt)
    summary_rows = summary_result.all()

    summary = {}
    for tgt_type, sig_lvl, cnt in summary_rows:
        key = f"{_cn('target_type', tgt_type)}:{sig_lvl}"
        summary[key] = cnt

    return {
        "code": 0,
        "data": {
            "total": len(rows),
            "date_range": {"start": sd.isoformat(), "end": ed.isoformat()},
            "summary": summary,
            "records": [
                {
                    "id": r.id,
                    "snapshot_date": r.snapshot_date.isoformat(),
                    "target_code": r.target_code,
                    "target_name": r.target_name,
                    "target_type": _cn("target_type", r.target_type),
                    "composite_score": float(r.composite_score) if r.composite_score else None,
                    "signal_level": r.signal_level,
                    "confidence_stars": r.confidence_stars,
                    "track_type": _cn("track_type", r.track_type),
                    "position_rating": _cn("position_rating", r.position_rating),
                    "target_position_pct": float(r.target_position_pct) if r.target_position_pct else None,
                    "nav": float(r.nav) if r.nav else None,
                    "action_advice": _cn("action_advice", r.action_advice),
                    "overall_status": _cn("overall_status", r.overall_status),
                    "gate_1_triggered": r.gate_1_triggered,
                    "gate_2_triggered": r.gate_2_triggered,
                    "gate_e_triggered": r.gate_e_triggered,
                    "factor_std": float(r.factor_std) if r.factor_std else None,
                    "regime": r.regime,
                    "macd_state": r.macd_state,
                    "drawdown_pct": float(r.drawdown_pct) if r.drawdown_pct else None,
                    "advice_reason": r.advice_reason,
                    "frequency_block_direction": r.frequency_block_direction,
                    "gate_1_distance_pct": float(r.gate_1_distance_pct) if r.gate_1_distance_pct else None,
                    "gate_2_distance_pct": float(r.gate_2_distance_pct) if r.gate_2_distance_pct else None,
                }
                for r in rows
            ],
        },
        "message": "ok",
    }


@router.get("/snapshot-stats")
async def get_snapshot_stats(
    target_type: Optional[str] = Query(None, description="标的类型"),
    days: int = Query(30, description="统计天数"),
    db: AsyncSession = Depends(get_session),
):
    """快照统计（中文化版）"""
    sd = date.today() - timedelta(days=days)

    cn_to_type = {v: k for k, v in TYPE_CN.items()}
    effective_type = cn_to_type.get(target_type, target_type)

    base_cond = [DailySignalSnapshot.snapshot_date >= sd]
    if effective_type:
        base_cond.append(DailySignalSnapshot.target_type == effective_type)

    # 信号等级分布
    signal_dist_stmt = select(
        DailySignalSnapshot.signal_level,
        func.count(DailySignalSnapshot.id),
        func.avg(DailySignalSnapshot.composite_score),
    ).where(*base_cond).group_by(DailySignalSnapshot.signal_level)
    signal_dist_result = await db.execute(signal_dist_stmt)

    signal_distribution = {}
    for sig, cnt, avg_score in signal_dist_result.all():
        signal_distribution[sig or "unknown"] = {
            "count": cnt,
            "avg_composite_score": round(float(avg_score), 2) if avg_score else None,
        }

    # 操作建议分布（中文化）
    action_dist_stmt = select(
        DailySignalSnapshot.action_advice,
        func.count(DailySignalSnapshot.id),
    ).where(*base_cond).group_by(DailySignalSnapshot.action_advice)
    action_dist_result = await db.execute(action_dist_stmt)

    action_distribution = {}
    for action, cnt in action_dist_result.all():
        action_distribution[_cn("action_advice", action) or "未知"] = cnt

    # Gate触发统计
    gate_stats_stmt = select(
        func.sum(DailySignalSnapshot.gate_1_triggered),
        func.sum(DailySignalSnapshot.gate_2_triggered),
        func.sum(DailySignalSnapshot.gate_e_triggered),
        func.count(DailySignalSnapshot.id),
    ).where(
        DailySignalSnapshot.snapshot_date >= sd,
        DailySignalSnapshot.target_type == "fund",
    )
    gate_result = await db.execute(gate_stats_stmt)
    g1_sum, g2_sum, ge_sum, total_funds = gate_result.one()

    # 风控状态分布（中文化）
    status_dist_stmt = select(
        DailySignalSnapshot.overall_status,
        func.count(DailySignalSnapshot.id),
    ).where(
        DailySignalSnapshot.snapshot_date >= sd,
        DailySignalSnapshot.target_type == "fund",
    ).group_by(DailySignalSnapshot.overall_status)
    status_result = await db.execute(status_dist_stmt)
    status_distribution = {}
    for status, cnt in status_result.all():
        status_distribution[_cn("overall_status", status) or "未知"] = cnt

    return {
        "code": 0,
        "data": {
            "days": days,
            "signal_distribution": signal_distribution,
            "action_distribution": action_distribution,
            "gate_stats": {
                "gate_1_triggered": int(g1_sum or 0),
                "gate_2_triggered": int(g2_sum or 0),
                "gate_e_triggered": int(ge_sum or 0),
                "total_fund_snapshots": int(total_funds or 0),
            },
            "status_distribution": status_distribution,
        },
        "message": "ok",
    }

@router.get("/sector-trigger")
async def trigger_sector_snapshot():
    """手动触发板块快照"""
    from app.core.scheduler import _run_sector_snapshot
    try:
        await _run_sector_snapshot()
        return {"code": 0, "data": {"message": "板块快照已执行"}, "message": "ok"}
    except Exception as e:
        logger.error("[Sector trigger] failed: %s", e, exc_info=True)
        return {"code": 1, "data": {"error": str(e)}, "message": "failed"}


# ============================================================
# 策略验证分析表 API
# ============================================================

# 补充翻译映射
SOURCE_CN = {"fundgz": "实时估值", "unavailable": "不可用"}
TREND_CN = {"up": "上涨", "down": "下跌", "flat": "横盘"}

VALIDATION_CSV_COLUMNS = [
    # G1 标识
    ("快照日期", "trade_date"),
    ("基金代码", "fund_code"),
    ("基金名称", "fund_name"),
    ("板块代码", "sector_code"),
    ("板块名称", "sector_name"),
    ("用户ID", "user_id"),
    # G2 昨日基线
    ("昨日信号", "yesterday_signal"),
    ("昨日置信度", "yesterday_confidence"),
    ("昨日情绪分", "yesterday_score"),
    ("昨日仓位", "yesterday_position"),
    ("昨日净值", "yesterday_nav"),
    ("昨日轨道", "yesterday_track_type"),
    # G3 盘中预演
    ("预演情绪分", "preview_score"),
    ("预演信号", "preview_signal"),
    ("预演置信度", "preview_confidence"),
    ("盘中估值", "gszzl"),
    ("估值来源", "gszzl_source"),
    ("弹性系数", "elasticity"),
    ("情绪分变化", "score_delta"),
    ("有效星级", "effective_stars"),
    ("盘中最高", "intraday_high_gszzl"),
    ("盘中最低", "intraday_low_gszzl"),
    ("预演摘要", "preview_summary"),
    ("异常标记", "anomaly_flags"),
    # G3b 市场上下文
    ("大盘涨跌幅", "market_index_chg_pct"),
    ("板块涨跌幅", "sector_chg_pct"),
    # G4 当日决策
    ("当日操作", "actual_action"),
    ("当日目标仓位", "actual_target_position"),
    ("当日净值", "actual_nav"),
    ("当日信号", "actual_signal"),
    # G4b 持仓盈亏
    ("成本净值", "cost_basis"),
    ("浮盈亏比例", "unrealized_pnl_pct"),
    ("持有份额", "holding_shares"),
    ("持仓市值", "holding_market_value"),
    # G5 Gate风控
    ("Gate1触发", "gate_1_triggered"),
    ("Gate2触发", "gate_2_triggered"),
    ("GateE触发", "gate_e_triggered"),
    ("Gate1距离", "gate_1_distance_pct"),
    ("Gate2距离", "gate_2_distance_pct"),
    ("GateE距离", "gate_e_distance_pct"),
    ("频率限制", "frequency_block_direction"),
    ("总状态", "overall_status"),
    # G6 次日实际
    ("次日趋势", "actual_trend"),
    ("次日净值变化", "actual_nav_change_pct"),
    ("次日情绪分", "actual_score"),
    ("次日信号", "actual_signal_level"),
    # G7 回验评分
    ("验证评分", "validation_score"),
    ("信号准确度", "signal_accuracy"),
    ("建议准确度", "advice_accuracy"),
    ("Gate准确度", "gate_accuracy"),
    ("系统建议", "system_advice_text"),
    ("建议原因", "advice_reason"),
    # G8 AI建议
    ("AI建议", "deepseek_advice"),
    ("AI建议方向", "deepseek_advice_action"),
    ("AI建议准确度", "deepseek_advice_correct"),
    # G9 扩展
    ("连续信号天数", "consecutive_signal_days"),
    ("扩展数字1", "ext_num1"),
    ("扩展数字2", "ext_num2"),
    ("扩展文本1", "ext_text1"),
]


def _format_validation_value(en: str, val) -> str:
    """格式化策略验证表CSV单元格值"""
    if val is None:
        return ""

    # 中文化枚举值
    if en in ("gszzl_source",):
        return SOURCE_CN.get(str(val), str(val))
    if en in ("actual_trend",):
        return TREND_CN.get(str(val), str(val))
    if en in ("overall_status",):
        return STATUS_CN.get(str(val), str(val))
    if en in ("actual_action", "deepseek_advice_action"):
        return ACTION_CN.get(str(val), str(val))
    if en == "yesterday_track_type":
        return TRACK_CN.get(str(val), str(val))
    if en == "frequency_block_direction":
        return ACTION_CN.get(str(val), str(val))

    # 日期
    if en == "trade_date":
        return val.isoformat() if val else ""

    # 数值格式化
    if en in ("preview_score", "yesterday_score", "score_delta", "validation_score",
              "signal_accuracy", "advice_accuracy", "gate_accuracy", "actual_score",
              "market_index_chg_pct", "sector_chg_pct", "unrealized_pnl_pct",
              "gate_1_distance_pct", "gate_2_distance_pct", "gate_e_distance_pct",
              "actual_nav_change_pct", "gszzl", "intraday_high_gszzl", "intraday_low_gszzl",
              "ext_num1", "ext_num2"):
        return f"{float(val):.2f}" if val is not None else ""
    if en in ("yesterday_nav", "actual_nav", "cost_basis", "elasticity"):
        return f"{float(val):.4f}" if val is not None else ""
    if en in ("yesterday_position", "actual_target_position"):
        return f"{float(val):.4f}" if val is not None else ""
    if en in ("holding_shares",):
        return f"{float(val):.4f}" if val is not None else ""
    if en in ("holding_market_value",):
        return f"{float(val):.2f}" if val is not None else ""

    # 布尔/整数
    if en in ("gate_1_triggered", "gate_2_triggered", "gate_e_triggered",
              "yesterday_confidence", "preview_confidence", "effective_stars",
              "deepseek_advice_correct", "consecutive_signal_days"):
        return str(int(val)) if val is not None else ""

    # JSON
    if en == "anomaly_flags":
        if isinstance(val, list):
            return json.dumps(val, ensure_ascii=False)
        return str(val) if val else ""

    # 大文本截断(CSV中不截断，完整输出)
    return str(val) if val is not None else ""


@router.get("/validation-download")
async def download_validation_csv(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    fund_code: Optional[str] = Query(None, description="基金代码"),
    sector_code: Optional[str] = Query(None, description="板块代码"),
    db: AsyncSession = Depends(get_session),
):
    """导出策略验证分析表为CSV（中英双语表头，59列）"""
    if start_date:
        sd = date.fromisoformat(start_date)
    else:
        sd = date.today() - timedelta(days=30)
    if end_date:
        ed = date.fromisoformat(end_date)
    else:
        ed = date.today()

    conditions = [
        StrategyValidationLog.trade_date >= sd,
        StrategyValidationLog.trade_date <= ed,
    ]
    if fund_code:
        conditions.append(StrategyValidationLog.fund_code == fund_code)
    if sector_code:
        conditions.append(StrategyValidationLog.sector_code == sector_code)

    stmt = select(StrategyValidationLog).where(*conditions).order_by(
        StrategyValidationLog.trade_date.desc(),
        StrategyValidationLog.fund_code,
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    # 双行表头：中文列名 + 英文字段名
    writer.writerow([col[0] for col in VALIDATION_CSV_COLUMNS])
    writer.writerow([col[1] for col in VALIDATION_CSV_COLUMNS])

    for r in rows:
        row_data = [_format_validation_value(en, getattr(r, en, None)) for cn, en in VALIDATION_CSV_COLUMNS]
        writer.writerow(row_data)

    output.seek(0)
    csv_bytes = b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")
    filename_ascii = f"validation_{sd.isoformat()}_{ed.isoformat()}.csv"
    filename_utf8 = f"策略验证分析_{sd.isoformat()}_{ed.isoformat()}.csv"
    filename_encoded = urllib.parse.quote(filename_utf8, safe="")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=\"" + filename_ascii + "\"; filename*=UTF-8''" + filename_encoded,
        },
    )


@router.get("/validation-history")
async def get_validation_history(
    start_date: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    fund_code: Optional[str] = Query(None, description="基金代码"),
    sector_code: Optional[str] = Query(None, description="板块代码"),
    limit: int = Query(100, description="返回条数上限"),
    db: AsyncSession = Depends(get_session),
):
    """查询策略验证分析历史记录"""
    if start_date:
        sd = date.fromisoformat(start_date)
    else:
        sd = date.today() - timedelta(days=30)
    if end_date:
        ed = date.fromisoformat(end_date)
    else:
        ed = date.today()

    conditions = [
        StrategyValidationLog.trade_date >= sd,
        StrategyValidationLog.trade_date <= ed,
    ]
    if fund_code:
        conditions.append(StrategyValidationLog.fund_code == fund_code)
    if sector_code:
        conditions.append(StrategyValidationLog.sector_code == sector_code)

    stmt = select(StrategyValidationLog).where(*conditions).order_by(
        StrategyValidationLog.trade_date.desc(),
        StrategyValidationLog.fund_code,
    ).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "code": 0,
        "data": {
            "total": len(rows),
            "date_range": {"start": sd.isoformat(), "end": ed.isoformat()},
            "records": [
                {
                    "id": r.id,
                    "trade_date": r.trade_date.isoformat(),
                    "fund_code": r.fund_code,
                    "fund_name": r.fund_name,
                    "sector_code": r.sector_code,
                    "sector_name": r.sector_name,
                    "preview_score": float(r.preview_score) if r.preview_score else None,
                    "preview_signal": r.preview_signal,
                    "preview_confidence": r.preview_confidence,
                    "gszzl": float(r.gszzl) if r.gszzl is not None else None,
                    "gszzl_source": r.gszzl_source,
                    "overall_status": r.overall_status,
                    "actual_action": r.actual_action,
                    "actual_trend": r.actual_trend,
                    "actual_nav_change_pct": float(r.actual_nav_change_pct) if r.actual_nav_change_pct is not None else None,
                    "validation_score": float(r.validation_score) if r.validation_score is not None else None,
                    "signal_accuracy": float(r.signal_accuracy) if r.signal_accuracy is not None else None,
                    "advice_accuracy": float(r.advice_accuracy) if r.advice_accuracy is not None else None,
                    "gate_accuracy": float(r.gate_accuracy) if r.gate_accuracy is not None else None,
                    "system_advice_text": (r.system_advice_text[:100] + "...") if r.system_advice_text and len(r.system_advice_text) > 100 else r.system_advice_text,
                    "deepseek_advice": (r.deepseek_advice[:100] + "...") if r.deepseek_advice and len(r.deepseek_advice) > 100 else r.deepseek_advice,
                    "deepseek_advice_action": r.deepseek_advice_action,
                    "deepseek_advice_correct": r.deepseek_advice_correct,
                    "consecutive_signal_days": r.consecutive_signal_days,
                    "gate_1_triggered": r.gate_1_triggered,
                    "gate_2_triggered": r.gate_2_triggered,
                    "unrealized_pnl_pct": float(r.unrealized_pnl_pct) if r.unrealized_pnl_pct is not None else None,
                    "anomaly_flags": r.anomaly_flags,
                }
                for r in rows
            ],
        },
        "message": "ok",
    }


@router.get("/validation-stats")
async def get_validation_stats(
    days: int = Query(30, description="统计天数"),
    fund_code: Optional[str] = Query(None, description="基金代码"),
    db: AsyncSession = Depends(get_session),
):
    """策略验证统计分析"""
    sd = date.today() - timedelta(days=days)

    conditions = [StrategyValidationLog.trade_date >= sd]
    if fund_code:
        conditions.append(StrategyValidationLog.fund_code == fund_code)

    # 总记录数
    count_stmt = select(func.count(StrategyValidationLog.id)).where(*conditions)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 平均准确率
    avg_stmt = select(
        func.avg(StrategyValidationLog.signal_accuracy),
        func.avg(StrategyValidationLog.advice_accuracy),
        func.avg(StrategyValidationLog.gate_accuracy),
        func.avg(StrategyValidationLog.validation_score),
        func.avg(StrategyValidationLog.deepseek_advice_correct),
    ).where(*conditions)
    avg_result = await db.execute(avg_stmt)
    avg_row = avg_result.one()

    # 信号分布
    sig_dist_stmt = select(
        StrategyValidationLog.preview_signal,
        func.count(StrategyValidationLog.id),
    ).where(*conditions).group_by(StrategyValidationLog.preview_signal)
    sig_result = await db.execute(sig_dist_stmt)
    signal_distribution = {sig or "unknown": cnt for sig, cnt in sig_result.all()}

    # 操作分布
    action_dist_stmt = select(
        StrategyValidationLog.actual_action,
        func.count(StrategyValidationLog.id),
    ).where(*conditions).group_by(StrategyValidationLog.actual_action)
    action_result = await db.execute(action_dist_stmt)
    action_distribution = {
        (ACTION_CN.get(act or "", act or "未知")): cnt
        for act, cnt in action_result.all()
    }

    # 按基金分组准确率
    fund_stats_stmt = select(
        StrategyValidationLog.fund_code,
        StrategyValidationLog.fund_name,
        func.count(StrategyValidationLog.id),
        func.avg(StrategyValidationLog.signal_accuracy),
        func.avg(StrategyValidationLog.advice_accuracy),
        func.avg(StrategyValidationLog.validation_score),
    ).where(*conditions).group_by(
        StrategyValidationLog.fund_code,
        StrategyValidationLog.fund_name,
    )
    fund_result = await db.execute(fund_stats_stmt)
    fund_stats = []
    for fcode, fname, cnt, sig_acc, adv_acc, val_score in fund_result.all():
        fund_stats.append({
            "fund_code": fcode,
            "fund_name": fname or "",
            "count": cnt,
            "signal_accuracy": round(float(sig_acc), 2) if sig_acc else None,
            "advice_accuracy": round(float(adv_acc), 2) if adv_acc else None,
            "validation_score": round(float(val_score), 2) if val_score else None,
        })

    return {
        "code": 0,
        "data": {
            "days": days,
            "total_records": total,
            "avg_signal_accuracy": round(float(avg_row[0]), 2) if avg_row[0] else None,
            "avg_advice_accuracy": round(float(avg_row[1]), 2) if avg_row[1] else None,
            "avg_gate_accuracy": round(float(avg_row[2]), 2) if avg_row[2] else None,
            "avg_validation_score": round(float(avg_row[3]), 2) if avg_row[3] else None,
            "avg_deepseek_accuracy": round(float(avg_row[4]), 2) if avg_row[4] else None,
            "signal_distribution": signal_distribution,
            "action_distribution": action_distribution,
            "fund_stats": fund_stats,
        },
        "message": "ok",
    }
