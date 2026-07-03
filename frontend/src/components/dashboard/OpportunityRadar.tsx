/**
 * OpportunityRadar - 机会雷达（仪表盘版）
 * 推荐10条，分类Tab: 全部 | 强势 | 反弹 | 稳健
 * 按有利度排序：恐惧=买入机会→排前
 */
import { useState, useEffect, useMemo } from 'react';
import { fetchRecommendations } from '../../api/market';
import type { OpportunityItem, SignalLevel } from '../../types';
import LoadingSpinner from '../common/LoadingSpinner';
import SentimentBadge from '../common/SentimentBadge';
import { clsx } from 'clsx';
import { Zap, RefreshCw, Shield, LayoutGrid } from 'lucide-react';

/** Tab类型定义 */
type RadarTab = 'all' | 'strong' | 'rebound' | 'steady';

const TAB_CONFIG: { value: RadarTab; label: string; icon: typeof Zap }[] = [
  { value: 'all',     label: '全部', icon: LayoutGrid },
  { value: 'strong',  label: '强势', icon: Zap },
  { value: 'rebound', label: '反弹', icon: RefreshCw },
  { value: 'steady',  label: '稳健', icon: Shield },
];

/** 信号等级有利度排序权重 */
const SIGNAL_FAVOR_ORDER: Record<SignalLevel, number> = {
  'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5, 'E': 6,
};

/** 旧版 SentimentLabel 有利度排序 */
const LEGACY_FAVOR: Record<string, number> = {
  extreme_fear: 0, fear: 1, neutral: 3, greed: 5, extreme_greed: 6,
};

function getFavorOrder(label: string): number {
  if (label in SIGNAL_FAVOR_ORDER) return SIGNAL_FAVOR_ORDER[label as SignalLevel];
  if (label in LEGACY_FAVOR) return LEGACY_FAVOR[label];
  return 3;
}

/** 根据信号等级判断分类 */
function classifyBySignal(item: OpportunityItem): 'strong' | 'rebound' | 'steady' {
  // 先用 opportunity_type 做基础分类
  if (item.opportunity_type === 'strong') return 'strong';
  if (item.opportunity_type === 'rebound') return 'rebound';
  if (item.opportunity_type === 'steady') return 'steady';

  // 降级：用 signal_level 推断
  const label = item.sentiment_label;
  const favor = getFavorOrder(label);
  if (favor <= 2) return 'strong';     // S+/S/A → 恐惧区 = 强势买入
  if (favor >= 5) return 'rebound';    // D/E → 贪婪区 = 反弹?
  return 'steady';                      // B/C → 中性 = 稳健
}

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  strong:  { label: '强势', color: 'text-red-500' },
  rebound: { label: '反弹', color: 'text-green-500' },
  steady:  { label: '稳健', color: 'text-blue-500' },
};

const TYPE_BORDER_COLORS: Record<string, string> = {
  strong:  'border-l-red-400',
  rebound: 'border-l-green-400',
  steady:  'border-l-blue-400',
};

export default function OpportunityRadar() {
  const [allItems, setAllItems] = useState<OpportunityItem[]>([]);
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<RadarTab>('all');

  useEffect(() => {
    fetchRecommendations()
      .then((data) => {
        // 合并三类推荐为统一列表，按有利度排序，取Top10
        const merged: OpportunityItem[] = [
          ...(data.strong_sectors || []),
          ...(data.rebound_opportunities || []),
          ...(data.steady_choices || []),
        ];
        const sorted = merged.sort((a, b) => {
          const favDiff = getFavorOrder(a.sentiment_label) - getFavorOrder(b.sentiment_label);
          if (favDiff !== 0) return favDiff;
          return b.sentiment_score - a.sentiment_score;
        });
        setAllItems(sorted.slice(0, 10));
        setSummary(data.summary || '');
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  /** 根据 Tab 筛选 */
  const filteredItems = useMemo(() => {
    if (activeTab === 'all') return allItems;
    return allItems.filter((item) => classifyBySignal(item) === activeTab);
  }, [allItems, activeTab]);

  if (loading) return <LoadingSpinner text="加载机会雷达..." />;

  return (
    <div className="card p-4">
      <h3 className="text-sm font-bold text-gray-700 mb-3">机会雷达 <span className="text-[10px] font-normal text-gray-400">Top 10</span></h3>

      {/* 分类 Tab */}
      <div className="flex gap-1 mb-3">
        {TAB_CONFIG.map((tab) => {
          const count = tab.value === 'all'
            ? allItems.length
            : allItems.filter((it) => classifyBySignal(it) === tab.value).length;
          const Icon = tab.icon;
          return (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={clsx(
                'flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors',
                activeTab === tab.value
                  ? 'bg-brand-500 text-white font-medium'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
              )}
            >
              <Icon className="w-3 h-3" />
              {tab.label}
              <span className="text-[10px]">({count})</span>
            </button>
          );
        })}
      </div>

      {/* 机会列表 */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {filteredItems.map((item, idx) => {
          const classified = classifyBySignal(item);
          const borderColor = TYPE_BORDER_COLORS[classified] || 'border-l-gray-300';

          return (
            <div
              key={`${item.sector_code}-${idx}`}
              className={clsx('p-3 rounded-lg border-l-4 bg-white border border-gray-100', borderColor)}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className={clsx(
                    'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0',
                    idx < 3 ? 'bg-brand-500 text-white' : 'bg-gray-100 text-gray-400',
                  )}>
                    {idx + 1}
                  </span>
                  <span className="text-sm font-medium text-gray-700">{item.sector_name}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className={clsx('text-[10px] font-medium', TYPE_LABELS[classified]?.color)}>
                    {TYPE_LABELS[classified]?.label}
                  </span>
                  <SentimentBadge sentiment={item.sentiment_label} size="sm" variant="inline" />
                </div>
              </div>

              <div className="flex items-center gap-3 text-[10px] text-gray-500 mb-1 ml-7">
                <span>情绪: {item.sentiment_score.toFixed(0)}</span>
                <span className={item.momentum_5d >= 0 ? 'text-red-500' : 'text-green-500'}>
                  5日动量: {item.momentum_5d >= 0 ? '+' : ''}{item.momentum_5d.toFixed(1)}%
                </span>
                <span>强度: {item.strength_index.toFixed(0)}</span>
              </div>

              <p className="text-[10px] text-gray-400 ml-7">{item.opportunity_reason}</p>
            </div>
          );
        })}

        {filteredItems.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">
            当前无{activeTab === 'strong' ? '强势' : activeTab === 'rebound' ? '反弹' : activeTab === 'steady' ? '稳健' : ''}机会
          </p>
        )}
      </div>

      {/* 总结 */}
      {summary && (
        <p className="mt-3 text-[10px] text-gray-400 border-t pt-2">{summary}</p>
      )}
    </div>
  );
}
