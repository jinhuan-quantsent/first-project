"""
因子相关性分析 API
分析策略验证表中的因子与准确率指标之间的相关性。
连续因子: Pearson/Spearman 相关系数 + p值
分类因子: 分组均值 + ANOVA
Bonferroni校正防多重比较假阳性
"""
import logging
import math
from datetime import date, timedelta

import numpy as np
from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["因子分析"])

# 连续因子（可用 Pearson/Spearman）
CONTINUOUS_FACTORS = [
    "elasticity",
    "preview_score",
    "yesterday_score",
    "yesterday_confidence",
    "market_index_chg_pct",
    "sector_chg_pct",
    "gszzl",
    "gate_1_distance_pct",
    "gate_2_distance_pct",
    "score_delta",
]

# 分类因子（用分组均值 + ANOVA）
CATEGORICAL_FACTORS = [
    "regime",
    "macd_state",
]

# 合法结果变量（防SQL注入白名单）
RESULT_TYPES = ["deepseek_advice_correct", "signal_accuracy", "advice_accuracy", "gate_accuracy"]


@router.get("/factor-correlation")
async def get_factor_correlation(
    days: int = Query(30, ge=1, le=365, description="回溯天数"),
    result_type: str = Query("deepseek_advice_correct", description="结果变量"),
    min_samples: int = Query(30, ge=5, le=500, description="最小样本量阈值"),
    method: str = Query("pearson", pattern="^(pearson|spearman)$", description="相关系数方法"),
):
    """
    因子相关性分析

    返回各因子与指定准确率指标的相关性:
    - 连续因子(10个): Pearson/Spearman 相关系数 + p值
    - 分类因子(2个): 分组均值 + ANOVA F检验
    - Bonferroni校正: alpha/n_tests 防多重比较假阳性
    """
    from scipy import stats

    if result_type not in RESULT_TYPES:
        return {"error": f"Invalid result_type, must be one of {RESULT_TYPES}"}

    today = date.today()
    start_date = today - timedelta(days=days)
    engine = get_async_engine()

    # 查询: strategy_validation_log LEFT JOIN daily_signal_snapshot
    async with AsyncSession(engine) as session:
        sql = text(f"""
            SELECT
                v.elasticity, v.preview_score, v.yesterday_score,
                v.yesterday_confidence, v.market_index_chg_pct,
                v.sector_chg_pct, v.gszzl,
                v.gate_1_distance_pct, v.gate_2_distance_pct,
                v.score_delta,
                s.regime, s.macd_state,
                v.{result_type} AS result_value
            FROM strategy_validation_log v
            LEFT JOIN daily_signal_snapshot s
                ON v.fund_code = s.target_code COLLATE utf8mb4_unicode_ci
                AND v.trade_date = s.snapshot_date
                AND s.target_type = 'fund'
            WHERE v.trade_date >= :start_date
            AND v.trade_date < :today
            AND v.{result_type} IS NOT NULL
        """)
        result = await session.execute(sql, {"start_date": start_date, "today": today})
        rows = result.fetchall()

    sample_size = len(rows)

    if sample_size < min_samples:
        return {
            "days": days,
            "sample_size": sample_size,
            "min_samples": min_samples,
            "method": method,
            "result_type": result_type,
            "message": f"样本量不足 ({sample_size} < {min_samples})",
            "continuous_factors": [],
            "categorical_factors": [],
        }

    # 提取结果变量数组
    result_values = np.array([float(r[-1]) for r in rows], dtype=float)

    # === 连续因子分析 ===
    n_tests = len(CONTINUOUS_FACTORS) + len(CATEGORICAL_FACTORS)
    bonferroni_alpha = 0.05 / n_tests
    continuous_results = []

    for idx, factor_name in enumerate(CONTINUOUS_FACTORS):
        # 提取 (factor_value, result_value) 对, 过滤 NULL
        pairs = []
        for row in rows:
            val = row[idx]
            if val is not None:
                pairs.append((float(val), float(row[-1])))

        if len(pairs) < min_samples:
            continuous_results.append({
                "factor_name": factor_name,
                "correlation": None,
                "p_value": None,
                "sample_size": len(pairs),
                "significant": False,
                "note": "有效样本不足",
            })
            continue

        x = np.array([p[0] for p in pairs], dtype=float)
        y = np.array([p[1] for p in pairs], dtype=float)

        try:
            if method == "spearman":
                corr, p_value = stats.spearmanr(x, y)
            else:
                corr, p_value = stats.pearsonr(x, y)
        except Exception:
            corr, p_value = 0.0, 1.0

        if math.isnan(corr):
            corr = 0.0
        if math.isnan(p_value):
            p_value = 1.0

        continuous_results.append({
            "factor_name": factor_name,
            "correlation": round(float(corr), 4),
            "p_value": round(float(p_value), 4),
            "sample_size": len(pairs),
            "significant": float(p_value) < bonferroni_alpha,
        })

    # 按相关系数绝对值降序
    continuous_results.sort(key=lambda x: abs(x.get("correlation") or 0), reverse=True)

    # === 分类因子分析 ===
    categorical_results = []
    cat_offset = len(CONTINUOUS_FACTORS)  # 分类因子在查询结果中的列偏移

    for idx, factor_name in enumerate(CATEGORICAL_FACTORS):
        col_idx = cat_offset + idx
        groups = {}
        for row in rows:
            val = row[col_idx]
            if val is not None:
                groups.setdefault(val, []).append(float(row[-1]))

        group_stats = {}
        for g, vals in sorted(groups.items(), key=lambda x: -len(x[1])):
            if vals:
                group_stats[g] = {
                    "mean": round(float(np.mean(vals)), 4),
                    "n": len(vals),
                }

        # 单因素 ANOVA (需 2+ 组, 每组 2+ 样本)
        anova_p = None
        valid_groups = [v for v in groups.values() if len(v) >= 2]
        if len(valid_groups) >= 2:
            try:
                _f_stat, anova_p = stats.f_oneway(*[np.array(v) for v in valid_groups])
                if math.isnan(anova_p):
                    anova_p = None
            except Exception:
                pass

        categorical_results.append({
            "factor_name": factor_name,
            "groups": group_stats,
            "sample_size": sum(len(v) for v in groups.values()),
            "anova_p_value": round(float(anova_p), 4) if anova_p is not None else None,
            "significant": anova_p is not None and float(anova_p) < bonferroni_alpha,
        })

    return {
        "days": days,
        "sample_size": sample_size,
        "method": method,
        "result_type": result_type,
        "bonferroni_alpha": round(bonferroni_alpha, 4),
        "continuous_factors": continuous_results,
        "categorical_factors": categorical_results,
    }


@router.get("/snapshots")
async def get_analysis_snapshots(
    analysis_type: str = Query(
        None,
        description="分析类型: rolling_window / per_fund / factor_correlation / data_quality",
    ),
    fund_code: str = Query(None, description="基金代码(per_fund专用)"),
    metric_name: str = Query(None, description="指标名筛选"),
    days: int = Query(30, ge=1, le=365, description="回溯天数"),
):
    """
    查询分析日报快照

    返回 analysis_daily_snapshot 表中存储的历史分析结果。
    每天 validation-B (17:35) 自动写入。
    """
    from app.models.analysis_daily_snapshot import AnalysisDailySnapshot
    from sqlalchemy import select

    today = date.today()
    start_date = today - timedelta(days=days)
    engine = get_async_engine()

    async with AsyncSession(engine) as session:
        stmt = select(AnalysisDailySnapshot).where(
            AnalysisDailySnapshot.snapshot_date >= start_date,
            AnalysisDailySnapshot.snapshot_date <= today,
        )

        if analysis_type:
            if analysis_type not in ("rolling_window", "per_fund", "factor_correlation", "data_quality"):
                return {"error": f"Invalid analysis_type, must be one of: rolling_window, per_fund, factor_correlation, data_quality"}
            stmt = stmt.where(AnalysisDailySnapshot.analysis_type == analysis_type)

        if fund_code:
            stmt = stmt.where(AnalysisDailySnapshot.fund_code == fund_code)

        if metric_name:
            stmt = stmt.where(AnalysisDailySnapshot.metric_name == metric_name)

        stmt = stmt.order_by(
            AnalysisDailySnapshot.snapshot_date.desc(),
            AnalysisDailySnapshot.metric_name,
        ).limit(500)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    return {
        "total": len(rows),
        "days": days,
        "filters": {
            "analysis_type": analysis_type,
            "fund_code": fund_code,
            "metric_name": metric_name,
        },
        "snapshots": [
            {
                "snapshot_date": str(r.snapshot_date),
                "analysis_type": r.analysis_type,
                "fund_code": r.fund_code,
                "metric_name": r.metric_name,
                "metric_value": float(r.metric_value) if r.metric_value is not None else None,
                "sample_size": r.sample_size,
                "p_value": float(r.p_value) if r.p_value is not None else None,
                "is_significant": r.is_significant,
                "extra": r.extra,
            }
            for r in rows
        ],
    }


@router.get("/snapshots/summary")
async def get_snapshot_summary(
    days: int = Query(30, ge=1, le=365, description="回溯天数"),
):
    """
    分析快照汇总 — 一键查看4方向的最新结果

    返回每个分析类型的最新快照日期和关键指标摘要。
    """
    from app.models.analysis_daily_snapshot import AnalysisDailySnapshot
    from sqlalchemy import select, func as sa_func

    today = date.today()
    start_date = today - timedelta(days=days)
    engine = get_async_engine()

    async with AsyncSession(engine) as session:
        # 最新快照日期
        latest_stmt = select(
            sa_func.max(AnalysisDailySnapshot.snapshot_date)
        )
        latest_result = await session.execute(latest_stmt)
        latest_date = latest_result.scalar()

        if latest_date is None:
            return {"message": "暂无快照数据", "latest_date": None}

        # 各类型最新日期的记录
        summaries = {}
        for atype in ("rolling_window", "per_fund", "factor_correlation", "data_quality"):
            stmt = select(AnalysisDailySnapshot).where(
                AnalysisDailySnapshot.analysis_type == atype,
                AnalysisDailySnapshot.snapshot_date == latest_date,
            ).order_by(AnalysisDailySnapshot.metric_name)
            result = await session.execute(stmt)
            rows = result.scalars().all()

            summaries[atype] = {
                "count": len(rows),
                "records": [
                    {
                        "fund_code": r.fund_code,
                        "metric_name": r.metric_name,
                        "metric_value": float(r.metric_value) if r.metric_value is not None else None,
                        "sample_size": r.sample_size,
                        "p_value": float(r.p_value) if r.p_value is not None else None,
                        "is_significant": r.is_significant,
                        "extra": r.extra,
                    }
                    for r in rows
                ],
            }

    return {
        "latest_date": str(latest_date),
        "summary": summaries,
    }
