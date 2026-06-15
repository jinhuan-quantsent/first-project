/**
 * FundResultList - 基金搜索结果列表
 * 卡片式布局，点击行展开右侧详情面板
 */
import type { FundSearchItem, SignalLevel } from '../../types';
import { SIGNAL_LABELS } from '../../types';
import { Star, Plus } from 'lucide-react';
import { clsx } from 'clsx';

/** 安全取数，防止 undefined/null 调用 .toFixed() 崩溃 */
const safeNum = (v: number | undefined | null, fallback = 0): number => v ?? fallback;

/** 信号徽章背景色映射：S+/S=深绿emerald, A=浅绿teal, B/C=黄amber, D/E/F=红rose */
const SIGNAL_BG: Record<SignalLevel, string> = {
  'S+': 'bg-emerald-600 text-white',
  'S':  'bg-emerald-500 text-white',
  'A':  'bg-teal-400 text-white',
  'B':  'bg-amber-400 text-white',
  'C':  'bg-amber-500 text-white',
  'D':  'bg-rose-500 text-white',
  'E':  'bg-rose-600 text-white',
};

interface FundResultListProps {
  results: FundSearchItem[];
  total: number;
  selectedCode: string | null;
  loading: boolean;
  sentimentMap: Record<string, {
    signalLevel: SignalLevel;
    confidenceStars: number;
    score: number;
    shortTerm: SignalLevel;
    midTerm: SignalLevel;
    longTerm: SignalLevel;
    hasDivergence: boolean;
    divergenceType?: 'bullish' | 'bearish';
    reason?: string;
  }>;
  onSelect: (fund: FundSearchItem) => void;
  onAddWatchlist?: (fund: FundSearchItem) => void;
  onAddPortfolio?: (fund: FundSearchItem) => void;
}

export default function FundResultList({
  results,
  total,
  selectedCode,
  loading,
  sentimentMap,
  onSelect,
  onAddWatchlist,
  onAddPortfolio,
}: FundResultListProps) {
  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-gray-400 text-sm">
        搜索中...
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center">
        <p className="text-gray-400 text-sm">未找到相关基金</p>
        <p className="text-xs text-gray-300 mt-1">请尝试其他关键词</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-400">
        共 {total} 个结果，显示 {results.length} 条
      </p>

      <div className="space-y-3">
        {results.map((fund) => {
          const s = sentimentMap[fund.fund_code];
          const isSelected = selectedCode === fund.fund_code;
          const level = s?.signalLevel;
          const score = s?.score;
          const reason = s?.reason;
          const label = level ? SIGNAL_LABELS[level] : '';

          return (
            <div
              key={fund.fund_code}
              onClick={() => onSelect(fund)}
              className={clsx(
                'bg-white rounded-lg border p-4 cursor-pointer transition-colors',
                isSelected
                  ? 'border-brand-cyan shadow-sm'
                  : 'border-gray-200 hover:border-brand-cyan',
              )}
            >
              <div className="flex items-center gap-4">
                {/* 左列：基金名称 + 代码 */}
                <div className="min-w-0 flex-shrink-0" style={{ width: '200px' }}>
                  <p className="text-base font-bold text-gray-900 truncate">
                    {fund.fund_short_name || fund.fund_name}
                  </p>
                  <p className="text-[13px] text-gray-400 mt-0.5 font-mono">
                    {fund.fund_code}
                  </p>
                </div>

                {/* 中列：信号徽章 + 分数 */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {level && (
                    <span className={clsx(
                      'px-2.5 py-1 rounded-md text-xs font-bold whitespace-nowrap',
                      SIGNAL_BG[level],
                    )}>
                      {level}·{label}
                    </span>
                  )}
                  {score !== undefined && score !== null && (
                    <span className="text-sm text-gray-500">
                      {safeNum(score).toFixed(0)}分
                    </span>
                  )}
                </div>

                {/* 右列：推荐理由 */}
                <div className="min-w-0 flex-1 hidden sm:block">
                  {reason && (
                    <p className="text-[13px] text-gray-500 truncate">
                      {reason}
                    </p>
                  )}
                </div>

                {/* 操作按钮 */}
                <div
                  className="flex items-center gap-1 flex-shrink-0"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    onClick={() => onAddWatchlist?.(fund)}
                    className="p-1.5 rounded-lg hover:bg-yellow-50 text-gray-400 hover:text-yellow-500 transition-colors"
                    title="添加到自选"
                  >
                    <Star className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => onAddPortfolio?.(fund)}
                    className="p-1.5 rounded-lg hover:bg-green-50 text-gray-400 hover:text-green-500 transition-colors"
                    title="添加到持仓"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
