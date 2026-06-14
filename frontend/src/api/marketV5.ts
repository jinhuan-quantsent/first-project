/**
 * V5.0 市场情绪 API 服务
 * 11因子流水线 + 7级信号 + 4星置信度
 */
import client from './client';
import type { ApiResponse } from '../types';

/** V5 因子明细 */
export interface V5FactorDetail {
  factor_name: string;
  percentile: number | null;
  sigmoid_score: number;
  raw_value: number;
  label: string;
  direction: string;
  weight: number;
}

/** V5 情绪结果 */
export interface V5SentimentResult {
  index_code: string;
  index_name: string;
  composite_score: number;
  score_std: number;
  divergence_penalty: number;
  regime: string;
  signal_level: string;
  signal_jump_blocked: boolean;
  confidence_stars: number;
  confidence_detail: Record<string, number>;
  defenses_triggered: string[];
  factor_details: V5FactorDetail[];
  updated_at: string;
}

/** V5 多指数摘要 */
export interface V5MultiIndexItem {
  index_code: string;
  index_name: string;
  composite_score: number;
  signal_level: string;
  confidence_stars: number;
  regime: string;
}

/** V5 信号灯数据 */
export interface V5SignalLight {
  date: string;
  signal_level: string;
  composite_score: number;
  confidence_stars: number;
}

/** V5 仓位建议 */
export interface V5PositionAdvice {
  fund_code: string;
  current_position_pct: number;
  target_position_pct: number;
  action: 'increase' | 'hold' | 'decrease';
  signal_level: string;
  confidence_stars: number;
  matrix_result: { current: string; target: string };
  confidence_adj_factor: number;
  regime_adj_factor: number;
  cost_rejected: boolean;
  frequency_blocked: boolean;
  reason: string;
}

/** V5 因子热力图 */
export interface V5FactorHeatmap {
  index_code: string;
  composite_score: number;
  signal_level: string;
  factors: V5FactorDetail[];
  updated_at: string;
}

// ================== API 函数 ==================

const V5_PREFIX = '/api/v5';

/** 获取 V5 指数情绪（完整流水线） */
export async function fetchV5Sentiment(
  indexCode: string,
  tradeDate?: string,
): Promise<V5SentimentResult> {
  const params = tradeDate ? { trade_date: tradeDate } : {};
  const res = await client.get<ApiResponse<V5SentimentResult>>(
    `${V5_PREFIX}/market/sentiment/${indexCode}`,
    { params },
  );
  return res.data.data;
}

/** 获取 V5 多指数情绪摘要 */
export async function fetchV5MultiIndex(
  codes?: string,
): Promise<{
  indexes: V5MultiIndexItem[];
  composite: V5MultiIndexItem | null;
  updated_at: string;
}> {
  const params = codes ? { codes } : {};
  const res = await client.get<ApiResponse<{
    indexes: V5MultiIndexItem[];
    composite: V5MultiIndexItem | null;
    updated_at: string;
  }>>(`${V5_PREFIX}/market/multi-index`, { params });
  return res.data.data;
}

/** 获取 V5 信号灯数据 */
export async function fetchV5SignalLights(
  indexCode: string,
  days: number = 3,
): Promise<{
  index_code: string;
  signals: V5SignalLight[];
  updated_at: string;
}> {
  const res = await client.get<ApiResponse<{
    index_code: string;
    signals: V5SignalLight[];
    updated_at: string;
  }>>(`${V5_PREFIX}/market/signal-lights/${indexCode}`, {
    params: { days },
  });
  return res.data.data;
}

/** 获取 V5 仓位建议 */
export async function fetchV5PositionAdvice(
  fundCode: string,
  currentPositionPct: number,
): Promise<V5PositionAdvice> {
  const res = await client.post<ApiResponse<V5PositionAdvice>>(
    `${V5_PREFIX}/portfolio/position-advice`,
    { fund_code: fundCode, current_position_pct: currentPositionPct },
  );
  return res.data.data;
}

/** 执行 V5 仓位调整 */
export async function executeV5Position(params: {
  fund_code: string;
  target_position_pct: number;
  signal_level: string;
  confidence_stars: number;
}): Promise<{ execution_id: number; message: string }> {
  const res = await client.post<ApiResponse<{ execution_id: number; message: string }>>(
    `${V5_PREFIX}/portfolio/position-execute`,
    params,
  );
  return res.data.data;
}

/** 获取 V5 因子热力图 */
export async function fetchV5FactorHeatmap(
  indexCode: string = 'SH000300',
): Promise<V5FactorHeatmap> {
  const res = await client.get<ApiResponse<V5FactorHeatmap>>(
    `${V5_PREFIX}/market/factor-heatmap`,
    { params: { index_code: indexCode } },
  );
  return res.data.data;
}
