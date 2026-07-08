#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回填 strategy_validation_log 中 trade_date=2026-07-07 的脏数据。

背景
----
2026-07-07 的导出 CSV 发现 5 个数据质量 bug（对应 scheduler.py 的 A/B/C/D/E 修复）：
  A: sector_name / sector_chg_pct 为 NULL（原查 SectorHeatmapCache 表，该表从不写入）
  B: market_index_chg_pct 为 0（盘中日线未生成时被伪装成平盘）
  D: system_advice_text【结论】写"建议加仓"但【持仓】当前/目标均为 0%（应为"建议持有"）
  E: yesterday_position 为 0（原取 snapshot.target_position_pct，无实际持仓概念）

本脚本对 07-07 行做一次性修正（C 为解析层 bug，不影响已落库数据，无需回填）。

回填值来源（均为可验证的真实历史数据，非伪造）
--------------------------------------------
  market_index_chg_pct : HS300(000300.SH) 2026-07-07 真实涨跌 = -1.0272%
                         （Tushare index_daily，与修复后兜底源 get_index_data 一致）
  sector_chg_pct       : 各行业(申万 801xxx.SI) 2026-07-07 真实涨跌（Tushare index_daily 实测）
  sector_name          : 复制 2026-07-08 同 fund_code 行（fund→板块为静态映射，100% 可靠）
                         013286 无板块分类 → 保持 NULL（与 07-08 一致，非 bug）
  yesterday_position   : 复制 2026-07-08 同 fund_code 行。
                         该值是修复后逻辑在 07-08 算出的"昨日实际持仓"（≈07-07 真实持仓），
                         是距 07-07 最近的实际持仓快照，作为 07-07 昨日持仓的一日近似。
  system_advice_text   : 手术修补两处叙事，使其与已修正的结构化字段一致：
                         - 【大盘】大盘跌0.00% → 大盘跌1.03%（Fix B 文案）
                         - 012538/022387【结论】建议加仓。 → 建议持有。（Fix D 文案）

安全特性
--------
  * 默认 DRY-RUN：仅打印每行的变更计划，不写库。加 --apply 才执行。
  * 幂等：重跑安全；文本修补仅当旧子串存在时才替换（不会重复打补丁）。
  * 仅 UPDATE trade_date=2026-07-07 的行，不影响其他日期。
"""
import sys
import pymysql

DB = dict(host="127.0.0.1", user="funduser", password="FundSent2026!",
          db="fund_sentiment", charset="utf8mb4")
TARGET_DATE = "2026-07-07"
SOURCE_DATE = "2026-07-08"  # sector_name + yesterday_position 的复制源

# 已用 Tushare index_daily(ts_code, start_date='20260707', end_date='20260707') 实测，
# 按下表 pct_chg 回填。历史数据确定不变，硬编码以保证回填可复现、不依赖网络。
HS300_0707 = -1.0272
SECTOR_PCT_0707 = {
    "801050": -2.7508,  # 有色金属
    "801790": -2.5898,  # 非银金融
    "801110": -1.7189,  # 家用电器
    "801080": -0.682,    # 电子
    "801030": -2.7447,   # 基础化工
    "801150": -3.707,    # 医药生物
    "801770": -0.0461,   # 通信
    "801880": -2.0922,   # 汽车
}

# 大盘叙事展示用的四舍五入值（与 decimal(6,2) 存储一致）
HS300_DISPLAY = f"{abs(round(HS300_0707, 2)):.2f}"  # "1.03"
# 需修正【结论】的基金（当前/目标均为 0% 却写"建议加仓"）
CONCLUSION_FIX_FUNDS = {"012538", "022387"}


def main(apply: bool = False) -> None:
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor(pymysql.cursors.DictCursor)

        # 1) 载入复制源（07-08）的 sector_name + yesterday_position
        cur.execute(
            "SELECT fund_code, sector_name, yesterday_position "
            "FROM strategy_validation_log WHERE trade_date=%s",
            (SOURCE_DATE,),
        )
        src = {r["fund_code"]: r for r in cur.fetchall()}

        # 2) 载入目标（07-07）待修正行
        cur.execute(
            "SELECT id, fund_code, sector_code, sector_name, sector_chg_pct, "
            "market_index_chg_pct, yesterday_position, system_advice_text "
            "FROM strategy_validation_log WHERE trade_date=%s ORDER BY fund_code",
            (TARGET_DATE,),
        )
        rows = cur.fetchall()

        plan = []
        for r in rows:
            fc = r["fund_code"]
            sc = r["sector_code"]
            text = r["system_advice_text"] or ""

            new_sector_name = src.get(fc, {}).get("sector_name")  # 可能为 None
            new_sector_chg = SECTOR_PCT_0707.get(sc) if sc else None
            new_mkt = HS300_0707
            new_yest = src.get(fc, {}).get("yesterday_position")

            patches = []
            # Fix B 文案：大盘跌0.00% -> 跌1.03%
            if "大盘跌0.00%" in text:
                text = text.replace("大盘跌0.00%", f"大盘跌{HS300_DISPLAY}%")
                patches.append(f"大盘→跌{HS300_DISPLAY}%")
            # Fix D 文案：012538/022387 建议加仓 -> 建议持有
            if fc in CONCLUSION_FIX_FUNDS and "【结论】建议加仓。" in text:
                text = text.replace("【结论】建议加仓。", "【结论】建议持有。")
                patches.append("结论→持有")

            plan.append({
                "id": r["id"], "fund_code": fc, "sector_code": sc,
                "sector_name": new_sector_name, "sector_chg_pct": new_sector_chg,
                "market_index_chg_pct": new_mkt, "yesterday_position": new_yest,
                "text": text, "patches": patches,
            })

        # 3) 打印变更计划
        print(f"=== 回填计划: trade_date={TARGET_DATE} (共 {len(plan)} 行) ===")
        for p in plan:
            print(
                f"  {p['fund_code']} (sector={p['sector_code']}): "
                f"sector_name={p['sector_name']!r} "
                f"sector_chg_pct={p['sector_chg_pct']} "
                f"market_index_chg_pct={p['market_index_chg_pct']} "
                f"yesterday_position={p['yesterday_position']} "
                f"text_patches={p['patches']}"
            )

        if not apply:
            print("\n[DRY-RUN] 未写入任何数据。加 --apply 执行。")
            return

        # 4) 执行
        for p in plan:
            cur.execute(
                "UPDATE strategy_validation_log SET "
                "sector_name=%s, sector_chg_pct=%s, market_index_chg_pct=%s, "
                "yesterday_position=%s, system_advice_text=%s, updated_at=NOW() "
                "WHERE id=%s",
                (p["sector_name"], p["sector_chg_pct"], p["market_index_chg_pct"],
                 p["yesterday_position"], p["text"], p["id"]),
            )
        conn.commit()
        print(f"\n[APPLIED] 已更新 {len(plan)} 行。")
    finally:
        conn.close()


if __name__ == "__main__":
    main(apply=("--apply" in sys.argv))
