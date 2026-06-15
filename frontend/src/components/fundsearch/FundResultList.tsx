/**
 * FundResultList - 基金搜索结果列表
 * 表格形式展示，点击行展开详情
 */
import type { FundSearchItem, SignalLevel } from '../../types';
import SentimentBadge from '../common/SentimentBadge';
import SignalLights from '../common/SignalLights';
import { Star, ChevronUp, ChevronDown, Plus } from 'lucide-react';
import { clsx } from 'clsx';

/** 安全取数，防止 undefined/null 调用 .toFixed() 崩溃 */
const safeNum = (v: number | undefined | null, fallback = 0): number => v ?? fallback;

interface FundResultListProps {
  results: FundSearchItem[];
  total: number;
  selectedCode: string | null;
  loading: boolean;
  sentimentMap: Record<string, {
    signalLevel: SignalLevel;
    confidenceStars: number;
    shortTerm: SignalLevel;
    midTerm: SignalLevel;
    longTerm: SignalLevel;
    hasDivergence: boolean;
    divergenceType?: 'bullish' | 'bearish';
  }>;
  onSelect: (fund: FundSearchItem) => void;
  onAddWatchlist?: (fund: FundSearchItem) => void;
  onAddPortfolio?: (fund: FundSearchItem) => void;
}

/** 涨跌颜色（A股习惯：红涨绿跌） */
function returnClass(v: number | undefined | null): string {
  const safe = v ?? 0;
  if (safe > 0) return 'text-red-500';
  if (safe < 0) return 'text-green-500';
  return 'text-gray-400';
}

function formatReturn(v: number | undefined | null): string {
  const safe = v ?? 0;
  return `${safe >= 0 ? '+' : ''}${safe.toFixed(2)}%`;
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
      <div className="card p-8 text-center text-gray-400 text-sm">
        搜索中...
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="card p-8 text-center">
        <p className="text-gray-400 text-sm">未找到相关基金</p>
        <p className="text-xs text-gray-300 mt-1">请尝试其他关键词</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400">
        共 {total} 个结果，显示 {results.length} 条
      </p>

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">代码</th>
                <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">名称</th>
                <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">类型</th>
                <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">V5信号</th>
                <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">置信度</th>
                <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">多周期</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">净值</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">日收益</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">月收益</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">年收益</th>
                <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">操作</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {results.map((fund) => {
                const s = sentimentMap[fund.fund_code];
                const isSelected = selectedCode === fund.fund_code;
                return (
                  <tr
                    key={fund.fund_code}
                    onClick={() => onSelect(fund)}
                    className={clsx(
                      'border-t border-gray-100 cursor-pointer transition-colors',
                      isSelected ? 'bg-brand-50/50' : 'hover:bg-gray-50',
                    )}
                  >
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{fund.fund_code}</td>
                    <td className="px-4 py-2.5 font-medium text-gray-800">
                      {fund.fund_short_name || fund.fund_name}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="text-xs px-1.5 py-0.5 bg-gray-100 rounded">{fund.fund_type}</span>
                    </td>

                    {/* V5信号 */}
                    <td className="px-4 py-2.5 text-center">
                      {s ? <SentimentBadge level={s.signalLevel} size="sm" /> : '-'}
                    </td>

                    {/* 置信度星级 */}
                    <td className="px-4 py-2.5 text-center">
                      {s && (
                        <div className="flex justify-center gap-0.5">
                          {[1, 2, 3, 4].map((star) => (
                            <Star
                              key={star}
                              className={clsx(
                                'w-3 h-3',
                                star <= s.confidenceStars
                                  ? 'text-yellow-400 fill-yellow-400'
                                  : 'text-gray-300',
                              )}
                            />
                          ))}
                        </div>
                      )}
                    </td>

                    {/* 多周期信号灯 */}
                    <td className="px-4 py-2.5 text-center">
                      {s && (
                        <div className="flex justify-center">
                          <SignalLights
                            shortTerm={s.shortTerm}
                            midTerm={s.midTerm}
                            longTerm={s.longTerm}
                            hasDivergence={s.hasDivergence}
                            divergenceType={s.divergenceType}
                            size="sm"
                          />
                        </div>
                      )}
                    </td>

                    <td className={`px-4 py-2.5 text-right font-mono text-xs ${returnClass(fund.nav)}`}>
                      {safeNum(fund.nav).toFixed(4)}
                    </td>
                    <td className={`px-4 py-2.5 text-right text-xs ${returnClass(fund.daily_return)}`}>
                      {formatReturn(fund.daily_return)}
                    </td>
                    <td className={`px-4 py-2.5 text-right text-xs ${returnClass(fund.month_return)}`}>
                      {formatReturn(fund.month_return)}
                    </td>
                    <td className={`px-4 py-2.5 text-right text-xs ${returnClass(fund.year_return)}`}>
                      {formatReturn(fund.year_return)}
                    </td>

                    {/* 操作按钮 */}
                    <td className="px-3 py-2.5 text-center" onClick={e => e.stopPropagation()}>
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => onAddWatchlist?.(fund)}
                          className="p-1 rounded hover:bg-yellow-50 text-gray-400 hover:text-yellow-500 transition-colors"
                          title="添加到自选"
                        >
                          <Star className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onAddPortfolio?.(fund)}
                          className="p-1 rounded hover:bg-green-50 text-gray-400 hover:text-green-500 transition-colors"
                          title="添加到持仓"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>

                    <td className="px-2 py-2.5 text-gray-400">
                      {isSelected ? (
                        <ChevronUp className="w-4 h-4" />
                      ) : (
                        <ChevronDown className="w-4 h-4" />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
