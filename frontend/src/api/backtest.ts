/**
 * backtest API 层 V5
 */
import client from './client';
import type { ApiResponse } from '../types';

/** 运行回测 */
export async function runBacktestV5(params: {
  index_code: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  signal_boundaries?: number[];
  factor_weights?: Record<string, number>;
  sigmoid_params?: Record<string, { c: number; k: number }>;
  position_matrix?: number[][];
  risk_params?: { cost_threshold: number; frequency_limit_days: number; max_single_adjustment: number };
}): Promise<{
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  win_rate: number;
  sharpe_ratio: number;
  benchmark_return: number;
  equity_curve: { date: string; value: number }[];
  trades: { date: string; type: string; price: number; amount: number; reason: string }[];
}> {
  const res = await client.post<ApiResponse<any>>('/api/v5/backtest/run', params);
  return res.data.data;
}

/** 获取回测历史列表 */
export async function fetchBacktestHistoryV5(
  page?: number;
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
