/**
 * OpportunityRadarPanel - 机会雷达面板（基金查询页版）
 * 推荐10条，分类Tab: 全部 | 强势 | 反弹 | 稳健
 * 按有利度排序：恐惧=买入机会→排前
 * 点击条目弹出详情（由父组件控制 RightPanel）
 */
import type { SignalLevel } from '../../types';
import { ChevronRight } from 'lucide-react';
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
  composite_score?: number;
}

/** 信号等级有利度排序权重：恐惧=买入机会→排前 */
const SIGNAL_FAVOR_ORDER: Record<SignalLevel, number> = {
  'S+': 0,  // 极度恐惧 → 最有利
  'S':  1,  // 恐惧
  'A':  2,  // 偏恐惧
  'B':  3,  // 中性
  'C':  4,  // 偏贪婪
  'D':  5,  // 贪婪
  'E':  6,  // 极度贪婪 → 最不利
};

/** 根据信号等级推断分类（当 opportunity_type 不够明确时使用） */
function classifyItem(item: OpportunityItem): OpportunityType {
  if (item.opportunity_type) return item.opportunity_type;
  const favor = SIGNAL_FAVOR_ORDER[item.signal_level] ?? 3;
  if (favor <= 2) return 'strong';    // S+/S/A → 强势（恐惧区买入机会）
  if (favor >= 5) return 'rebound';   // D/E → 反弹（贪婪区超跌机会）
  return 'steady';                     // B/C → 稳健
}

const DUMMY_ITEMS: OpportunityItem[] = [
  { fund_code: '000001', fund_name: '华夏成长混合',         signal_level: 'S+', confidence_stars: 4, opportunity_type: 'strong',   opportunity_reason: '情绪极度悲观，估值处于历史低位',   strength_index: 88, composite_score: 18 },
  { fund_code: '000002', fund_name: '易方达消费行业',         signal_level: 'S',  confidence_stars: 3, opportunity_type: 'strong',   opportunity_reason: '恐惧信号强烈，市场过度恐慌',       strength_index: 82, composite_score: 25 },
  { fund_code: '000010', fund_name: '南方中证500ETF联接',   signal_level: 'S',  confidence_stars: 3, opportunity_type: 'rebound',  opportunity_reason: '超跌反弹信号，资金开始流入',       strength_index: 75, composite_score: 28 },
  { fund_code: '000003', fund_name: '天弘沪深300ETF联接',   signal_level: 'A',  confidence_stars: 3, opportunity_type: 'strong',   opportunity_reason: '情绪偏恐惧，适合定投布局',         strength_index: 70, composite_score: 32 },
  { fund_code: '000007', fund_name: '富国天惠成长混合',       signal_level: 'A',  confidence_stars: 2, opportunity_type: 'rebound',  opportunity_reason: '情绪修复中，可关注反弹机会',       strength_index: 68, composite_score: 35 },
  { fund_code: '000005', fund_name: '广发稳健增长混合',       signal_level: 'B',  confidence_stars: 2, opportunity_type: 'steady',   opportunity_reason: '情绪中性，适合持有观察',           strength_index: 55, composite_score: 48 },
  { fund_code: '000008', fund_name: '嘉实沪深300ETF联接',   signal_level: 'B',  confidence_stars: 3, opportunity_type: 'steady',   opportunity_reason: '稳健配置型，波动率较低',           strength_index: 52, composite_score: 50 },
  { fund_code: '000009', fund_name: '招商中证白酒指数',       signal_level: 'C',  confidence_stars: 2, opportunity_type: 'steady',   opportunity_reason: '情绪偏贪婪但尚可持有',             strength_index: 50, composite_score: 55 },
  { fund_code: '000004', fund_name: '汇添富价值精选混合',     signal_level: 'D',  confidence_stars: 2, opportunity_type: 'rebound',  opportunity_reason: '超跌后修复，反弹概率增大',         strength_index: 45, composite_score: 65 },
  { fund_code: '000006', fund_name: '工银瑞信核心价值混合',   signal_level: 'E',  confidence_stars: 1, opportunity_type: 'rebound',  opportunity_reason: '极度贪婪，注意回调风险',           strength_index: 40, composite_score: 78 },
];

const TYPE_LABELS: Record<OpportunityType, { label: string; color: string }> = {
  strong:  { label: '强势', color: 'text-red-500' },
  rebound: { label: '反弹', color: 'text-orange-500' },
  steady:  { label: '稳健', color: 'text-blue-500' },
};

type TabValue = '' | OpportunityType;

const TYPE_TABS: { value: TabValue; label: string }[] = [
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
  /** 按有利度排序：恐惧信号排前，同等级按 composite_score 降序 */
  const sortedItems = [...items].sort((a, b) => {
    const favDiff = SIGNAL_FAVOR_ORDER[a.signal_level] - SIGNAL_FAVOR_ORDER[b.signal_level];
    if (favDiff !== 0) return favDiff;
    return (b.composite_score ?? 0) - (a.composite_score ?? 0);
  });

  /** Tab 筛选 */
  const filtered = activeType
    ? sortedItems.filter((it) => classifyItem(it) === activeType)
    : sortedItems;

  return (
    <div className="card p-4">
      {/* 标题 + 类型筛选 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-700">
          机会雷达 <span className="text-[10px] font-normal text-gray-400">Top 10</span>
        </h3>
        <div className="flex gap-1">
          {TYPE_TABS.map((tab) => {
            const count = tab.value === ''
              ? sortedItems.length
              : sortedItems.filter((it) => classifyItem(it) === tab.value).length;
            return (
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
                <span className="ml-0.5 opacity-70">({count})</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="space-y-2 animate-pulse">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="h-12 bg-gray-100 rounded" />
          ))}
        </div>
      ) : (
        <div className="space-y-1">
          {filtered.map((item, idx) => {
            const classified = classifyItem(item);
            return (
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

                {/* 类型标签 + 分数 */}
                <div className="flex flex-col items-end shrink-0">
                  <span className={clsx('text-[10px] font-medium', TYPE_LABELS[classified].color)}>
                    {TYPE_LABELS[classified].label}
                  </span>
                  {item.composite_score !== undefined && (
                    <span className="text-[10px] text-gray-400 font-mono">
                      {item.composite_score}
                    </span>
                  )}
                </div>

                <ChevronRight className="w-3.5 h-3.5 text-gray-300 shrink-0" />
              </button>
            );
          })}

          {filtered.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-4">
              当前分类下暂无推荐
            </p>
          )}
        </div>
      )}
    </div>
  );
}
