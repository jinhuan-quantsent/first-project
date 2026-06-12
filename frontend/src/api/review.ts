import client from './client';
import type {
  ApiResponse,
  SignalPerformance,
  BacktestParams,
  BacktestResult,
  BacktestTrade,
  EquityCurvePoint,
} from '../types';

// 信号表现
export async function fetchSignalPerformance(
  indexCode?: string,
  days?: number
): Promise<SignalPerformance> {
  const res = await client.get<ApiResponse<SignalPerformance>>('/review/signal-performance', {
    params: { index_code: indexCode, days },
  });
  return res.data.data;
}

// 执行回测
export async function runBacktest(params: BacktestParams): Promise<{
  params: BacktestParams;
  result: BacktestResult;
  trades: BacktestTrade[];
  equity_curve: EquityCurvePoint[];
}> {
  const res = await client.post<ApiResponse<{
    params: BacktestParams;
    result: BacktestResult;
    trades: BacktestTrade[];
    equity_curve: EquityCurvePoint[];
  }>>('/review/backtest', params);
  return res.data.data;
}

// 优化报告
export async function fetchOptimizationReport(): Promise<{
  current_params: Record<string, number>;
  suggested_params: Record<string, number>;
  improvement: { expected_excess_return: number; expected_win_rate_improvement: number };
  sensitivity_analysis: { param: string; range: number[]; returns: number[] }[];
  recommendation: string;
}> {
  const res = await client.get<ApiResponse<{
    current_params: Record<string, number>;
    suggested_params: Record<string, number>;
    improvement: { expected_excess_return: number; expected_win_rate_improvement: number };
    sensitivity_analysis: { param: string; range: number[]; returns: number[] }[];
    recommendation: string;
  }>>('/review/optimization-report');
  return res.data.data;
}
