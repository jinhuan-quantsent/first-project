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
