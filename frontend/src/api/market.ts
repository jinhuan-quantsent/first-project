import client from './client';
import type {
  ApiResponse,
  MarketSnapshot,
  IndexDetail,
  MultiIndexData,
  CompositeSentiment,
  SectorData,
  RecommendationData,
  SectorHeatmapItem,
  GroupSummary,
  AbnormalItem,
  TrendSummary,
} from '../types';

// 多指数情绪
export async function fetchMultiIndex(codes?: string): Promise<{
  indexes: MultiIndexData[];
  composite: CompositeSentiment;
  updated_at: string;
}> {
  const params = codes ? { codes } : {};
  const res = await client.get<ApiResponse<{
    indexes: MultiIndexData[];
    composite: CompositeSentiment;
    updated_at: string;
  }>>('/api/v1/market/multi-index', { params });
  return res.data.data;
}

// 单指数详情
export async function fetchIndexDetail(code: string): Promise<IndexDetail> {
  const res = await client.get<ApiResponse<IndexDetail>>(`/api/v1/market/index/${code}`);
  return res.data.data;
}

// 市场快照
export async function fetchMarketSnapshot(): Promise<MarketSnapshot> {
  const res = await client.get<ApiResponse<MarketSnapshot>>('/api/v1/market/snapshot');
  return res.data.data;
}

// 板块详情
export async function fetchSectorDetail(name: string): Promise<SectorData> {
  const res = await client.get<ApiResponse<SectorData>>(`/api/v1/market/sector/${encodeURIComponent(name)}`);
  return res.data.data;
}

// 机会推荐
export async function fetchRecommendations(): Promise<RecommendationData> {
  const res = await client.get<ApiResponse<RecommendationData>>('/api/v1/market/recommendations');
  return res.data.data;
}

// 板块热力图
export async function fetchSectorHeatmap(): Promise<{
  sectors: SectorHeatmapItem[];
  group_summary: GroupSummary[];
}> {
  const res = await client.get<ApiResponse<{
    sectors: SectorHeatmapItem[];
    group_summary: GroupSummary[];
  }>>('/api/v1/market/sector-heatmap');
  return res.data.data;
}

// 异常检测
export async function fetchAbnormalCheck(): Promise<{
  has_abnormal: boolean;
  abnormal_count: number;
  items: AbnormalItem[];
}> {
  const res = await client.get<ApiResponse<{
    has_abnormal: boolean;
    abnormal_count: number;
    items: AbnormalItem[];
  }>>('/api/v1/market/abnormal-check');
  return res.data.data;
}

// 趋势摘要
export async function fetchTrendSummary(): Promise<TrendSummary> {
  const res = await client.get<ApiResponse<TrendSummary>>('/api/v1/market/trend-summary');
  return res.data.data;
}
