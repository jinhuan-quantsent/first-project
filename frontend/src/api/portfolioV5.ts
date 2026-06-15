/**
 * portfolio API 层 V5
 */
import client from './client';
import type { ApiResponse, PortfolioItem, PortfolioSummary, PositionAdviceData } from '../types';

/** 获取持仓列表 */
export async function fetchPortfolioV5(): Promise<{ items: PortfolioItem[]; summary: PortfolioSummary }> {
  const res = await client.get<ApiResponse<any>>('/api/v5/portfolio');
  return res.data.data;
}

/** 添加持仓 */
export async function addPortfolioV5(params: {
  fund_code: string;
  fund_name: string;
  fund_type?: string;
  holding_shares?: number;
  cost_nav?: number;
  current_nav?: number;
  buy_date?: string;
  portfolio_tag?: string;
  weight_pct?: number;
}): Promise<PortfolioItem> {
  const res = await client.post<ApiResponse<PortfolioItem>>('/api/v5/portfolio', params);
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
  const res = await client.post<ApiResponse<any>>('/api/v5/portfolio/position-execute', params);
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
