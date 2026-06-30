/**
 * 信号表现面板 — SignalPerformancePanel
 *
 * 展示最近 N 天信号统计：
 *   - 各信号等级（S+/S/A/B/C/D/E）出现次数与占比
 *   - 极值信号次数（极端恐惧 / 极端贪婪）
 *   - 当前连续同向天数（用于防跳变判断）
 *
 * 数据来源：/api/v5/market/signal-lights/{index_code}?days=90
 */
import { useEffect, useState } from 'react';
import { fetchV5SignalLights, type V5SignalLight } from '../../api/marketV5';
import LoadingSpinner from '../common/LoadingSpinner';

interface Props {
  indexCode?: string;
  days?: number;
}

const SIGNAL_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  'S+': { label: '极度贪婪', color: 'text-red-700', bg: 'bg-red-100' },
  'S':  { label: '贪婪',     color: 'text-red-600', bg: 'bg-red-50' },
  'A':  { label: '偏贪婪',   color: 'text-orange-600', bg: 'bg-orange-50' },
  'B':  { label: '中性',     color: 'text-gray-600', bg: 'bg-gray-50' },
  'C':  { label: '偏恐惧',   color: 'text-blue-600', bg: 'bg-blue-50' },
  'D':  { label: '恐惧',     color: 'text-blue-700', bg: 'bg-blue-50' },
  'E':  { label: '极度恐惧', color: 'text-indigo-700', bg: 'bg-indigo-50' },
};

export default function SignalPerformancePanel({ indexCode = 'SH000300', days = 90 }: Props) {
  const [signals, setSignals] = useState<V5SignalLight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchV5SignalLights(indexCode, days);
        if (!cancelled) setSignals(data.signals);
      } catch (e: any) {
        if (!cancelled) setError(e.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [indexCode, days]);

  if (loading) return <LoadingSpinner />;
  if (error) return <div className="text-red-500 text-sm p-4">错误: {error}</div>;
  if (signals.length === 0) return <div className="text-gray-400 text-sm p-4 text-center">暂无数据</div>;

  const stats = calcSignalStats(signals);
  const consecutiveDays = calcConsecutiveDays(signals);

  return (
    <div className="bg-white rounded-lg border border-gray-100 p-6">
      <h3 className="text-base font-semibold text-gray-900 mb-4">信号表现（近 {days} 天）</h3>

      {/* 概览卡片 */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="text-center p-3 bg-gray-50 rounded">
          <div className="text-2xl font-semibold text-gray-900">{signals.length}</div>
          <div className="text-xs text-gray-500 mt-1">样本天数</div>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded">
          <div className="text-2xl font-semibold text-indigo-600">{consecutiveDays}</div>
          <div className="text-xs text-gray-500 mt-1">当前连续天数</div>
        </div>
        <div className="text-center p-3 bg-gray-50 rounded">
          <div className="text-2xl font-semibold text-orange-600">{stats.extreme_count}</div>
          <div className="text-xs text-gray-500 mt-1">极值信号次数</div>
        </div>
      </div>

      {/* 信号分布 */}
      <div className="space-y-2">
        {Object.entries(stats.distribution).map(([level, count]) => {
          if (count === 0) return null;
          const pct = (count / signals.length) * 100;
          const meta = SIGNAL_LABELS[level] || { label: level, color: 'text-gray-600', bg: 'bg-gray-50' };
          return (
            <div key={level} className="flex items-center gap-3">
              <div className={`w-16 text-sm font-medium ${meta.color}`}>{level}</div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-600">{meta.label}</span>
                  <span className="text-xs text-gray-500">{count} 次 · {pct.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${meta.bg.replace('50', '400').replace('100', '500')}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ===== 工具函数（纯函数，可单测）=====

export interface SignalStats {
  distribution: Record<string, number>;
  extreme_count: number;  // 极值（S+/E）次数
  most_common: string;    // 出现最多的信号
}

/**
 * 计算信号统计
 */
export function calcSignalStats(signals: V5SignalLight[]): SignalStats {
  const distribution: Record<string, number> = {
    'S+': 0, 'S': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0,
  };

  for (const s of signals) {
    if (s.signal_level in distribution) {
      distribution[s.signal_level]++;
    }
  }

  const extreme_count = distribution['S+'] + distribution['E'];
  const most_common = Object.entries(distribution)
    .sort(([, a], [, b]) => b - a)[0]?.[0] || 'B';

  return { distribution, extreme_count, most_common };
}

/**
 * 计算当前连续同向天数（从最新信号往前数）
 */
export function calcConsecutiveDays(signals: V5SignalLight[]): number {
  if (signals.length === 0) return 0;
  const sorted = [...signals].sort((a, b) => b.date.localeCompare(a.date));
  const latest = sorted[0].signal_level;
  let count = 0;
  for (const s of sorted) {
    if (s.signal_level === latest) count++;
    else break;
  }
  return count;
}
