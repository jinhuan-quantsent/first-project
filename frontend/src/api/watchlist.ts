import client from './client';
import type { ApiResponse, WatchlistItem } from '../types';

// 获取自选
export async function fetchWatchlist(): Promise<{
  items: WatchlistItem[];
  total: number;
  updated_at: string;
}> {
  const res = await client.get<ApiResponse<{
    items: WatchlistItem[];
    total: number;
    updated_at: string;
  }>>('/api/v1/watchlist');
  return res.data.data;
}

// 添加自选
export async function addWatchlistItem(item: {
  fund_code: string;
  fund_name?: string;
  notes?: string;
  alert_threshold?: number;
}): Promise<WatchlistItem> {
  const res = await client.post<ApiResponse<WatchlistItem>>('/api/v1/watchlist', item);
  return res.data.data;
}

// 删除自选
export async function deleteWatchlistItem(id: number): Promise<void> {
  await client.delete(`/api/v1/watchlist/${id}`);
}
