import client from './client';
import type { ApiResponse, PortfolioItem, PortfolioSummary, PortfolioOverlap } from '../types';

const V5 = '/api/v5';

// 获取持仓
export async function fetchPortfolio(): Promise<{
  items: PortfolioItem[];
  summary: PortfolioSummary;
  updated_at: string;
}> {
  const res = await client.get<ApiResponse<{
    items: PortfolioItem[];
    summary: PortfolioSummary;
    updated_at: string;
  }>>(`${V5}/portfolio`);
  return res.data.data;
}

// 添加持仓
export async function addPortfolioItem(item: Omit<PortfolioItem, 'id'>): Promise<PortfolioItem> {
  const res = await client.post<ApiResponse<PortfolioItem>>(`${V5}/portfolio`, item);
  return res.data.data;
}

// 更新持仓
export async function updatePortfolioItem(id: number, item: Omit<PortfolioItem, 'id'>): Promise<PortfolioItem> {
  const res = await client.put<ApiResponse<PortfolioItem>>(`${V5}/portfolio/${id}`, item);
  return res.data.data;
}

// 删除持仓
export async function deletePortfolioItem(id: number): Promise<void> {
  await client.delete(`${V5}/portfolio/${id}`);
}

// 持仓重叠分析
export async function fetchPortfolioOverlap(): Promise<PortfolioOverlap> {
  const res = await client.get<ApiResponse<PortfolioOverlap>>(`${V5}/portfolio/overlap`);
  return res.data.data;
}
