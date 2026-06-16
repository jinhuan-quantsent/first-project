import { TrendingUp, Shield, AlertTriangle } from 'lucide-react';
import type { BacktestResultV5 } from '../../api/backtest';
import { SIGNAL_BG } from './constants';
import { EquityChart } from './EquityChart';

/** 回测结果展示（ECharts 版） */
export function BacktestResultPanel({ result }: { result: BacktestResultV5 | null }) {
  if (!result) {
    return (
      <div className="card p-8 text-center">
        <TrendingUp className="w-8 h-8 text-gray-300 mx-auto mb-2" />
        <p className="text-gray-500 text-sm font-medium">点击「运行回测」查看结果</p>
        <p className="text-xs text-gray-300 mt-1">基于 V5.0 信号系统进行历史回测</p>
      </div>
    );
  }

  const metrics = [
    { label: '初始金额', value: '¥100,000', cls: 'text-gray-700' },
    { label: '最终金额', value: `¥${(100000 * (1 + result.total_return / 100)).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`, cls: result.total_return >= 0 ? 'text-red-500' : 'text-green-500' },
    { label: '总收益率', value: `${result.total_return.toFixed(2)}%`, cls: result.total_return >= 0 ? 'text-red-500' : 'text-green-500' },
    { label: '信号准确率', value: `${(result.signal_accuracy ?? 0).toFixed(1)}%`, cls: 'text-brand-500' },
    { label: '最大回撤', value: `${result.max_drawdown.toFixed(2)}%`, cls: 'text-green-500' },
    { label: '夏普比率', value: result.sharpe_ratio.toFixed(2), cls: result.sharpe_ratio >= 1 ? 'text-brand-500' : 'text-gray-700' },
    { label: '风控触发', value: `${result.risk_stats?.risk_triggers ?? 0}次`, cls: 'text-orange-500', icon: <Shield className="w-3 h-3" /> },
    { label: '回调加仓', value: `${(result.risk_stats?.pullback_buys ?? 0) + (result.risk_stats?.deviation_buys ?? 0)}次`, cls: 'text-cyan-500' },
  ];

  const dailyLog = result.daily_log || [];

  return (
    <div className="card p-4 space-y-4">
      <h3 className="text-sm font-bold text-gray-700">回测结果</h3>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {metrics.map(it => (
          <div key={it.label} className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-xs text-gray-400 flex items-center gap-1">{it.icon}{it.label}</p>
            <p className={`text-base font-bold ${it.cls}`}>{it.value}</p>
          </div>
        ))}
      </div>
      <div className="bg-gray-50 rounded-lg p-3">
        <p className="text-xs text-gray-400 mb-1">收益率曲线（策略 vs 基准）</p>
        <EquityChart curve={result.equity_curve} benchmarkCurve={result.benchmark_curve} />
      </div>
      {result.summary_text && (
        <div className="bg-brand-50 rounded-lg p-2.5 flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-brand-500 shrink-0" />
          <p className="text-[11px] text-brand-700 font-medium">{result.summary_text}</p>
        </div>
      )}
      {result.risk_stats && (result.risk_stats.risk_triggers > 0 || result.risk_stats.pullback_buys > 0) && (
        <div className="bg-orange-50 rounded-lg p-2.5 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-orange-500 shrink-0" />
          <p className="text-xs text-orange-700">
            风控触发 {result.risk_stats.risk_triggers}次
            （回撤加仓{result.risk_stats.drawdown_add_buys}·过热{result.risk_stats.overheat_triggers}）
            · 回调加仓{result.risk_stats.pullback_buys}·偏离加仓{result.risk_stats.deviation_buys}
          </p>
        </div>
      )}
      {dailyLog.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-gray-600 mb-1.5">每日操作日志（最近{dailyLog.length}条）</h4>
          <div className="overflow-x-auto max-h-48 overflow-y-auto border border-gray-200 rounded-lg">
            <table className="w-full text-xs text-left">
              <thead className="bg-gray-50 sticky top-0">
                <tr className="text-gray-400">
                  <th className="px-2 py-1">日期</th>
                  <th className="px-2 py-1">信号</th>
                  <th className="px-2 py-1">净值</th>
                  <th className="px-2 py-1">建议操作</th>
                  <th className="px-2 py-1">持仓市值</th>
                  <th className="px-2 py-1">原因</th>
                </tr>
              </thead>
              <tbody>
                {dailyLog.map((log, i) => (
                  <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-2 py-1 font-mono text-gray-600">{log.date}</td>
                    <td className="px-2 py-1">
                      <span className={`px-1 py-0.5 rounded text-[10px] font-bold ${SIGNAL_BG[log.signal] || ''}`}>{log.signal}</span>
                    </td>
                    <td className="px-2 py-1 font-mono text-gray-700">{log.nav.toFixed(2)}</td>
                    <td className="px-2 py-1 text-gray-700">{log.advice_text}</td>
                    <td className="px-2 py-1 font-mono text-gray-600">¥{log.position_value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</td>
                    <td className="px-2 py-1 text-gray-400 max-w-[200px] truncate">{log.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
