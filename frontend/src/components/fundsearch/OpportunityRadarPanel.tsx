/**
 * OpportunityRadarPanel - 机会雷达面板
 * 纵向排名列表，支持 strong/rebound/steady 三类筛选
 * 点击条目弹出详情（由父组件控制 RightPanel）
 */
import type { SignalLevel } from '../../types';
import { TrendingUp, TrendingDown, Minus, ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';
import SentimentBadge from '../common/SentimentBadge';

export type OpportunityType = 'strong' | 'rebound' | 'steady';

interface OpportunityItem {
  fund_code: string;
  fund_name: string;
  signal_level: SignalLevel;
  confidence_stars: 1 | 2 | 3 | 4;
  opportunity_type: OpportunityType;
  opportunity_reason: string;
  strength_index: number;
}

const DUMMY_ITEMS: OpportunityItem[] = [
  { fund_code: '000001', fund_name: '华夏成长混合',       signal_level: 'S+', confidence_stars: 4, opportunity_type: 'strong',   opportunity_reason: '情绪极度悲观，估值处于历史低位', strength_index: 88 },
  { fund_code: '000002', fund_name: '易方达消费行业',       signal_level: 'S',  confidence_stars: 3, opportunity_type: 'rebound',  opportunity_reason: '超跌反弹信号，资金开始流入',   strength_index: 75 },
  { fund_code: '000003', fund_name: '天弘沪深300ETF联接', signal_level: 'A',  confidence_stars: 3, opportunity_type: 'steady',   opportunity_reason: '情绪偏恐惧，适合定投布局',     strength_index: 62 },
  { fund_code: '000007', fund_name: '富国天惠成长混合',     signal_level: 'S',  confidence_stars: 2, opportunity_type: 'rebound',  opportunity_reason: '情绪修复中，可关注反弹机会',   strength_index: 70 },
  { fund_code: '000005', fund_name: '广发稳健增长混合',     signal_level: 'B',  confidence_stars: 2, opportunity_type: 'steady',   opportunity_reason: '情绪中性，适合持有观察',       strength_index: 55 },
];

const TYPE_LABELS: Record<OpportunityType, { label: string; color: string }> = {
  strong:  { label: '强势机会', color: 'text-red-500' },
  rebound: { label: '反弹机会', color: 'text-orange-500' },
  steady:  { label: '稳健机会', color: 'text-blue-500' },
};

const TYPE_TABS: { value: '' | OpportunityType; label: string }[] = [
  { value: '',       label: '全部' },
  { value: 'strong',  label: '强势' },
  { value: 'rebound', label: '反弹' },
  { value: 'steady',  label: '稳健' },
];

interface OpportunityRadarPanelProps {
  items?: OpportunityItem[];
  loading?: boolean;
  activeType?: string;
  onTypeChange?: (type: string) => void;
  onSelect?: (item: OpportunityItem) => void;
}

export default function OpportunityRadarPanel({
  items = DUMMY_ITEMS,
  loading = false,
  activeType = '',
  onTypeChange,
  onSelect,
}: OpportunityRadarPanelProps) {
  const filtered = activeType
    ? items.filter((it) => it.opportunity_type === activeType)
    : items;

  return (
    <div className="card p-4">
      {/* 标题 + 类型筛选 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-700">机会雷达</h3>
        <div className="flex gap-1">
          {TYPE_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => onTypeChange?.(tab.value)}
              className={clsx(
                'px-2 py-0.5 text-[10px] rounded-full border transition-colors',
                activeType === tab.value
                  ? 'bg-brand-500 text-white border-brand-500'
                  : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 bg-gray-100 rounded" />
          ))}
        </div>
      ) : (
        <div className="space-y-1">
          {filtered.map((item, idx) => (
            <button
              key={item.fund_code}
              onClick={() => onSelect?.(item)}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg
                         hover:bg-gray-50 transition-colors text-left"
            >
              {/* 排名 */}
              <span className={clsx(
                'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0',
                idx < 3 ? 'bg-brand-500 text-white' : 'bg-gray-100 text-gray-400',
              )}>
                {idx + 1}
              </span>

              {/* 信号 + 名称 */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <SentimentBadge level={item.signal_level} size="sm" />
                  <span className="text-xs font-medium text-gray-700 truncate">
                    {item.fund_name}
                  </span>
                </div>
                <p className="text-[10px] text-gray-400 truncate mt-0.5">
                  {item.opportunity_reason}
                </p>
              </div>

              {/* 类型标签 */}
              <span className={clsx('text-[10px] font-medium shrink-0', TYPE_LABELS[item.opportunity_type].color)}>
                {TYPE_LABELS[item.opportunity_type].label}
              </span>

              <ChevronRight className="w-3.5 h-3.5 text-gray-300 shrink-0" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
