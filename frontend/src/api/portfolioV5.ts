/**
 * portfolio API 层 V5
 */
import client from './client';
import type { ApiResponse, PortfolioItem, PortfolioSummary, PositionAdviceData } from '../types';

/** 获取持仓列表 */
export async function fetchPortfolioV5(): Promise<{ items: PortfolioItem[]; summary: PortfolioSummary }> {
  const res = await client.get<ApiResponse<any>>('/api/v5/portfolio/list');
  return res.data.data;
}

/** 获取仓位建议 */
export async function fetchPositionAdviceV5(
  fundCode: string,
  currentPct: number,
): Promise<PositionAdviceData> {
  const res = await client.post<ApiResponse<any>>('/api/v5/portfolio/position-advice', {
    fund_code: fundCode,
    current_position_pct: currentPct,
  });
  return res.data.data;
}

/** 执行仓位调整 */
export async function executePositionV5(params: {
  fund_code: string;
  target_position_pct: number;
  signal_level: string;
  confidence_stars: number;
}): Promise<{ execution_id: number; message: string }> {
  const res = await client.post<ApiResponse<any>>('/api/v5/portfolio/execute', params);
  return res.data.data;
}

/** 获取历史建议 */
export async function fetchAdviceHistoryV5(
  fundCode?: string,
  page?: number,
): Promise<{ items: unknown[]; stats: Record<string, number> }> {
  const params: Record<string, string | number> = {};
  if (fundCode) params.fund_code = fundCode;
  if (page)       params.page       = page;
  const res = await client.get<ApiResponse<any>>('/api/v5/portfolio/advice-history', { params });
  return res.data.data;
}

/** 获取交易记录 */
export async function fetchTradeRecordsV5(
  fundCode?: string,
  page?: number,
): Promise<{ items: unknown[] }> {
  const params: Record<string, string | number> = {};
  if (fundCode) params.fund_code = fundCode;
  if (page)       params.page       = page;
  const res = await client.get<ApiResponse<any>>('/api/v5/portfolio/trade-records', { params });
  return res.data.data;
}
