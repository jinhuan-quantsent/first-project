import { useState, useEffect } from 'react';
import { fetchSectorHeatmap } from '../../api/market';
import type { SectorHeatmapItem, GroupSummary, SignalLevel } from '../../types';
import SentimentBadge from '../common/SentimentBadge';
import LoadingSpinner from '../common/LoadingSpinner';
import { clsx } from 'clsx';

/**
 * 信号等级有利度排序权重
 * 恐惧 = 市场低位 = 买入机会 = 有利 → 排前面
 * 贪婪 = 市场高位 = 风险 = 不利 → 排后面
 */
const SIGNAL_FAVOR_ORDER: Record<SignalLevel, number> = {
  'S+': 0,  // 极度恐惧 → 最有利
  'S':  1,  // 恐惧
  'A':  2,  // 偏恐惧
  'B':  3,  // 中性
  'C':  4,  // 偏贪婪
  'D':  5,  // 贪婪
  'E':  6,  // 极度贪婪 → 最不利
};

/** 从旧版 SentimentLabel 映射到有利度排序权重 */
const LEGACY_LABEL_FAVOR_ORDER: Record<string, number> = {
  extreme_fear: 0,
  fear: 1,
  neutral: 3,
  greed: 5,
  extreme_greed: 6,
};

/** 获取任意信号标签的有利度排序值 */
function getFavorOrder(label: string): number {
  if (label in SIGNAL_FAVOR_ORDER) return SIGNAL_FAVOR_ORDER[label as SignalLevel];
  if (label in LEGACY_LABEL_FAVOR_ORDER) return LEGACY_LABEL_FAVOR_ORDER[label];
  return 3; // 默认中性
}

export default function SectorOverview() {
  const [sectors, setSectors] = useState<SectorHeatmapItem[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<'favor' | 'score' | 'return' | 'momentum'>('favor');

  useEffect(() => {
    fetchSectorHeatmap()
      .then((data) => {
        setSectors(data.sectors);
        setGroups(data.group_summary);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner text="加载板块数据..." />;

  const sorted = [...sectors].sort((a, b) => {
    if (sortBy === 'favor') {
      const favDiff = getFavorOrder(a.sentiment_label) - getFavorOrder(b.sentiment_label);
      if (favDiff !== 0) return favDiff;
      return b.sentiment_score - a.sentiment_score;
    }
    if (sortBy === 'score') return b.sentiment_score - a.sentiment_score;
    if (sortBy === 'return') return b.sector_return - a.sector_return;
    return b.momentum_5d - a.momentum_5d;
  });

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-700">板块情绪速览</h3>
        <div className="flex gap-1">
          {(['favor', 'score', 'return', 'momentum'] as const).map((key) => (
            <button
              key={key}
              onClick={() => setSortBy(key)}
              className={clsx(
                'px-2 py-0.5 text-[10px] rounded transition-colors',
                sortBy === key
                  ? 'bg-brand-500 text-white font-medium'
                  : 'text-gray-400 hover:text-gray-600'
              )}
            >
              {key === 'favor' ? '有利度' : key === 'score' ? '情绪' : key === 'return' ? '涨跌' : '动量'}
            </button>
          ))}
        </div>
      </div>

      {/* 分组摘要 */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {groups.map((g) => {
          const color = g.avg_score >= 60 ? 'text-red-500' :
            g.avg_score >= 45 ? 'text-gray-500' : 'text-green-500';
          return (
            <span key={g.group_name} className="text-[10px] px-1.5 py-0.5 bg-gray-100 rounded">
              {g.group_name}
              <span className={clsx('ml-1 font-medium', color)}>{g.avg_score.toFixed(0)}</span>
            </span>
          );
        })}
      </div>

      {/* 板块列表 */}
      <div className="space-y-1.5 max-h-[360px] overflow-y-auto">
        {sorted.map((s) => {
          const barColor = s.sentiment_score >= 60 ? 'bg-red-400' :
            s.sentiment_score >= 45 ? 'bg-gray-300' : 'bg-green-400';

          return (
            <div key={s.sector_code} className="flex items-center gap-2 py-1">
              <span className="w-14 text-xs text-gray-500 truncate" title={s.sector_name}>
                {s.sector_name}
              </span>
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={clsx('h-full rounded-full transition-all', barColor)}
                  style={{ width: `${s.sentiment_score}%` }}
                />
              </div>
              <span className="w-8 text-xs text-right font-mono text-gray-600">
                {s.sentiment_score.toFixed(0)}
              </span>
              <span className={clsx(
                'w-12 text-xs text-right',
                s.sector_return >= 0 ? 'text-red-500' : 'text-green-500'
              )}>
                {s.sector_return >= 0 ? '+' : ''}{s.sector_return.toFixed(1)}%
              </span>
              <SentimentBadge sentiment={s.sentiment_label} size="sm" variant="inline" showLabel={false} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
