/**
 * 信号验证看板 — 按信号等级统计前瞻胜率和收益
 * 展示各信号等级的实战效果验证
 */
import { useEffect, useState } from 'react';
import { fetchSignalPerformance, type ForwardAccuracy } from '../../api/marketV5';
import LoadingSpinner from '../common/LoadingSpinner';
import { clsx } from 'clsx';

interface Props {
  indexCode?: string;
  days?: number;
  forwardDays?: number;
}

const SIGNAL_ORDER = ['S+', 'S', 'A', 'B', 'C', 'D', 'E'];
const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};
const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', 'S': '恐惧', 'A': '偏恐惧', 'B': '中性',
  'C': '偏贪婪', 'D': '贪婪', 'E': '极度贪婪',
};

export default function SignalVerifyBoard({
  indexCode = 'SH000300',
  days = 60,
  forwardDays = 5,
}: Props) {
  const [totalSignals, setTotalSignals] = useState(0);
  const [distribution, setDistribution] = useState<Record<string, number>>({});
  const [accuracy, setAccuracy] = useState<Record<string, ForwardAccuracy>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSignalPerformance({ indexCode, days, forwardDays });
        if (!cancelled) {
          setTotalSignals(data.total_signals);
          setDistribution(data.signal_distribution);
          setAccuracy(data.forward_accuracy);
        }
      } catch (e: any) {
        if (!cancelled) setError(e.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [indexCode, days, forwardDays]);

  if (loading) return <LoadingSpinner size="sm" text="验证数据加载中..." />;
  if (error) return <p className="text-xs text-red-400">{error}</p>;

  const activeLevels = SIGNAL_ORDER.filter(
    (sl) => distribution[sl] || accuracy[sl]
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-xs text-gray-400">
            {days}天统计 · {forwardDays}日前瞻 · 共{totalSignals}条信号
          </span>
        </div>
      </div>

      {/* 信号分布柱状图 */}
      <div className="flex items-end gap-1.5 h-16 mb-3">
        {SIGNAL_ORDER.map((sl) => {
          const count = distribution[sl] || 0;
          const maxCount = Math.max(...Object.values(distribution), 1);
          const height = (count / maxCount) * 100;
          return (
            <div key={sl} className="flex-1 flex flex-col items-center">
              <span className="text-[9px] text-gray-400">{count}</span>
              <div
                className="w-full rounded-t"
                style={{
                  height: `${Math.max(height, 4)}%`,
                  background: SIGNAL_COLORS[sl],
                  opacity: count > 0 ? 1 : 0.2,
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="flex gap-1.5 mb-4">
        {SIGNAL_ORDER.map((sl) => (
          <div key={sl} className="flex-1 text-center">
            <span className="text-[10px] font-bold" style={{ color: SIGNAL_COLORS[sl] }}>
              {sl}
            </span>
          </div>
        ))}
      </div>

      {/* 验证结果表 */}
      {Object.keys(accuracy).length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 border-b border-gray-100">
                <th className="text-left py-1.5 font-medium">信号</th>
                <th className="text-right py-1.5 font-medium">样本数</th>
                <th className="text-right py-1.5 font-medium">胜率</th>
                <th className="text-right py-1.5 font-medium">平均收益</th>
              </tr>
            </thead>
            <tbody>
              {activeLevels.map((sl) => {
                const acc = accuracy[sl];
                if (!acc) return null;
                const winRate = acc.win_rate;
                const avgReturn = acc.avg_return;
                const isPositive = avgReturn >= 0;
                return (
                  <tr key={sl} className="border-b border-gray-50">
                    <td className="py-1.5">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="inline-block w-2 h-2 rounded-full"
                          style={{ background: SIGNAL_COLORS[sl] }}
                        />
                        <span className="font-bold" style={{ color: SIGNAL_COLORS[sl] }}>{sl}</span>
                        <span className="text-[10px] text-gray-400">{SIGNAL_LABELS[sl]}</span>
                      </div>
                    </td>
                    <td className="text-right py-1.5 text-gray-500">{acc.count}</td>
                    <td className="text-right py-1.5">
                      <span className={clsx(
                        'font-mono font-medium',
                        winRate >= 60 ? 'text-green-600' : winRate >= 40 ? 'text-gray-500' : 'text-red-500'
                      )}>
                        {winRate.toFixed(1)}%
                      </span>
                    </td>
                    <td className="text-right py-1.5">
                      <span className={clsx(
                        'font-mono font-medium',
                        isPositive ? 'text-green-600' : 'text-red-500'
                      )}>
                        {isPositive ? '+' : ''}{avgReturn.toFixed(2)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-xs text-gray-400 text-center py-4">
          暂无前瞻验证数据（需要更多历史信号积累）
        </p>
      )}
    </div>
  );
}
