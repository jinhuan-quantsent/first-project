"""
每日自动导出策略验证表 + 分析快照表(全4类) → 上传到 IMA 知识库
在 validation-B 完成后运行（建议 17:40）

用法:
    python export_and_upload.py              # 导出今天的数据
    python export_and_upload.py 2026-07-10   # 导出指定日期的数据（测试用）

crontab:
    50 17 * * 1-5  cd /opt/fund-sentiment/v5-deploy/backend && venv/bin/python scripts/export_and_upload.py >> /opt/fund-sentiment/v5-deploy/logs/ima_upload.log 2>&1
"""

import os
import sys
import csv
import logging
from datetime import datetime, date, timedelta

# 把 backend 目录加入 path，便于 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from ima_kb_uploader import upload_to_kb

# ── 日志 ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── MySQL 配置 ────────────────────────────────────────────────
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "funduser",
    "password": "FundSent2026!",
    "database": "fund_sentiment",
    "charset": "utf8mb4",
}

# ── IMA 知识库配置 ────────────────────────────────────────────
KB_ID = "tuJfn4N7tageFElKFxYUUJ5c6DlrulR63EfeF7tKNXw="
FOLDER_SNAPSHOT = "folder_7482043537567835"   # 每日快照
FOLDER_FACTOR   = "folder_7482043537569027"   # 因子数据

# 导出临时目录
EXPORT_DIR = "/tmp/ima_exports"


# ── 工具函数 ──────────────────────────────────────────────────
def _clean_value(v):
    """把 MySQL 返回的值转为 CSV 友好的字符串"""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)


def _rows_to_csv(rows: list[dict], filepath: str):
    """把 dict 列表写成 CSV（UTF-8 BOM，Excel 友好）"""
    if not rows:
        return False
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _clean_value(v) for k, v in row.items()})
    return True


# ── 导出函数 ──────────────────────────────────────────────────
def export_strategy_validation(conn, target_date: str) -> str | None:
    """导出 strategy_validation_log（策略验证表）"""
    sql = """
        SELECT trade_date, fund_code, fund_name, sector_code, sector_name,
               user_id, yesterday_signal, yesterday_confidence, yesterday_score,
               yesterday_position, yesterday_nav, yesterday_track_type,
               preview_score, preview_signal, preview_confidence,
               gszzl, gszzl_source, elasticity, score_delta, effective_stars,
               intraday_high_gszzl, intraday_low_gszzl,
               preview_summary, anomaly_flags,
               market_index_chg_pct, sector_chg_pct,
               actual_action, actual_target_position, actual_nav, actual_signal,
               cost_basis, unrealized_pnl_pct, holding_shares, holding_market_value,
               gate_1_triggered, gate_2_triggered, gate_e_triggered,
               gate_1_distance_pct, gate_2_distance_pct, gate_e_distance_pct,
               frequency_block_direction, overall_status,
               actual_trend, actual_nav_change_pct, actual_score,
               actual_signal_level, validation_score,
               signal_accuracy, advice_accuracy, gate_accuracy,
               system_advice_action, deepseek_advice_action, deepseek_advice_correct,
               consecutive_signal_days, ext_text1,
               system_advice_text, advice_reason, deepseek_advice,
               created_at, updated_at
        FROM strategy_validation_log
        WHERE trade_date = %s
        ORDER BY fund_code
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(sql, (target_date,))
        rows = cur.fetchall()

    if not rows:
        logger.warning(f"策略验证表无 {target_date} 数据，跳过")
        return None

    filename = f"策略验证_{target_date}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)
    if _rows_to_csv(rows, filepath):
        logger.info(f"导出策略验证表: {len(rows)} 行 → {filepath}")
        return filepath
    return None


def export_analysis_snapshot(conn, target_date: str) -> str | None:
    """导出 analysis_daily_snapshot 全量（4类: rolling_window/per_fund/factor_correlation/data_quality）"""
    sql = """
        SELECT snapshot_date, analysis_type, fund_code, metric_name,
               metric_value, sample_size, p_value, is_significant, extra,
               created_at, updated_at
        FROM analysis_daily_snapshot
        WHERE snapshot_date = %s
        ORDER BY analysis_type, metric_name, fund_code
    """
    with conn.cursor(pymysql.cursors.DictCursor) as cur:
        cur.execute(sql, (target_date,))
        rows = cur.fetchall()

    if not rows:
        logger.warning(f"分析快照表无 {target_date} 数据，跳过")
        return None

    filename = f"分析快照_{target_date}.csv"
    filepath = os.path.join(EXPORT_DIR, filename)
    if _rows_to_csv(rows, filepath):
        logger.info(f"导出分析快照表: {len(rows)} 行 → {filepath}")
        return filepath
    return None


# ── 主流程 ────────────────────────────────────────────────────
def main():
    # 日期参数：默认今天，可传参指定
    target_date = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    logger.info(f"=== IMA 知识库每日上传开始 (target_date={target_date}) ===")

    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = pymysql.connect(**MYSQL_CONFIG)
    uploaded = 0
    failed = 0

    try:
        # ── 1. 策略验证表 → 每日快照 ──
        sv_file = export_strategy_validation(conn, target_date)
        if sv_file:
            try:
                upload_to_kb(
                    sv_file, KB_ID, FOLDER_SNAPSHOT,
                    rename=os.path.basename(sv_file),
                )
                logger.info(f"✓ 策略验证表已上传到「每日快照」文件夹")
                uploaded += 1
            except Exception as e:
                logger.error(f"✗ 策略验证表上传失败: {e}", exc_info=True)
                failed += 1

        # ── 2. 分析快照表(全4类) → 因子数据 ──
        snap_file = export_analysis_snapshot(conn, target_date)
        if snap_file:
            try:
                upload_to_kb(
                    snap_file, KB_ID, FOLDER_FACTOR,
                    rename=os.path.basename(snap_file),
                )
                logger.info(f"✓ 分析快照表已上传到「因子数据」文件夹")
                uploaded += 1
            except Exception as e:
                logger.error(f"✗ 分析快照表上传失败: {e}", exc_info=True)
                failed += 1

        if uploaded == 0 and failed == 0:
            logger.warning(f"今日无数据可上传（可能是非交易日）")

        logger.info(
            f"=== 完成: 成功 {uploaded}, 失败 {failed} ==="
        )
    finally:
        conn.close()
        # 清理临时 CSV 文件
        for f in os.listdir(EXPORT_DIR):
            if f.startswith(("策略验证_", "分析快照_")):
                try:
                    os.remove(os.path.join(EXPORT_DIR, f))
                except OSError:
                    pass

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
