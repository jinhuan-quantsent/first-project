/**
 * paramsMapper — 前后端参数映射工具
 * 消除 Backtest.tsx 中的手写41字段映射
 */
import type { ModelParams, ActionRule } from '../api/backtest';

/* ============================================================
   常量（从 Backtest.tsx 迁出）
   ============================================================ */

export const FACTOR_LABELS: Record<string, string> = {
  VOL: '波动率', ADR: '涨跌比', ERP: '股债比', FLOW: '北向资金',
  ETF: 'ETF资金', NHNL: '新高新低', TURN: '换手率', POS: '持仓结构',
  NBF: '融资余额', PCR: '看跌看涨比', NEWF: '新发基金',
};
export const FACTOR_NAMES = Object.keys(FACTOR_LABELS);

export const SIGNAL_LEVELS = ['S+', 'S', 'A', 'B', 'C', 'D', 'E'] as const;

export const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#7C3AED', S: '#2563EB', A: '#0891B2', B: '#65A30D',
  C: '#CA8A04', D: '#EA580C', E: '#DC2626',
};

export const SIGNAL_BG: Record<string, string> = {
  'S+': 'bg-purple-100 text-purple-700', S: 'bg-blue-100 text-blue-700',
  A: 'bg-cyan-100 text-cyan-700', B: 'bg-lime-100 text-lime-700',
  C: 'bg-yellow-100 text-yellow-700', D: 'bg-orange-100 text-orange-700',
  E: 'bg-red-100 text-red-700',
};

export const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', S: '恐惧', A: '偏恐惧', B: '中性',
  C: '偏贪婪', D: '贪婪', E: '极度贪婪',
};

export const ACTION_TYPE_OPTIONS = [
  { value: 'buy', label: '加仓' },
  { value: 'sell_half', label: '减仓' },
  { value: 'sell_all', label: '清仓' },
  { value: 'hold', label: '持有' },
] as const;

/* ============================================================
   默认参数
   ============================================================ */

export const DEFAULT_ACTION_MAPPING: Record<string, ActionRule> = {
  'S+': { type: 'buy', mult: 2.0, label: '大幅加仓' },
  S: { type: 'buy', mult: 1.5, label: '加仓' },
  A: { type: 'buy', mult: 1.0, label: '小幅加仓' },
  B: { type: 'hold', mult: 0, label: '持有' },
  C: { type: 'sell_half', mult: 0.3, label: '减仓30%' },
  D: { type: 'sell_half', mult: 0.5, label: '减仓50%' },
  E: { type: 'sell_all', mult: 1.0, label: '清仓' },
};

export const DEFAULT_MODEL_PARAMS: ModelParams = {
  signal_boundaries: [12, 25, 38, 52, 65, 80],
  signal_lag_days: 1,
  factor_weights: Object.fromEntries(FACTOR_NAMES.map(n => [n, parseFloat((1 / FACTOR_NAMES.length).toFixed(3))])),
  factor_enabled: Object.fromEntries(FACTOR_NAMES.map(n => [n, true])),
  action_mapping: { ...DEFAULT_ACTION_MAPPING },
  quantile_window: 252,
  sigmoid_k: 3.0,
  composite_method: 'weighted_sum',
  neutral_score: 50,
  max_position: 0.95,
  min_position: 0.05,
  stop_loss: -0.15,
  stop_loss_threshold: 1.0,
  stop_loss_reduce_pct: 50,
  take_profit: 0.30,
  take_profit_drawdown: 0.10,
  overheat_days: 10,
  overheat_factor: 0.7,
  pullback_lower: -0.08,
  pullback_buy_mult: 0.5,
  position_dev_lower: -0.05,
  position_dev_buy_mult: 0.3,
  base_buy_amount: 10000,
};

/* ============================================================
   映射函数
   ============================================================ */

/** ModelParams → runBacktestV5 API 请求参数 */
export function modelParamsToApiRequest(p: {
  strategy: { params: ModelParams };
  selectedFund: { code: string } | null;
  backtestParams: {
    startDate: string;
    endDate: string;
    initialCapital: number;
    strategyId: number | null;
  };
}) {
  const params = p.strategy.params;
  const isFundMode = !!p.selectedFund;

  return {
    index_code: 'SH000300',
    fund_code: isFundMode ? p.selectedFund!.code : undefined,
    daily_tracking: isFundMode,
    start_date: p.backtestParams.startDate,
    end_date: p.backtestParams.endDate,
    initial_capital: p.backtestParams.initialCapital,
    signal_boundaries: params.signal_boundaries,
    signal_lag_days: params.signal_lag_days,
    factor_weights: params.factor_weights,
    factor_enabled: params.factor_enabled,
    action_mapping: params.action_mapping,
    quantile_window: params.quantile_window,
    sigmoid_k: params.sigmoid_k,
    composite_method: params.composite_method,
    neutral_score: params.neutral_score,
    risk_params: {
      max_position: params.max_position,
      min_position: params.min_position,
      stop_loss: params.stop_loss,
      stop_loss_threshold: params.stop_loss_threshold,
      stop_loss_reduce_pct: params.stop_loss_reduce_pct,
      take_profit: params.take_profit,
      take_profit_drawdown: params.take_profit_drawdown,
      overheat_days: params.overheat_days,
      overheat_factor: params.overheat_factor,
      pullback_lower: params.pullback_lower,
      pullback_buy_mult: params.pullback_buy_mult,
      position_dev_lower: params.position_dev_lower,
      position_dev_buy_mult: params.position_dev_buy_mult,
      base_buy_amount: params.base_buy_amount,
    },
  };
}

/** 后端策略响应 → 前端 BacktestStrategy */
export function apiStrategyToLocal(s: Record<string, unknown>) {
  return {
    id: s.id as number,
    name: s.name as string,
    is_active: s.is_active as boolean,
    params: typeof s.params_json === 'string'
      ? JSON.parse(s.params_json)
      : (s.params_json as Record<string, unknown>),
  };
}
