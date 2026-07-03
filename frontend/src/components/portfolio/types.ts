/**
 * PositionDetailPanel 共享类型定义
 * V5.1: 结构化 Gate 数据 + 轨道标签 + 信号切换
 */
import type { SignalLevel } from '../../types';

export interface PositionDetailData {
  fundCode: string;
  fundName: string;
  marketValue: number;
  dailyReturn: number;
  holdingReturn: number;
  holdingReturnRate: number;
  signalLevel: SignalLevel;
  confidenceStars: number;
  signalReason: string;

  /** 合规星级 */
  complianceStars: number;
  complianceDirection: 'new' | 'recent_close';
  operationTag: '加仓' | '减仓' | '持有' | '买入';
  recommendationReason: string;
  updateNote: string;

  /** 绩效记录 */
  winRate: number;
  winRateDetail: string;
  performanceRecords: {
    date: string;
    signal: string;
    operation: string;
    position?: string;
    isExecuted?: boolean;
    correctUp: boolean;
    correctDown: boolean;
    returnPct: number;
    reason: string;
  }[];

  /** 交易记录 */
  tradeRecords: {
    date: string;
    type: string;
    amount: number;
    nav: number;
    fee: number;
  }[];

  /** 净值走势 */
  navHistory: { date: string; nav: number; daily_return?: number }[];

  /** 趋势解读 */
  trendText?: string;
  marketStatus?: string;

  /** 后端决策结果 */
  action?: 'hold' | 'increase' | 'decrease' | null;
  reason?: string;
  targetPositionPct?: number;
  currentPositionPct?: number;
  totalValue?: number;
  cashAmount?: number;
  totalAssets?: number;
  trendGuardText?: string;

  /** V5.1 新增: 分母类型 + 金额 + 约束 */
  suggestedTargetPct?: number;
  suggestedBuyAmount?: number;
  suggestedSellAmount?: number;
  denominatorType?: string;
  cashWarning?: string | null;
  portfolioConstraints?: string[];
  constraintDetail?: {
    single_fund_cap: number;
    sector_cap: number;
    sector_code: string | null;
    total_cap: number;
    current_total_pct: number;
    sector_used_pct?: number;
    sector_remaining?: number;
    remaining_total?: number;
  };

  /** 趋势卫士完整结构化数据 */
  trendGuard?: {
    trend_signal: string;
    macd_signal: string;
    macd_detail?: {
      signal: string;
      strength: string;
      trend: string;
      days: number;
      last_cross_type: string | null;   // "gold" / "death" / null
      last_cross_days: number | null;   // 距今天数
      histogram: number;
      reason: string | null;            // null 或 "data_short"
    };
    oscillation_silence: boolean;
    gate_triggered: { gate: string; reason: string; threshold?: number } | null;  // DEPRECATED: 请改用 gates
    gates?: {
      gate_1?: { triggered: boolean; trigger_price?: number | null; current_distance_pct?: number; drawdown?: number; label?: string; description?: string; reason?: string; action?: string };
      gate_2?: { triggered: boolean; trigger_price?: number | null; current_distance_pct?: number; exempted?: boolean; exempt_reason?: string | null; label?: string; description?: string; reason?: string; action?: string };
      gate_e?: { triggered: boolean; trigger_price?: number | null; label?: string; description?: string; reason?: string; action?: string };
      overall_status?: string;
      sector_track?: string | null;
    };
    sector_track?: string | null;
    operation_suggestion: string;
    trend_narrative: string;
  };

  /** 重仓股 */
  topHoldings: {
    name: string;
    pct: number;
    description: string;
  }[];

  /** 基础评级 */
  morningStarRating: number;
  ratingDetails: string[];

  /** 今日评估 */
  todayEvaluation: string;
  shortTerm: { label: string; reason: string };
  midTerm: { label: string; reason: string };
  longTerm: { label: string; reason: string };
}

export interface PositionDetailPanelProps {
  data: PositionDetailData;
  onCollapse: () => void;
  onExecute?: () => Promise<void>;
  onDelete?: () => void;
  onIncrease?: (amount: number, date: string) => Promise<void>;
  onDecrease?: (amount: number, date: string) => Promise<void>;
  /** 信号当日切换标志 */
  signalSwitched?: boolean;
  /** 轨道类型 */
  trackType?: string | null;
}

/** Gate 结构化数据类型（从 trendGuard.gates 提取） */
export interface GateStructure {
  gate_1?: { triggered: boolean; trigger_price?: number | null; current_distance_pct?: number; drawdown?: number; label?: string; description?: string; reason?: string; action?: string };
  gate_2?: { triggered: boolean; trigger_price?: number | null; current_distance_pct?: number; exempted?: boolean; exempt_reason?: string | null; label?: string; description?: string; reason?: string; action?: string };
  gate_e?: { triggered: boolean; trigger_price?: number | null; label?: string; description?: string; reason?: string; action?: string };
  overall_status?: string;
  sector_track?: string | null;
}

/** overall_status 显示配置 */
export const STATUS_CONFIG: Record<string, { color: string; bg: string; border: string; label: string; icon: string }> = {
  'stop_loss': { color: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', label: '⚠ 止损线生效', icon: '🔴' },
  'warning':   { color: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', label: '⚡ 风险预警', icon: '🟡' },
  'normal':    { color: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', label: '✓ 风控正常', icon: '🟢' },
};

/** 轨道标签配置 */
export const TRACK_BADGE: Record<string, { label: string; color: string; bg: string }> = {
  'contrarian':  { label: '逆向', color: 'text-amber-700', bg: 'bg-amber-50' },
  'trend_follow':{ label: '趋势', color: 'text-teal-700', bg: 'bg-teal-50' },
  'excluded':    { label: '排除', color: 'text-red-700', bg: 'bg-red-50' },
};

/** 从 gates 结构提取 overall_status（带 fallback 推算） */
export function getOverallStatus(gates?: GateStructure): string {
  if (gates?.overall_status) return gates.overall_status;
  if (gates?.gate_1?.triggered || (gates?.gate_2?.triggered && !gates?.gate_2?.exempted)) return 'stop_loss';
  if (gates?.gate_e?.triggered) return 'warning';
  return 'normal';
}
