import { useAppStore } from '../../store';
import SentimentBadge from '../common/SentimentBadge';
import { clsx } from 'clsx';

export default function MultiIndexCards() {
  const { multiIndexData, selectedIndex, setSelectedIndex } = useAppStore();

  if (multiIndexData.length === 0) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="card p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-16 mb-2" />
            <div className="h-6 bg-gray-200 rounded w-24 mb-2" />
            <div className="h-3 bg-gray-200 rounded w-12" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {multiIndexData.map((idx) => {
        const isSelected = idx.index_code === selectedIndex;
        const changeColor = idx.change_pct >= 0 ? 'text-market-up' : 'text-market-down';

        return (
          <button
            key={idx.index_code}
            onClick={() => setSelectedIndex(idx.index_code)}
            className={clsx(
              'card p-4 text-left transition-all duration-200 cursor-pointer',
              isSelected
                ? 'ring-2 ring-blue-500 shadow-md scale-[1.02]'
                : 'hover:shadow-md hover:scale-[1.01]'
            )}
          >
            {/* 第一重标识：情绪色块 */}
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400 font-medium">{idx.index_name}</span>
              <SentimentBadge sentiment={idx.sentiment_label} size="sm" variant="inline" showLabel={false} />
            </div>

            {/* 指数点位 */}
            <div className="flex items-baseline gap-2 mb-1">
              <span className="text-lg font-bold text-gray-800 font-mono">
                {idx.close.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={clsx('text-xs font-medium', changeColor)}>
                {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct.toFixed(2)}%
              </span>
            </div>

            {/* 第二重标识：综合评分 */}
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-400">情绪评分</span>
              <span className="text-sm font-bold text-gray-700 font-mono">
                {idx.composite_score.toFixed(0)}
                <span className="text-[10px] text-gray-400 font-normal">/100</span>
              </span>
            </div>

            {/* 第三重标识：选中态边框 + 缩放 */}
            {isSelected && (
              <div className="mt-2 text-[10px] text-blue-500 font-medium">当前选中 ▸</div>
            )}
          </button>
        );
      })}
    </div>
  );
}
