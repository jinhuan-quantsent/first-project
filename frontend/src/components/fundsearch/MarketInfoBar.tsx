/**
 * MarketInfoBar - 大盘信息栏
 * 显示上证/深证/创业板指数实时行情 + 市场情绪摘要
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { IndexSnapshot, SentimentLabel } from '../../types';
import { clsx } from 'clsx';

interface MarketInfoBarProps {
  indexes: IndexSnapshot[];
  globalLabel?: SentimentLabel | null;
  globalScore?: number | null;
  loading?: boolean;
}

const DUMMY_INDEXES: IndexSnapshot[] = [
  { index_code: 'SH000001', index_name: '上证指数', close: 3245.68, change_pct: 0.85, composite_score: 52, sentiment_label: 'neutral' },
  { index_code: 'SZ399001', index_name: '深证成指', close: 10562.31, change_pct: 1.23, composite_score: 55, sentiment_label: 'neutral' },
  { index_code: 'SZ399006', index_name: '创业板指', close: 2156.42, change_pct: 1.87, composite_score: 58, sentiment_label: 'neutral' },
];

function FormatChange({ value }: { value: number }) {
  const isUp   = value > 0;
  const isFlat = value === 0;
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-0.5 text-xs font-mono font-medium',
        isFlat ? 'text-gray-400' : isUp ? 'text-red-500' : 'text-green-500',
      )}
    >
      {isUp ? (
        <TrendingUp className="w-3 h-3" />
      ) : isFlat ? (
        <Minus className="w-3 h-3" />
      ) : (
        <TrendingDown className="w-3 h-3" />
      )}
      {isUp ? '+' : ''}
      {value.toFixed(2)}%
    </span>
  );
}

export default function MarketInfoBar({
  indexes = DUMMY_INDEXES,
  globalLabel = null,
  globalScore = null,
  loading = false,
}: MarketInfoBarProps) {
  if (loading) {
    return (
      <div className="card p-3 flex items-center gap-4 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-5 w-24 bg-gray-200 rounded" />
        ))}
      </div>
    );
  }

  return (
    <div className="card p-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
      {indexes.map((idx) => (
        <div key={idx.index_code} className="flex items-center gap-2">
          <span className="text-xs text-gray-400">{idx.index_name}</span>
          <span className="font-mono text-xs text-gray-700">{idx.close.toFixed(2)}</span>
          <FormatChange value={idx.change_pct} />
        </div>
      ))}

      {/* 分隔线 */}
      <div className="hidden sm:block w-px h-4 bg-gray-200" />

      {/* 市场情绪摘要 */}
      {globalScore !== null && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">市场情绪</span>
          <span
            className="text-xs font-bold px-2 py-0.5 rounded-full"
            style={{
              backgroundColor:
                globalScore >= 80 ? 'var(--signal-e)' :
                globalScore >= 65 ? 'var(--signal-d)' :
                globalScore >= 52  ? 'var(--signal-c)' :
                globalScore >= 38  ? 'var(--signal-b)' :
                globalScore >= 25  ? 'var(--signal-a)' :
                globalScore >= 12  ? 'var(--signal-s)' :
                'var(--signal-sp)',
              color: '#fff',
            }}
          >
            {globalScore.toFixed(0)}分
          </span>
          {globalLabel && (
            <span className="text-xs text-gray-500">
              {String(globalLabel).replace('_', ' ')}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
