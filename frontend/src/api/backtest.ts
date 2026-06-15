/**
 * backtest API 层 V5 — 支持5类参数
 */
import client from './client';
import type { ApiResponse } from '../types';

/* ============================================================
   类型定义 — 5类参数
   ============================================================ */

/** Category 3: 行动映射规则 */
export interface ActionRule {
  type: 'buy' | 'sell_half' | 'sell_all' | 'hold';
  mult: number;
  label: string;
}

/** 5类模型参数 */
export interface ModelParams {
  // Category 1: 信号映射
  signal_boundaries: number[];        // 6个边界值
  signal_lag_days: number;            // 信号滞后天数

  // Category 2: 因子权重
  factor_weights: Record<string, number>;    // 因子名→权重(0-0.5)
  factor_enabled: Record<string, boolean>;   // 因子名→开关

  // Category 3: 行动映射
  action_mapping: Record<string, ActionRule>; // 信号等级→行动规则

  // Category 4: 因子引擎
  quantile_window: number;            // 分位数窗口
  sigmoid_k: number;                  // Sigmoid 陡峭度
  composite_method: string;           // 聚合方式
  neutral_score: number;              // 中性分数

  // Category 5: 仓位风控
  max_position: number;               // 最大仓位
  min_position: number;               // 最小仓位
  stop_loss: number;                  // 止损线
  stop_loss_threshold: number;         // 止损触发阈值倍数
  stop_loss_reduce_pct: number;       // 止损减仓比例%
  take_profit: number;                // 止盈线
  take_profit_drawdown: number;       // 止盈回撤触发
  overheat_days: number;              // 过热连续天数
  overheat_factor: number;            // 过热减仓系数
  pullback_lower: number;             // 回调加仓下限
  pullback_buy_mult: number;          // 回调加仓倍数
  position_dev_lower: number;         // 偏离加仓下限
  position_dev_buy_mult: number;       // 偏离加仓倍数
  base_buy_amount: number;             // 单次加仓金额
}

/** 回测结果 — 扩展版 */
export interface BacktestResultV5 {
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  win_rate: number;
  sharpe_ratio: number;
  benchmark_return: number;
  signal_accuracy?: number;           // 信号准确率
  equity_curve: { date: string; value: number; position_pct?: number; signal_level?: string }[];
  benchmark_curve?: { date: string; value: number }[];
  trades: { date: string; type: string; signal: string; price: number; amount: number; reason: string }[];
  daily_log?: DailyLogEntry[];
  risk_stats?: RiskStats;
  summary_text?: string;                // 操作汇总文字
  _data_source?: string;
  index_code?: string;
  start_date?: string;
  end_date?: string;
}

export interface DailyLogEntry {
  date: string;
  signal: string;
  nav: number;
  advice_text: string;
  position_value: number;
  reason: string;
}

export interface RiskStats {
  risk_triggers: number;
  pullback_buys: number;
  deviation_buys: number;
  stop_loss_triggers: number;
  overheat_triggers: number;
}

/* ============================================================
   API 函数
   ============================================================ */

/** 运行回测 — 5类参数版 */
export async function runBacktestV5(params: {
  index_code: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  fund_code?: string;                 // 基金代码（单基金回测时传入）
  signal_boundaries?: number[];
  signal_lag_days?: number;
  factor_weights?: Record<string, number>;
  factor_enabled?: Record<string, boolean>;
  action_mapping?: Record<string, ActionRule>;
  quantile_window?: number;
  sigmoid_k?: number;
  composite_method?: string;
  neutral_score?: number;
  risk_params?: Record<string, number>;
  // 旧参数兼容
  sigmoid_params?: Record<string, { c: number; k: number }>;
  position_matrix?: number[][];
}): Promise<BacktestResultV5> {
  const res = await client.post<ApiResponse<BacktestResultV5>>('/api/v5/backtest/run', params);
  return res.data.data;
}

/** 获取回测历史列表 */
export async function fetchBacktestHistoryV5(
  page?: number,
): Promise<{ items: unknown[] }> {
  const params: Record<string, number> = {};
  if (page) params.page = page;
  const res = await client.get<ApiResponse<any>>('/api/v5/backtest/history', { params });
  return res.data.data;
}

/** 保存回测方案 */
export async function saveBacktestStrategyV5(params: {
  name: string;
  params_json: Record<string, unknown>;
}): Promise<{ id: number; name: string }> {
  const res = await client.post<ApiResponse<any>>('/api/v5/backtest/strategy', params);
  return res.data.data;
}

/** 删除回测方案 */
export async function deleteBacktestStrategyV5(id: number): Promise<void> {
  await client.delete(`/api/v5/backtest/strategy/${id}`);
}

/** 应用回测方案（设为活跃） */
export async function activateBacktestStrategyV5(id: number): Promise<void> {
  await client.put(`/api/v5/backtest/strategy/${id}/activate`);
}
