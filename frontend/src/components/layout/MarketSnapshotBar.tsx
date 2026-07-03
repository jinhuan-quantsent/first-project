import { useAppStore } from '../../store';
import SignalBadge from '../common/SentimentBadge';
import type { SignalLevel, ConfidenceStars } from '../../types';
import { clsx } from 'clsx';
import { SIGNAL_COLORS, SIGNAL_LABELS, mapOldToNew } from '../../types';

/** 置信度星星渲染 */
function ConfidenceStarsDisplay({ stars, color, className }: { stars: ConfidenceStars; color: string; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-px", className)} title={`置信度 ${stars} 星`}>
      {Array.from({ length: 4 }, (_, i) => (
        <svg
          key={i}
          width="10"
          height="10"
          viewBox="0 0 10 10"
          className={i < stars ? '' : 'opacity-20'}
        >
          <path
            d="M5 1L6.2 3.6L9 4L7 6.1L7.5 9L5 7.6L2.5 9L3 6.1L1 4L3.8 3.6L5 1Z"
            fill={i < stars ? color : '#CBD5E1'}
          />
        </svg>
      ))}
    </span>
  );
}

/** 体制标签映射 */
const REGIME_CN: Record<string, string> = {
  bull: '牛市',
  bear: '熊市',
  sideways: '震荡',
  extreme_volatility: '极端波动',
};

export default function MarketSnapshotBar() {
  const { snapshot, snapshotLoading } = useAppStore();

  if (snapshotLoading || !snapshot) {
    return (
      <div
        className="bg-white border-b border-gray-200 flex items-center justify-center"
        style={{ height: 'var(--snapshot-bar-height)' }}
      >
        <span className="text-xs text-gray-400">加载市场数据中...</span>
      </div>
    );
  }

  const {
    indexes,
    global_sentiment,
    global_score,
    signal_level,
    confidence_stars,
    regime,
    conclusion,
  } = snapshot;

  // 获取综合信号等级（优先V5，降级用映射）
  const compositeLevel: SignalLevel = signal_level || mapOldToNew(global_sentiment);
  const compositeStars: ConfidenceStars = confidence_stars || 2;
  const compositeColor = SIGNAL_COLORS[compositeLevel] || '#94A3B8';
  const compositeLabel = SIGNAL_LABELS[compositeLevel] || '中性';
  const compositeRegime = regime || 'sideways';

  return (
    <div
      className="bg-white border-b border-gray-200 flex items-center px-3 md:px-4 gap-2 md:gap-4 overflow-x-auto text-xs md:text-sm"
      style={{ height: 'var(--snapshot-bar-height)' }}
    >
      {/* 全局情绪 — V5 7级信号 + 置信度星星 */}
      <div className="flex items-center gap-1.5 shrink-0">
        <SignalBadge level={compositeLevel} size="sm" variant="inline" />
        <span className="font-mono text-gray-800 font-semibold">{global_score.toFixed(0)}</span>
        <ConfidenceStarsDisplay stars={compositeStars} color={compositeColor} />
        <span className="text-[10px] text-gray-400 hidden md:inline">
          {REGIME_CN[compositeRegime] || compositeRegime}
        </span>
      </div>

      <div className="w-px h-4 bg-gray-200 shrink-0" />

      {/* 各指数快照 */}
      {indexes.map((idx) => {
        const idxLevel: SignalLevel = idx.signal_level || mapOldToNew(idx.sentiment_label);
        const idxStars: ConfidenceStars = idx.confidence_stars || 2;
        const idxColor = SIGNAL_COLORS[idxLevel] || '#94A3B8';

        return (
          <div key={idx.index_code} className="flex items-center gap-1 shrink-0">
            <span className="text-gray-400">{idx.index_name.replace('指', '')}</span>
            <span className={`font-mono ${idx.change_pct >= 0 ? 'text-red-500' : 'text-green-500'}`}>
              {idx.close.toFixed(0)}
            </span>
            <span className={`text-xs ${idx.change_pct >= 0 ? 'text-red-500' : 'text-green-500'}`}>
              {idx.change_pct >= 0 ? '+' : ''}{idx.change_pct.toFixed(2)}%
            </span>
            <SignalBadge level={idxLevel} size="sm" variant="inline" />
            <ConfidenceStarsDisplay stars={idxStars} color={idxColor} className="hidden md:inline-flex" />
          </div>
        );
      })}

      <div className="w-px h-4 bg-gray-200 shrink-0" />

      {/* 一句话结论 */}
      <span className="text-gray-500 truncate hidden md:block">{conclusion}</span>
    </div>
  );
}
