import { useAppStore } from '../../store';
import SentimentBadge from '../common/SentimentBadge';
import type { SentimentLabel } from '../../types';

const SENTIMENT_LABEL_CN: Record<SentimentLabel, string> = {
  extreme_fear: '极度恐慌',
  fear: '恐慌',
  neutral: '中性',
  greed: '乐观',
  extreme_greed: '极度乐观',
};

export default function MarketSnapshotBar() {
  const { snapshot, snapshotLoading } = useAppStore();

  if (snapshotLoading || !snapshot) {
    return (
      <div
        className="fixed top-0 left-0 right-0 z-50 bg-gray-800 text-white flex items-center justify-center"
        style={{ height: 'var(--snapshot-bar-height)' }}
      >
        <span className="text-xs">加载市场数据中...</span>
      </div>
    );
  }

  const { indexes, global_sentiment, global_score, conclusion } = snapshot;

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 bg-gray-800 text-white flex items-center px-3 md:px-4 gap-2 md:gap-4 overflow-x-auto text-xs md:text-sm"
      style={{ height: 'var(--snapshot-bar-height)' }}
    >
      {/* 全局情绪 */}
      <div className="flex items-center gap-1.5 shrink-0">
        <SentimentBadge sentiment={global_sentiment} size="sm" variant="inline" />
        <span className="font-mono text-white/90">{global_score.toFixed(0)}</span>
      </div>

      <div className="w-px h-4 bg-white/20 shrink-0" />

      {/* 各指数快照 */}
      {indexes.map((idx) => (
        <div key={idx.index_code} className="flex items-center gap-1 shrink-0">
          <span className="text-white/60">{idx.index_name.replace('指', '')}</span>
          <span className={`font-mono ${idx.change_pct >= 0 ? 'text-red-400' : 'text-green-400'}`}>
            {idx.close.toFixed(0)}
          </span>
          <span className={`text-xs ${idx.change_pct >= 0 ? 'text-red-400' : 'text-green-400'}`}>
            {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct.toFixed(2)}%
          </span>
          <SentimentBadge sentiment={idx.sentiment_label} size="sm" variant="inline" />
        </div>
      ))}

      <div className="w-px h-4 bg-white/20 shrink-0" />

      {/* 一句话结论 */}
      <span className="text-white/70 truncate hidden md:block">{conclusion}</span>
    </div>
  );
}
