/**
 * fundSearchV5 API 层
 * 基金搜索 V5 专属 API 调用（已有 fund.ts 的补充）
 */
import client from './client';
import type { ApiResponse, FundSearchResult } from '../types';

const V5_PREFIX = '/api/v5';

/**
 * V5 基金搜索（支持更丰富过滤）
 * GET /api/v5/fund/search
 */
export async function searchFundsV5(params: {
  keyword?: string;
  fund_type?: string;
  sector?: string;
  page?: number;
  page_size?: number;
}): Promise<FundSearchResult> {
  const res = await client.get<ApiResponse<FundSearchResult>>(
    `${V5_PREFIX}/fund/search`,
    { params },
  );
  return res.data.data;
}

/**
 * V5 基金详情（含 V5 信号/置信度/板块/重仓股）
 * GET /api/v5/fund/detail
 */
export async function fetchFundDetailV5(
  fundCode: string,
): Promise<{
  fund: FundSearchItem;
  signal_level: string;
  confidence_stars: number;
  sector_breakdown: { sector_name: string; weight: number; signal_level: string }[];
  top_holdings: { stock_name: string; weight: number }[];
}> {
  const res = await client.get<ApiResponse<any>>(
    `${V5_PREFIX}/fund/detail`,
    { params: { fund_code: fundCode } },
  );
  return res.data.data;
}

/**
 * V5 板块分析（单只基金）
 * GET /api/v5/fund/sectors
 */
export async function fetchFundSectorsV5(
  fundCode: string,
): Promise<
  { sector_name: string; weight: number; signal_level: string }[]
> {
  const res = await client.get<ApiResponse<any>>(
    `${V5_PREFIX}/fund/sectors`,
    { params: { fund_code: fundCode } },
  );
  return res.data.data;
}
