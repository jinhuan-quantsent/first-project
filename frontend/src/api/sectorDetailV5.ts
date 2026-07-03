/**
 * V5.0 板块详情 + 建仓评级 API 服务
 *
 * 对接后端端点:
 *   GET /api/v5/sector/position-rating              — 全部板块建仓评级
 *   GET /api/v5/sector/position-rating/{code}       — 单板块评级详情
 *   GET /api/v5/sector/position-rating/{code}/funds — 板块关联基金
 */
import client from './client';
import type { ApiResponse } from '../types';
import type {
  PositionRatingItem,
  SectorFund,
  PositionRating,
  TrackType,
} from '../types/positionRating';

const V5_PREFIX = '/api/v5';

// ============================================================
// API 函数
// ============================================================

/**
 * 获取单个板块的建仓评级详情（含基金列表）
 *
 * GET /api/v5/sector/position-rating/{sector_code}
 */
export async function fetchSectorDetail(sectorCode: string): Promise<PositionRatingItem> {
  const res = await client.get<ApiResponse<PositionRatingItem>>(
    `${V5_PREFIX}/sector/position-rating/${sectorCode}`,
    { timeout: 60000 },
  );
  if (res.data.code !== 0) {
    throw new Error(res.data.message || '板块评级详情获取失败');
  }
  return res.data.data;
}

/**
 * 获取板块关联基金列表
 *
 * GET /api/v5/sector/position-rating/{sector_code}/funds
 */
export async function fetchSectorFunds(sectorCode: string): Promise<SectorFund[]> {
  const res = await client.get<ApiResponse<{ sector_code: string; funds: SectorFund[]; total: number }>>(
    `${V5_PREFIX}/sector/position-rating/${sectorCode}/funds`,
    { timeout: 60000 },
  );
  if (res.data.code !== 0) {
    throw new Error(res.data.message || '板块基金获取失败');
  }
  return res.data.data.funds;
}

/**
 * 获取所有板块的建仓评级摘要（简化版，用于雷达面板）
 *
 * GET /api/v5/sector/position-rating
 * 将返回的 sectors 数组转为 Record<sector_code, { rating, type, reason }> 格式
 */
export async function fetchSectorRatings(): Promise<
  Record<string, { rating: PositionRating; type: string; reason: string }>
> {
  const res = await client.get<
    ApiResponse<{
      sectors: PositionRatingItem[];
      summary: Record<string, unknown>;
      elapsed_seconds: number;
    }>
  >(`${V5_PREFIX}/sector/position-rating`, { timeout: 60000 });

  if (res.data.code !== 0) {
    throw new Error(res.data.message || '板块评级摘要获取失败');
  }

  const result: Record<string, { rating: PositionRating; type: string; reason: string }> = {};
  for (const s of res.data.data.sectors) {
    result[s.sector_code] = {
      rating: s.rating,
      type: s.track,
      reason: s.reason,
    };
  }
  return result;
}

/**
 * 获取所有板块的完整建仓评级数据（用于自选页Tab裁决）
 *
 * GET /api/v5/sector/position-rating
 * 返回完整 PositionRatingItem（含信号/置信度/评分/基金列表）
 */
export async function fetchSectorRatingsFull(): Promise<Record<string, PositionRatingItem>> {
  const res = await client.get<
    ApiResponse<{
      sectors: PositionRatingItem[];
      summary: Record<string, unknown>;
      elapsed_seconds: number;
    }>
  >(`${V5_PREFIX}/sector/position-rating`, { timeout: 60000 });

  if (res.data.code !== 0) {
    throw new Error(res.data.message || '板块评级数据获取失败');
  }

  const result: Record<string, PositionRatingItem> = {};
  for (const s of res.data.data.sectors) {
    result[s.sector_code] = s;
  }
  return result;
}
