/**
 * V5.0 板块情绪 + 机会雷达 API 服务
 */
import client from './client';
import type { ApiResponse } from '../types';
import type { SectorSentimentData, SectorRadarData } from '../types/sector';

const V5_PREFIX = '/api/v5';

/**
 * 获取板块情绪评分 (31个申万一级行业)
 *
 * 注意: 该接口需要实时计算31个板块的5因子评分，耗时约25-30秒
 */
export async function fetchSectorSentiment(
  sectorCode?: string,
): Promise<SectorSentimentData> {
  const params = sectorCode ? { sector_code: sectorCode } : {};
  const res = await client.get<ApiResponse<SectorSentimentData>>(
    `${V5_PREFIX}/sector/sentiment`,
    { params, timeout: 60000 },
  );
  if (res.data.code !== 0) {
    throw new Error(res.data.message || '板块情绪数据获取失败');
  }
  return res.data.data;
}

/**
 * 获取机会雷达 (双轨制推荐引擎)
 *
 * 返回 contrarian (逆向) + trend_follow (趋势) 双轨推荐
 */
export async function fetchSectorRadar(params?: {
  max_contrarian?: number;
  max_trend_follow?: number;
}): Promise<SectorRadarData> {
  const query = params || {};
  const res = await client.get<ApiResponse<SectorRadarData>>(
    `${V5_PREFIX}/sector/radar`,
    { params: query, timeout: 60000 },
  );
  if (res.data.code !== 0) {
    throw new Error(res.data.message || '机会雷达数据获取失败');
  }
  return res.data.data;
}
