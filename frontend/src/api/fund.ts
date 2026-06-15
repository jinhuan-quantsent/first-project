import client from './client';
import type { ApiResponse, FundSearchResult, FundDetail } from '../types';

const V5_PREFIX = '/api/v5';

// 基金搜索
export async function searchFunds(params: {
  keyword?: string;
  fund_type?: string;
  page?: number;
  page_size?: number;
}): Promise<FundSearchResult> {
  const res = await client.get<ApiResponse<FundSearchResult>>(`${V5_PREFIX}/fund/search`, { params });
  return res.data.data;
}

// 基金详情
export async function fetchFundDetail(code: string): Promise<FundDetail> {
  const res = await client.get<ApiResponse<FundDetail>>(`${V5_PREFIX}/fund/detail/${code}`);
  return res.data.data;
}
