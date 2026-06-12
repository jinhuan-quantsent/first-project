import { useState, useEffect } from 'react';
import { fetchRecommendations } from '../../api/market';
import type { OpportunityItem } from '../../types';
import LoadingSpinner from '../common/LoadingSpinner';
import SentimentBadge from '../common/SentimentBadge';
import { clsx } from 'clsx';
import { Zap, RefreshCw, Shield } from 'lucide-react';

const TYPE_ICONS = {
  strong: Zap,
  rebound: RefreshCw,
  steady: Shield,
};

const TYPE_LABELS = {
  strong: '强势',
  rebound: '超跌反弹',
  steady: '稳健',
};

const TYPE_COLORS = {
  strong: 'text-red-500 bg-red-50 border-red-200',
  rebound: 'text-green-500 bg-green-50 border-green-200',
  steady: 'text-blue-500 bg-blue-50 border-blue-200',
};

export default function OpportunityRadar() {
  const [strong, setStrong] = useState<OpportunityItem[]>([]);
  const [rebound, setRebound] = useState<OpportunityItem[]>([]);
  const [steady, setSteady] = useState<OpportunityItem[]>([]);
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'strong' | 'rebound' | 'steady'>('strong');

  useEffect(() => {
    fetchRecommendations()
      .then((data) => {
        setStrong(data.strong_sectors);
        setRebound(data.rebound_opportunities);
        setSteady(data.steady_choices);
        setSummary(data.summary);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner text="加载机会雷达..." />;

  const currentList = activeTab === 'strong' ? strong : activeTab === 'rebound' ? rebound : steady;

  return (
    <div className="card p-4">
      <h3 className="text-sm font-bold text-gray-700 mb-3">机会雷达</h3>

      {/* 选项卡 */}
      <div className="flex gap-1 mb-3">
        {(['strong', 'rebound', 'steady'] as const).map((tab) => {
          const count = tab === 'strong' ? strong.length : tab === 'rebound' ? rebound.length : steady.length;
          const Icon = TYPE_ICONS[tab];
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                'flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs transition-colors',
                activeTab === tab
                  ? 'bg-gray-100 text-gray-800 font-medium'
                  : 'text-gray-400 hover:text-gray-600'
              )}
            >
              <Icon className="w-3 h-3" />
              {TYPE_LABELS[tab]}
              <span className="text-[10px]">({count})</span>
            </button>
          );
        })}
      </div>

      {/* 机会列表 */}
      <div className="space-y-2 max-h-[320px] overflow-y-auto">
        {currentList.map((item) => {
          const typeColor = TYPE_COLORS[item.opportunity_type];

          return (
            <div
              key={item.sector_code}
              className={clsx('p-3 rounded-lg border', typeColor)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-gray-700">{item.sector_name}</span>
                <SentimentBadge sentiment={item.sentiment_label} size="sm" variant="inline" />
              </div>

              <div className="flex items-center gap-3 text-[10px] text-gray-500 mb-1">
                <span>情绪: {item.sentiment_score.toFixed(0)}</span>
                <span className={item.momentum_5d >= 0 ? 'text-red-500' : 'text-green-500'}>
                  5日动量: {item.momentum_5d >= 0 ? '+' : ''}{item.momentum_5d.toFixed(1)}%
                </span>
                <span>强度: {item.strength_index.toFixed(0)}</span>
              </div>

              <p className="text-[10px] text-gray-400">{item.opportunity_reason}</p>
            </div>
          );
        })}

        {currentList.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">
            当前无{activeTab === 'strong' ? '强势' : activeTab === 'rebound' ? '超跌反弹' : '稳健'}机会
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
