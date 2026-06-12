import client from './client';
import type { ApiResponse, FundSearchResult, FundDetail } from '../types';

// 基金搜索
export async function searchFunds(params: {
  keyword?: string;
  fund_type?: string;
  page?: number;
  page_size?: number;
}): Promise<FundSearchResult> {
  const res = await client.get<ApiResponse<FundSearchResult>>('/fund/search', { params });
  return res.data.data;
}

// 基金详情
export async function fetchFundDetail(code: string): Promise<FundDetail> {
  const res = await client.get<ApiResponse<FundDetail>>(`/fund/detail/${code}`);
  return res.data.data;
}
