/**
 * watchlist API 层 V5
 */
import client from './client';
import type { ApiResponse, WatchlistItem } from '../types';

/** 获取自选列表 */
export async function fetchWatchlistV5(): Promise<WatchlistItem[]> {
  const res = await client.get<ApiResponse<WatchlistItem[]>>('/api/v5/watchlist');
  return res.data.data;
}

/** 添加自选 */
export async function addWatchlistV5(params: {
  fund_code: string;
  notes?: string;
}): Promise<WatchlistItem> {
  const res = await client.post<ApiResponse<WatchlistItem>>('/api/v5/watchlist', params);
  return res.data.data;
}

/** 删除自选 */
export async function removeWatchlistV5(id: number): Promise<void> {
  await client.delete(`/api/v5/watchlist/${id}`);
}

/** 更新自选 */
export async function updateWatchlistV5(
  id: number,
  params: { notes?: string; alert_threshold?: number },
): Promise<WatchlistItem> {
  const res = await client.put<ApiResponse<WatchlistItem>>(`/api/v5/watchlist/${id}`, params);
  return res.data.data;
}

/** 获取自选详情（含 V5 信号） */
export async function fetchWatchlistDetailV5(
  id: number,
): Promise<{
  fund: WatchlistItem;
  signal_level: string;
  confidence_stars: number;
  sector_breakdown: { sector_name: string; weight: number; signal_level: string }[];
}> {
  const res = await client.get<ApiResponse<any>>(`/api/v5/watchlist/${id}/detail`);
  return res.data.data;
}
