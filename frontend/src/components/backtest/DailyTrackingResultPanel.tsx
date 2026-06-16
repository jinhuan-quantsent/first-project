import { useState } from 'react';
import { TrendingUp } from 'lucide-react';
import type { BacktestResultV5 } from '../../../api/backtest';
import { SIGNAL_BG, SIGNAL_LABELS } from './constants';
import { EquityChart } from './EquityChart';

/** 逐日追踪结果展示（ECharts 版） */
export function DailyTrackingResultPanel({ result, strategyName }: { result: BacktestResultV5; strategyName?: string }) {
  const tracking = result.daily_tracking || [];
  if (tracking.length === 0) return null;

  const fmtDate = (d: string) => {
    if (d.length === 8) return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
    return d;
  };

  const actionLabel: Record<string, string> = {
    buy: '加仓', sell: '减仓', hold: '持有', none: '—',
  };

  const [page, setPage] = useState(0);
  const PAGE_SIZE = 30;
  const totalPages = Math.ceil(tracking.length / PAGE_SIZE);
  const pagedData = tracking.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // 操作标记
  const actionMarkers = tracking
    .filter(t => t.action === 'buy' || t.action === 'sell')
    .map(t => ({ date: t.date, type: t.action as 'buy' | 'sell' }));

  const initCap = result.initial_capital || 100000;
  const finalVal = result.final_portfolio_value || 0;
  const totalRet = result.tracking_total_return_pct || 0;
  const actCount = result.tracking_action_count || 0;

  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-700">逐日追踪结果</h3>
        {strategyName && (
          <span className="flex items-center gap-1.5 text-[11px] text-brand-600 bg-brand-50 px-2 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-500" />
            因子方案: {strategyName}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="bg-gray-50 rounded-lg p-2.5">
          <p className="text-xs text-gray-400">初始资金</p>
          <p className="text-base font-bold text-gray-700">¥{initCap.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-2.5">
          <p className="text-xs text-gray-400">最终持仓</p>
          <p className={`text-base font-bold ${finalVal >= initCap ? 'text-red-500' : 'text-green-500'}`}>
            ¥{finalVal.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}
          </p>
        </div>
        <div className="bg-gray-50 rounded-lg p-2.5">
          <p className="text-xs text-gray-400">总收益率</p>
          <p className={`text-base font-bold ${totalRet >= 0 ? 'text-red-500' : 'text-green-500'}`}>
            {totalRet >= 0 ? '+' : ''}{totalRet.toFixed(2)}%
          </p>
        </div>
        <div className="bg-gray-50 rounded-lg p-2.5">
          <p className="text-xs text-gray-400">操作次数</p>
          <p className="text-base font-bold text-brand-500">{actCount}次</p>
        </div>
      </div>

      <div className="bg-gray-50 rounded-lg p-3">
        <p className="text-xs text-gray-400 mb-1">权益曲线（持仓市值 vs 买入不动基准）</p>
        <EquityChart
          curve={result.equity_curve}
          benchmarkCurve={result.benchmark_curve}
          actionMarkers={actionMarkers}
          height={280}
        />
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <h4 className="text-xs font-medium text-gray-600">每日操作日志（共{tracking.length}天）</h4>
          {totalPages > 1 && (
            <div className="flex items-center gap-1 text-[10px] text-gray-400">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-1.5 py-0.5 border rounded disabled:opacity-30 hover:bg-gray-50"
              >上一页</button>
              <span>{page + 1}/{totalPages}</span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="px-1.5 py-0.5 border rounded disabled:opacity-30 hover:bg-gray-50"
              >下一页</button>
            </div>
          )}
        </div>
        <div className="overflow-x-auto overflow-y-auto border border-gray-200 rounded-lg pb-2" style={{ maxHeight: '280px' }}>
          <table className="w-full text-xs text-left min-w-[900px]">
            <thead className="bg-gray-50 sticky top-0 z-10">
              <tr className="text-gray-400">
                <th className="px-2 py-1.5 whitespace-nowrap">日期</th>
                <th className="px-2 py-1.5 whitespace-nowrap">信号</th>
                <th className="px-2 py-1.5 whitespace-nowrap">建议</th>
                <th className="px-2 py-1.5 whitespace-nowrap">操作金额</th>
                <th className="px-2 py-1.5 whitespace-nowrap">当日净值</th>
                <th className="px-2 py-1.5 whitespace-nowrap">持仓市值</th>
                <th className="px-2 py-1.5 whitespace-nowrap">现金</th>
                <th className="px-2 py-1.5 whitespace-nowrap">持仓</th>
                <th className="px-2 py-1.5 whitespace-nowrap">日收益率</th>
                <th className="px-2 py-1.5 whitespace-nowrap min-w-[140px]">建议原因</th>
              </tr>
            </thead>
            <tbody>
              {pagedData.map((r, i) => (
                <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                  <td className="px-2 py-1 font-mono text-gray-600">{fmtDate(r.date)}</td>
                  <td className="px-2 py-1">
                    {r.signal_level ? (
                      <span className={`px-1 py-0.5 rounded text-[10px] font-bold ${SIGNAL_BG[r.signal_level] || ''}`}>
                        {r.signal_level}{r.signal_score != null ? `·${SIGNAL_LABELS[r.signal_level] || ''}` : ''}
                      </span>
                    ) : (
                      <span className="text-gray-300 text-[10px]">—(首日)</span>
                    )}
                  </td>
                  <td className="px-2 py-1">
                    <span className={`text-xs ${
                      r.action === 'buy' ? 'text-green-600 font-medium' :
                      r.action === 'sell' ? 'text-red-500 font-medium' :
                      'text-gray-400'
                    }`}>
                      {actionLabel[r.action] || r.action}
                    </span>
                  </td>
                  <td className="px-2 py-1 font-mono">
                    {r.action === 'buy' ? (
                      <span className="text-green-600">+{r.action_amount?.toLocaleString('zh-CN')}</span>
                    ) : r.action === 'sell' ? (
                      <span className="text-red-500">-{r.action_amount?.toLocaleString('zh-CN')}</span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-2 py-1 font-mono text-gray-700">{r.nav.toFixed(4)}</td>
                  <td className="px-2 py-1 font-mono text-gray-600">¥{r.portfolio_value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</td>
                  <td className="px-2 py-1 font-mono text-gray-400">¥{(r.cash ?? 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</td>
                  <td className="px-2 py-1 font-mono text-gray-600">¥{(r.position_value ?? 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</td>
                  <td className="px-2 py-1 font-mono">
                    <span className={
                      r.daily_return_pct > 0 ? 'text-red-500' :
                      r.daily_return_pct < 0 ? 'text-green-500' :
                      'text-gray-400'
                    }>
                      {r.daily_return_pct > 0 ? '+' : ''}{r.daily_return_pct.toFixed(2)}%
                    </span>
                  </td>
                  <td className="px-2 py-1 text-gray-400 max-w-[180px] truncate" title={r.reason}>{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {result.summary_text && (
        <div className="bg-brand-50 rounded-lg p-2.5 flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-brand-500 shrink-0" />
          <p className="text-[11px] text-brand-700 font-medium">{result.summary_text}</p>
        </div>
      )}
    </div>
  );
}
