"""
仓位建议引擎 — V5.0
5×7 仓位矩阵 + 置信度修正 + 市场体制修正 + 交易成本校验 + 7天频率限制

Gate体系重构版：
- 持仓风控层：Gate1(20%回撤清仓) > Gate2(MA20破位+10%回撤清仓) > Gate-E(E级提示不减仓)
- 建仓准入层：Gate3(信号E/Gate2触发/置信度低/excluded → 不准入)
- Gate3不再在持仓层处理，仅影响建仓准入
"""
from __future__ import annotations

import logging

from datetime import date, datetime, timedelta
from typing import Optional

from app.engine.signal_mapper import SignalMapper
from app.core.config import settings
from app.core.redis_client import cache_get
from app.core.config import settings as _settings  # INTRADAY_PREVIEW_CACHE_PREFIX
import asyncio

logger = logging.getLogger(__name__)


class PositionEngineV5:
    """V5.0 仓位建议引擎"""

    # 当前仓位等级对应的百分比范围
    LEVEL_PCT: dict[str, float] = {
        "empty": 0.0,
        "light": 0.25,
        "mid": 0.50,
        "heavy": 0.75,
        "full": 1.0,
    }

    LEVELS: list[str] = ["empty", "light", "mid", "heavy", "full"]

    def __init__(self, session) -> None:
        self._session = session
        self._matrix = settings.V5_POSITION_MATRIX
        self._conf_adj = settings.V5_CONFIDENCE_POSITION_ADJ
        self._cost_threshold = settings.V5_COST_THRESHOLD_PCT
        self._freq_days = settings.V5_FREQUENCY_LIMIT_DAYS

    async def calculate(
        self,
        user_id: str,
        fund_code: str,
        current_position_pct: float,
        signal_level: str,
        confidence_stars: int,
        regime: str = "sideways",
        cash_amount: float = 0.0,        # V5.1: 用户可用现金
        total_assets: float = 0.0,       # V5.1: 用户总资产(持仓+现金)
    ) -> dict:
        """
        计算仓位调整建议
        输入：user_id, fund_code, current_position_pct, signal_level, confidence_stars
        输出：PositionAdvice dict

        action 字段覆盖所有场景（优先级从高到低）：
        1. 持仓风控Gate触发 → decrease (target=0) / hold (Gate-E提示)
        2. 置信度过低（1星）→ hold
        3. 7天频率限制 → hold
        4. B级中性信号 → hold
        5. 交易成本阈值 → hold
        6. 正常矩阵计算 → increase/hold/decrease
        """
        # 1. 确定当前仓位等级
        current_level = self._pct_to_level(current_position_pct)

        # 2. 矩阵查表 → 直接获取目标仓位百分比
        signal_idx = self._signal_to_idx(signal_level)
        current_idx = self.LEVELS.index(current_level)
        target_pct = self._matrix[current_idx][signal_idx]

        # 3. 置信度修正
        conf_factor = self._conf_adj.get(confidence_stars, 0.0)
        current_pct = current_position_pct
        if target_pct > current_pct:
            # 加仓：置信度修正
            adjusted_pct = current_pct + (target_pct - current_pct) * conf_factor
        elif target_pct < current_pct:
            # 减仓：置信度修正
            adjusted_pct = current_pct - (current_pct - target_pct) * conf_factor
        else:
            adjusted_pct = target_pct

        # 4. 市场体制修正
        # 牛市可稍激进（+10%），熊市更保守（-15%），极端波动极保守（-30%）
        regime_adj = self._calc_regime_adj(regime)
        if regime_adj != 1.0:
            delta = adjusted_pct - current_pct
            adjusted_pct = current_pct + delta * regime_adj

        # 5. 交易成本校验
        cost_rejected = False
        if abs(adjusted_pct - current_pct) < self._cost_threshold:
            cost_rejected = True
            adjusted_pct = current_pct  # 不操作
        cash_warning = None  # V5.1: 初始化现金不足警告
        constraint_result = None  # V5.1: 组合约束结果
        # V5.1 加仓金额校验(现金感知)
        if adjusted_pct > current_pct and total_assets > 0 and cash_amount > 0:
            required_amount = (adjusted_pct - current_pct) * total_assets
            if required_amount > cash_amount:
                max_affordable_pct = current_pct + (cash_amount / total_assets)
                cash_warning = f"加仓需{required_amount:.0f}元, 可用现金{cash_amount:.0f}元不足, 降为{max_affordable_pct:.1%}可支撑仓位"
                adjusted_pct = max_affordable_pct


        # 7. 7天频率检查
        frequency_blocked = False
        frequency_block_direction = None  # V5.1: 仅限减仓方向
        last_execute = await self._get_last_execute_date(
            user_id, fund_code,
            operation_types=["sell", "decrease"],  # V5.1: C类基金冷却期仅限减仓/赎回，加仓不受限
        )
        if last_execute:
            days_since = (date.today() - last_execute).days
            if days_since < self._freq_days:
                frequency_blocked = True
                frequency_block_direction = "decrease"  # 仅限减仓方向

        # 7. 调用趋势卫士获取完整趋势数据（含持仓风控Gate + 板块轨道 + 准入层）
        trend_guard_data = await calculate_trend_guard(
            fund_code=fund_code,
            signal_level=signal_level,
            confidence_stars=confidence_stars,
            current_position=current_position_pct,
        )

        # 8. 确定操作类型和原因（优先级覆盖）
        gate_triggered = trend_guard_data.get("gate_triggered") if trend_guard_data else None   # DEPRECATED
        gates = trend_guard_data.get("gates") if trend_guard_data else None  # 新结构化
        sector_track = trend_guard_data.get("sector_track") if trend_guard_data else None
        admission_gate = trend_guard_data.get("admission_gate") if trend_guard_data else None

        if gate_triggered:
            # 持仓风控Gate触发 — 最高优先级（安全保护）
            gate = gate_triggered.get("gate", "") if isinstance(gate_triggered, dict) else ""
            reason_text = gate_triggered.get("reason", "") if isinstance(gate_triggered, dict) else ""

            if gate == "gate-1":
                # Gate 1：极端回撤保命闸，无条件强制清仓
                adjusted_pct = 0.0
                action = "decrease"
                reason = f"触发持仓风控闸门（{reason_text}），强制清仓"
            elif gate == "gate-2":
                # Gate 2：趋势破位离场闸，强制清仓
                adjusted_pct = 0.0
                action = "decrease"
                reason = f"触发持仓风控闸门（{reason_text}），强制清仓"
            elif gate == "gate-e":
                # Gate-E：情绪过热提示闸，仅提示不减仓
                adjusted_pct = current_pct  # 保持当前仓位
                action = "hold"
                reason = f"触发情绪提示（{reason_text}），建议持有观察"
            else:
                # 兜底（不应触发）
                adjusted_pct = current_pct
                action = "hold"
                reason = f"触发闸门（{reason_text}），未知闸口，默认持有"

        elif confidence_stars <= 1:
            # 置信度过低 — 忽略信号
            action = "hold"
            adjusted_pct = current_pct
            reason = "置信度过低，忽略信号"
        elif frequency_blocked:
            # 7天频率限制（V5.1: 仅限制减仓，加仓放行）
            # 冷却期只阻止减仓操作，加仓方向仍可正常走矩阵计算
            # 因为 C类基金买入0手续费，频繁加仓不会产生额外成本
            # 下面的 else 分支会正常处理 increase/hold/decrease
            # 当 adjusted_pct > current_pct(即加仓方向)时，frequency_blocked 不阻拦
            # 当 adjusted_pct <= current_pct(即减仓/持有方向)时，强制 hold
            if adjusted_pct <= current_pct:
                # 减仓或持有方向 → 冷却期阻止
                action = "hold"
                adjusted_pct = current_pct
                reason = "7天内已减仓/赎回，冷却期暂不减仓"
            else:
                # 加仓方向 → 冷却期放行，正常走矩阵
                frequency_blocked = False  # 重置标记，加仓不受冷却限制
                if abs(adjusted_pct - current_pct) < 0.01:
                    action = "hold"
                    reason = "7天内已减仓/赎回，但加仓方向不受冷却限制，当前建议持有"
                else:
                    action = "increase"
                    reason = self._generate_reason(
                        signal_level, confidence_stars, current_level, adjusted_pct,
                        cost_rejected=False, frequency_blocked=False,
                    ) + "（加仓不受7天冷却限制）"
        elif signal_level == "B":
            # B级中性信号
            action = "hold"
            adjusted_pct = current_pct
            reason = "B级中性信号，建议持有"
        elif cost_rejected:
            # 交易成本阈值
            action = "hold"
            reason = "调整幅度小于交易成本阈值（1.5%），建议暂不操作"
        else:
            # 正常矩阵计算结果
            if abs(adjusted_pct - current_pct) < 0.01:
                action = "hold"
            elif adjusted_pct > current_pct:
                action = "increase"
            else:
                action = "decrease"
            reason = self._generate_reason(
                signal_level, confidence_stars, current_level, adjusted_pct,
                cost_rejected, frequency_blocked,
            )

        # 10. V5.1 组合约束裁剪(仅影响非清仓建议)
        if settings.ENABLE_PORTFOLIO_CONSTRAINTS and action != "decrease":
            constraint_result = await self.apply_portfolio_constraints(
                user_id=user_id,
                fund_code=fund_code,
                raw_target_pct=adjusted_pct,
                current_pct=current_pct,
                cash_amount=cash_amount,
                total_assets=total_assets,
            )
            if constraint_result["constraints"]:
                adjusted_pct = constraint_result["adjusted_pct"]
                if adjusted_pct <= current_pct and action == "increase":
                    action = "hold"
                    reason = "组合约束阻止加仓: " + "; ".join(constraint_result["constraints"])
                elif action == "increase":
                    # 约束部分削减目标，更新 reason 显示实际目标
                    reason = self._generate_reason(
                        signal_level, confidence_stars, current_level, adjusted_pct,
                        cost_rejected, frequency_blocked,
                    )
        # 9. 构建趋势卫士补充文案
        trend_guard_text = ""
        if trend_guard_data:
            trend_guard_text = trend_guard_data.get("trend_narrative", "")
            if not trend_guard_text:
                trend_guard_text = trend_guard_data.get("operation_suggestion", "")

        # contrarian 轨道补充提示
        if sector_track == "contrarian" and action == "hold":
            reason += "（逆向轨道：板块底部区域，可关注逆向布局机会）"

        return {
            "fund_code": fund_code,
            "current_position_pct": round(current_pct, 4),
            "target_position_pct": round(adjusted_pct, 4),
            "action": action,
            "signal_level": signal_level,
            "confidence_stars": confidence_stars,
            "matrix_result": {
                "current_level": current_level,
                "target_pct": round(target_pct, 4),
                "signal_idx": signal_idx,
                "current_idx": current_idx,
            },
            "confidence_adj_factor": conf_factor,
            "regime_adj_factor": regime_adj,
            "cost_rejected": cost_rejected,
            "frequency_blocked": frequency_blocked,
            "frequency_block_direction": frequency_block_direction,  # V5.1: "decrease"或None
            "reason": reason,
            "trend_text": trend_guard_data.get("trend_narrative", "") if trend_guard_data else "",
            "trend_guard_text": trend_guard_text,
            "trend_guard": trend_guard_data,
            "gates": gates,          # 新结构化 Gate 对象（gate_1/gate_2/gate_e/overall_status）
            "track_type": sector_track,  # 轨道类型顶层字段（前端直接读）
            "cash_warning": cash_warning,  # V5.1: 现金不足警告
            "portfolio_constraints": constraint_result.get("constraints", []) if constraint_result else [],
            "constraint_detail": constraint_result.get("constraint_detail", {}) if constraint_result else {},
            "sector_track": sector_track,
            "admission_gate": admission_gate,  # 准入层结果
        }

    async def apply_portfolio_constraints(
        self,
        user_id: str,
        fund_code: str,
        raw_target_pct: float,
        current_pct: float,
        cash_amount: float = 0.0,
        total_assets: float = 0.0,
    ) -> dict:
        """V5.1 组合约束裁剪 - 将矩阵查表的理想仓位裁剪到组合可行范围
        
        三层约束(按优先级叠加裁剪):
        1. 单基金上限: target_pct <= V5_SINGLE_FUND_CAP (30%)
        2. 板块上限: 同板块Sigma target_pct <= V5_SECTOR_POSITION_CAP (25%)
        3. 总仓位上限: Sigma(所有基金持仓/总资产) <= V5_TOTAL_POSITION_CAP (80%)
        
        Gate1/Gate2清仓不受约束影响(安全优先级最高)
        """
        from app.core.config import settings
        if not settings.ENABLE_PORTFOLIO_CONSTRAINTS:
            return {"adjusted_pct": raw_target_pct, "constraints": [], "constraint_detail": {}}
        
        from sqlalchemy import select, func
        from app.models.user_portfolio import UserPortfolio
        from app.models.user_cash import UserCash
        from app.models.position_rating_fund_map import PositionRatingFundMap
        
        constraints_applied = []
        adjusted_pct = raw_target_pct
        constraint_detail = {}

        # === 安全网: total_assets=0 时自动从 DB 计算 ===
        # 修复: API 路径未传 total_assets → denominator=1 → sector_used_pct 荒谬
        if total_assets <= 0:
            try:
                from sqlalchemy import select as _sel, func as _func
                mv_stmt = _sel(_func.sum(UserPortfolio.market_value)).where(
                    UserPortfolio.user_id == user_id
                )
                mv_result = await self._session.execute(mv_stmt)
                mv_total = float(mv_result.scalar() or 0)

                cash_total = 0.0
                try:
                    cash_stmt = _sel(UserCash.cash_amount).where(
                        UserCash.user_id == user_id
                    )
                    cash_result = await self._session.execute(cash_stmt)
                    cash_row = cash_result.first()
                    if cash_row and cash_row[0]:
                        cash_total = float(cash_row[0])
                except Exception:
                    pass

                total_assets = mv_total + cash_total
                if total_assets > 0:
                    logger.info(
                        f"[V5.1] total_assets=0, 自动计算: "
                        f"持仓市值={mv_total:.2f} + 现金={cash_total:.2f} = {total_assets:.2f}"
                    )
            except Exception as e:
                logger.warning(f"[V5.1] total_assets 自动计算失败: {e}")
        
        # === 约束1: 单基金上限 ===
        single_cap = settings.V5_SINGLE_FUND_CAP
        if adjusted_pct > single_cap:
            constraints_applied.append(f"单基金上限{single_cap:.0%}裁剪: {adjusted_pct:.0%} -> {single_cap:.0%}")
            adjusted_pct = single_cap
        
        # === 约束2: 板块上限 ===
        sector_cap = settings.V5_SECTOR_POSITION_CAP
        sector_stmt = select(PositionRatingFundMap.sw_sector_code).where(
            PositionRatingFundMap.fund_code == fund_code,
            PositionRatingFundMap.status == "active",
        ).limit(1)
        sector_result = await self._session.execute(sector_stmt)
        sector_code = sector_result.scalar_one_or_none()
        constraint_detail["sector_code"] = sector_code
        
        if sector_code:
            same_sector_stmt = select(PositionRatingFundMap.fund_code).where(
                PositionRatingFundMap.sw_sector_code == sector_code,
                PositionRatingFundMap.status == "active",
            )
            same_sector_result = await self._session.execute(same_sector_stmt)
            same_sector_funds = [row[0] for row in same_sector_result.fetchall()]
            
            held_stmt = select(UserPortfolio.fund_code, UserPortfolio.market_value).where(
                UserPortfolio.user_id == user_id,
                UserPortfolio.fund_code.in_(same_sector_funds),
            )
            held_result = await self._session.execute(held_stmt)
            held_in_sector = {row[0]: float(row[1] or 0) for row in held_result.fetchall()}
            
            denominator = total_assets if total_assets > 0 else 1
            sector_used_pct = sum(held_in_sector.values()) / denominator
            sector_remaining = sector_cap - sector_used_pct
            
            constraint_detail["sector_used_pct"] = round(sector_used_pct, 4)
            constraint_detail["sector_remaining"] = round(sector_remaining, 4)
            
            if adjusted_pct > sector_remaining and sector_remaining > 0:
                constraints_applied.append(
                    f"板块上限{sector_cap:.0%}裁剪: 板块已用{sector_used_pct:.1%}, 剩余{sector_remaining:.1%}, {adjusted_pct:.0%} -> {sector_remaining:.0%}"
                )
                adjusted_pct = max(sector_remaining, 0)
            elif sector_remaining <= 0:
                constraints_applied.append(f"板块上限{sector_cap:.0%}已满: 板块已用{sector_used_pct:.1%}, 不再加仓")
                adjusted_pct = max(current_pct, 0)  # 板块满, 不再加但不清仓
        
        # === 约束3: 总仓位上限 ===
        total_cap = settings.V5_TOTAL_POSITION_CAP
        all_mv_stmt = select(func.sum(UserPortfolio.market_value)).where(UserPortfolio.user_id == user_id)
        all_mv_result = await self._session.execute(all_mv_stmt)
        all_mv = float(all_mv_result.scalar() or 0)
        
        denominator = total_assets if total_assets > 0 else 1
        current_total_pct = all_mv / denominator
        remaining_total = total_cap - current_total_pct
        
        constraint_detail["single_fund_cap"] = single_cap
        constraint_detail["sector_cap"] = sector_cap
        constraint_detail["total_cap"] = total_cap
        constraint_detail["current_total_pct"] = round(current_total_pct, 4)
        constraint_detail["remaining_total"] = round(remaining_total, 4)
        
        if adjusted_pct > remaining_total and remaining_total > 0:
            constraints_applied.append(
                f"总仓位上限{total_cap:.0%}裁剪: 已用{current_total_pct:.1%}, 剩余{remaining_total:.1%}, {adjusted_pct:.0%} -> {remaining_total:.0%}"
            )
            adjusted_pct = max(remaining_total, 0)
        elif remaining_total <= 0 and adjusted_pct > current_pct:
            constraints_applied.append(f"总仓位上限{total_cap:.0%}已满: 已用{current_total_pct:.1%}, 不再加仓")
            adjusted_pct = current_pct
        
        return {
            "adjusted_pct": round(adjusted_pct, 4),
            "constraints": constraints_applied,
            "constraint_detail": constraint_detail,
        }

    def _pct_to_level(self, pct: float) -> str:
        """百分比 → 仓位等级"""
        if pct < 0.125:
            return "empty"
        if pct < 0.375:
            return "light"
        if pct < 0.625:
            return "mid"
        if pct < 0.875:
            return "heavy"
        return "full"

    def _calc_regime_adj(self, regime: str) -> float:
        """市场体制修正系数
        bull → 1.10（稍激进，加仓幅度×1.1）
        bear → 0.85（保守，调整幅度×0.85）
        extreme_volatility → 0.70（极保守，调整幅度×0.7）
        sideways → 1.00（中性）
        """
        return {
            "bull": 1.10,
            "bear": 0.85,
            "extreme_volatility": 0.70,
            "sideways": 1.00,
        }.get(regime, 1.00)

    def _signal_to_idx(self, level: str) -> int:
        """信号等级 → 列索引"""
        order = ["S+", "S", "A", "B", "C", "D", "E"]
        try:
            return order.index(level)
        except ValueError:
            return 3  # 默认 B

    async def _get_last_execute_date(
        self, user_id: str, fund_code: str,
        operation_types: list = None,
    ) -> Optional[date]:
        """获取上次执行日期
        
        V5.1: C类基金加仓0手续费，冷却期仅限减仓/赎回
        operation_types: 筛选操作类型列表，如 ["sell","decrease"]
        默认None=不限(查全部)，传列表=只查指定类型
        """
        try:
            from sqlalchemy import select
            from app.models.position_execution import PositionExecution
            stmt = (
                select(PositionExecution.execute_date)
                .where(
                    PositionExecution.user_id == user_id,
                    PositionExecution.fund_code == fund_code,
                )
                .order_by(PositionExecution.execute_date.desc())
                .limit(1)
            )
            # V5.1: C类基金加仓0手续费，冷却期仅限减仓操作
            if operation_types:
                stmt = stmt.where(PositionExecution.operation_type.in_(operation_types))
            result = await self._session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception:
            return None

    def _generate_reason(
        self,
        signal_level: str,
        confidence_stars: int,
        current_level: str,
        target_pct: float,
        cost_rejected: bool,
        frequency_blocked: bool,
    ) -> str:
        """生成建议原因文案"""
        if cost_rejected:
            return "调整幅度小于交易成本阈值（1.5%），建议暂不操作"
        if frequency_blocked:
            return "7天内已执行过仓位调整，建议等待"

        signal_labels = {
            "S+": "极度恐惧", "S": "恐惧", "A": "偏恐惧",
            "B": "中性", "C": "偏贪婪", "D": "贪婪", "E": "极度贪婪",
        }
        label = signal_labels.get(signal_level, signal_level)
        stars_str = "⭐" * confidence_stars

        return (
            f"当前信号：{label}（{signal_level}），"
            f"置信度：{stars_str}，"
            f"建议仓位从「{current_level}」调整至「{target_pct:.0%}」"
        )


# ============================================================
# 方案B: 趋势卫士
# ============================================================
async def calculate_trend_guard(
    fund_code: str,
    signal_level: str,
    fund_type: str = "unknown",
    cost_basis: float = 0.0,
    current_position: float = 0.5,
    confidence_stars: int = 3,
) -> dict:
    """
    计算趋势卫士完整数据（MA20+MACD双指标趋势判定 + 板块双轨制信号 + Gate体系）

    V5.4 缓存优先优化:
    - 先从 Redis 读 scheduler 预演 meta 缓存 → 命中则用缓存数据重构 (0ms)
    - 缓存缺失 → asyncio.to_thread(calculate_position_v5) 兜底 (不阻塞 event loop)

    Gate体系重构：
    - 持仓风控层（gate_triggered）：Gate1 > Gate2 > Gate-E
    - 建仓准入层（admission_gate）：Gate3
    """
    # 检查配置开关
    if not settings.ENABLE_TREND_GUARD:
        return {}

    # ── 缓存优先: 读 scheduler 预演 meta ──
    try:
        from datetime import date as _date, timedelta as _td
        _today = _date.today()
        for _d in (_today, _today - _td(days=1)):
            _meta_key = f"{_settings.INTRADAY_PREVIEW_CACHE_PREFIX}:{_d.isoformat()}:meta:{fund_code}"
            _meta = await cache_get(_meta_key)
            if _meta and isinstance(_meta, dict) and _meta.get("is_data_sufficient"):
                # 缓存命中 → 用缓存数据重构 trend_guard 结果 (纯数学 <1ms)
                logger.info(f"[trend_guard] 缓存命中: {fund_code}, date={_d.isoformat()}, 0ms重构")
                return _reconstruct_from_meta(_meta, signal_level, confidence_stars, current_position)
    except Exception as e:
        logger.warning(f"[trend_guard] 缓存读取异常: {fund_code}, {e}")

    # ── 缓存缺失 → asyncio.to_thread 兜底 ──
    try:
        from app.engine.trend_guard import calculate_position_v5
        result = await asyncio.to_thread(
            calculate_position_v5,
            fund_code=fund_code,
            cost_basis=cost_basis,
            current_position=current_position,
            signal_level=signal_level,
            fund_type=fund_type,
            confidence_stars=confidence_stars,
        )
        gates = result.get("gates")  # 新结构化 Gate 对象（gate_1/gate_2/gate_e/overall_status）
        return {
            "trend_signal": result.get("trend_signal", ""),
            "macd_signal": result.get("macd_signal", ""),
            "macd_detail": result.get("macd_detail", {}),             # 新增：完整 dict 详情
            "oscillation_silence": result.get("oscillation_silence", False),
            "gate_triggered": result.get("gate_triggered"),   # DEPRECATED 兼容字段
            "gates": gates,                                    # 新结构化 Gate 对象
            "gate_1": gates.get("gate_1") if isinstance(gates, dict) else None,
            "gate_2": gates.get("gate_2") if isinstance(gates, dict) else None,
            "gate_e": gates.get("gate_e") if isinstance(gates, dict) else None,
            "overall_status": gates.get("overall_status") if isinstance(gates, dict) else "normal",
            "sector_track": result.get("sector_track") or (gates.get("sector_track") if isinstance(gates, dict) else None),
            "admission_gate": result.get("admission_gate"),   # 准入层结果
            "operation_suggestion": result.get("operation_suggestion", ""),
            "trend_narrative": result.get("trend_narrative", ""),
        }
    except Exception as e:
        logger.error(f"趋势卫士调用失败: {e}")
        return {}


def _reconstruct_from_meta(
    meta: dict,
    signal_level: str,
    confidence_stars: int,
    current_position: float,
) -> dict:
    """
    从 scheduler 预演 meta 缓存重构 trend_guard 结果

    meta 包含: nav_history, ma20_trend, macd, sector_track, sector_code, regime, gate_p
    利用这些数据 + 纯数学计算(check_holding_gates/check_admission_gate) → 完整输出
    """
    from app.engine.trend_guard import (
        check_holding_gates, check_admission_gate,
        _generate_operation_suggestion, _generate_trend_narrative,
        _check_oscillation,
    )

    nav_history = meta.get("nav_history", [])
    ma20_trend = meta.get("ma20_trend", "震荡")
    macd_result = meta.get("macd")
    sector_track = meta.get("sector_track")
    gate_p_from_cache = meta.get("gate_p")

    # 1. trend/macd 信号 (直接从缓存取)
    trend_signal = ma20_trend
    macd_signal = macd_result.get("signal", "中性") if isinstance(macd_result, dict) else "中性"
    oscillation_silence = _check_oscillation(nav_history) if nav_history else False

    # 2. Gate体系: 用缓存的 nav_history + gate_p 重新计算 (纯数学 <1ms)
    # 注意: check_holding_gates 内部会调 check_panic_gate (fetch 沪深300),
    # 但 meta 缓存已存 gate_p → 需绕过, 直接传入 gate_p_from_cache
    if nav_history and gate_p_from_cache:
        # 方案: 手动重构 Gate 体系，用缓存的 gate_p 替代 check_panic_gate
        from app.engine.trend_guard import (
            _calculate_drawdown, _get_price,
            GATE1_DRAWDOWN_THRESHOLD, GATE2_DRAWDOWN_THRESHOLD,
            DRAWDOWN_WINDOW,
        )

        # -- drawdown 计算 (纯数学) --
        drawdown = _calculate_drawdown(nav_history, DRAWDOWN_WINDOW)

        # -- 价格计算 (纯数学) --
        prices = [_get_price(d) for d in nav_history]
        current_price = prices[-1] if prices else 0.0
        window_prices = prices[-DRAWDOWN_WINDOW:] if len(prices) >= DRAWDOWN_WINDOW else prices
        peak_price = max(window_prices) if window_prices else current_price
        ma20_prices = prices[-20:] if len(prices) >= 20 else prices
        ma20_price = sum(ma20_prices) / len(ma20_prices) if ma20_prices else 0.0

        # -- Gate1 (纯数学) --
        gate1_trigger_price = peak_price * (1 - GATE1_DRAWDOWN_THRESHOLD) if peak_price > 0 else None
        gate1_distance_pct = None
        if gate1_trigger_price and current_price > 0:
            gate1_distance_pct = round((GATE1_DRAWDOWN_THRESHOLD - drawdown) * 100, 2) * -1
        gate1_triggered = drawdown >= GATE1_DRAWDOWN_THRESHOLD

        # -- Gate2 (纯数学) --
        gate2_exempted = (sector_track == "contrarian")
        gate2_exempt_reason = "逆向策略逆趋势布局，MA20下降为正常特征" if gate2_exempted else None
        gate2_trigger_price = ma20_price if ma20_price > 0 else None
        gate2_distance_pct = None
        if gate2_trigger_price and current_price > 0:
            gate2_distance_pct = round((current_price - gate2_trigger_price) / gate2_trigger_price * 100, 2)
        gate2_triggered = False
        if not gate2_exempted:
            if ma20_trend == "下降" and drawdown >= GATE2_DRAWDOWN_THRESHOLD:
                gate2_triggered = True

        # -- Gate-E (纯判断) --
        gate_e_triggered = (signal_level == "E")

        # -- Gate-P (用缓存!) --
        gate_p_triggered = gate_p_from_cache.get("triggered", False) if isinstance(gate_p_from_cache, dict) else False

        # -- overall_status --
        if gate_p_triggered:
            overall_status = "panic"
        elif gate1_triggered or gate2_triggered:
            overall_status = "stop_loss"
        elif gate_e_triggered:
            overall_status = "warning"
        elif gate2_distance_pct is not None and gate2_distance_pct <= 3.0:
            overall_status = "warning"
        else:
            overall_status = "normal"

        # -- 构建结构化 Gate 对象 --
        gate1_obj = {
            "triggered": gate1_triggered,
            "action": "clear" if gate1_triggered else "hold",
            "label": "极端回撤（保命线）",
            "trigger_price": round(gate1_trigger_price, 4) if gate1_trigger_price else None,
            "current_distance_pct": gate1_distance_pct,
            "drawdown": round(drawdown, 4),
            "description": f"阶段回撤 >= {GATE1_DRAWDOWN_THRESHOLD*100:.0f}%",
            "reason": (
                f"极端回撤{drawdown*100:.1f}%>={GATE1_DRAWDOWN_THRESHOLD*100:.0f}%，无条件清仓"
                if gate1_triggered else ""
            ),
        }
        gate2_obj = {
            "triggered": gate2_triggered,
            "action": "clear" if gate2_triggered else "hold",
            "label": "趋势破位（离场线）",
            "trigger_price": round(gate2_trigger_price, 4) if gate2_trigger_price else None,
            "current_distance_pct": gate2_distance_pct,
            "drawdown": round(drawdown, 4),
            "description": f"跌破MA20 + 回撤 >= {GATE2_DRAWDOWN_THRESHOLD*100:.0f}%",
            "exempted": gate2_exempted,
            "exempt_reason": gate2_exempt_reason,
            "reason": (
                f"跌破MA20且回撤{drawdown*100:.1f}%>={GATE2_DRAWDOWN_THRESHOLD*100:.0f}%，趋势破位清仓"
                if gate2_triggered else (
                    "逆向轨道豁免趋势破位检测" if gate2_exempted else ""
                )
            ),
        }
        gate_e_obj = {
            "triggered": gate_e_triggered,
            "action": "hold",
            "label": "情绪过热（过热预警）",
            "trigger_price": None,
            "description": "信号等级达到 E（极度贪婪）",
            "reason": "进入极度贪婪区间，紧盯趋势破位信号" if gate_e_triggered else "",
        }

        gates = {
            "gate_p": gate_p_from_cache,
            "gate_1": gate1_obj,
            "gate_2": gate2_obj,
            "gate_e": gate_e_obj,
            "overall_status": overall_status,
            "sector_track": sector_track,
        }

        # DEPRECATED 兼容字段
        gate_triggered_compat = None
        if gate1_triggered:
            gate_triggered_compat = {"gate": "gate-1", "action": "clear", "adjusted_pct": 0.0,
                                     "reason": gate1_obj["reason"], "drawdown": drawdown}
        elif gate2_triggered:
            gate_triggered_compat = {"gate": "gate-2", "action": "clear", "adjusted_pct": 0.0,
                                     "reason": gate2_obj["reason"], "drawdown": drawdown}
        elif gate_e_triggered:
            gate_triggered_compat = {"gate": "gate-e", "action": "hold", "adjusted_pct": current_position,
                                     "reason": gate_e_obj["reason"]}
    else:
        # nav_history 或 gate_p 缺失 → 用空结构
        from app.engine.trend_guard import _build_gate_structure
        gates = _build_gate_structure(sector_track=sector_track)
        gate_triggered_compat = None

    # 3. 准入层 (纯判断, 不需要外部数据)
    gate2_triggered = gates.get("gate_2", {}).get("triggered", False) if isinstance(gates, dict) else False
    admission_gate = check_admission_gate(
        signal_level=signal_level,
        sector_track=sector_track,
        confidence=confidence_stars,
        gate2_triggered=gate2_triggered,
        fund_code=meta.get("fund_code", ""),
    )

    # 4. 操作建议 + 趋势叙事 (纯文本生成)
    operation_suggestion = _generate_operation_suggestion(
        trend_signal, macd_signal, oscillation_silence, gates,
        sector_track=sector_track,
    )
    trend_narrative = _generate_trend_narrative(
        trend_signal, macd_signal, oscillation_silence, gates, nav_history,
        sector_track=sector_track,
    )

    return {
        "trend_signal": trend_signal,
        "macd_signal": macd_signal,
        "macd_detail": macd_result if isinstance(macd_result, dict) else {"signal": macd_signal, "reason": "from_cache"},
        "oscillation_silence": oscillation_silence,
        "gate_triggered": gate_triggered_compat,
        "gates": gates,
        "gate_1": gates.get("gate_1") if isinstance(gates, dict) else None,
        "gate_2": gates.get("gate_2") if isinstance(gates, dict) else None,
        "gate_e": gates.get("gate_e") if isinstance(gates, dict) else None,
        "overall_status": gates.get("overall_status") if isinstance(gates, dict) else "normal",
        "sector_track": sector_track or (gates.get("sector_track") if isinstance(gates, dict) else None),
        "admission_gate": admission_gate,
        "operation_suggestion": operation_suggestion,
        "trend_narrative": trend_narrative,
    }


# 导出函数
__all__ = ["PositionEngineV5", "calculate_trend_guard", "_reconstruct_from_meta"]
