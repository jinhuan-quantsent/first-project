import type { SentimentLabel } from '../../types';
import { clsx } from 'clsx';

interface MicroTrendBarProps {
  /** 5日数据点 */
  data: { date: string; score: number; label: SentimentLabel }[];
  className?: string;
}

const SENTIMENT_BG: Record<SentimentLabel, string> = {
  extreme_fear: 'bg-sentiment-extreme_fear',
  fear: 'bg-sentiment-fear',
  neutral: 'bg-sentiment-neutral',
  greed: 'bg-sentiment-greed',
  extreme_greed: 'bg-sentiment-extreme_greed',
};

export default function MicroTrendBar({ data, className }: MicroTrendBarProps) {
  if (!data || data.length === 0) {
    return <div className="h-6 bg-gray-100 rounded animate-pulse" />;
  }

  return (
    <div className={clsx('relative flex items-end gap-1 h-8', className)}>
      {data.map((point, i) => {
        const heightPct = Math.max(8, Math.min(100, point.score));
        return (
          <div
            key={i}
            className="flex-1 flex flex-col items-center justify-end"
            title={`${point.date}: ${point.score.toFixed(0)}分`}
          >
            <div
              className={clsx('w-full rounded-t-sm transition-all duration-300', SENTIMENT_BG[point.label])}
              style={{ height: `${heightPct}%` }}
            />
          </div>
        );
      })}
      {/* 中性基准线 */}
      <div className="absolute left-0 right-0 border-b border-dashed border-gray-300" style={{ bottom: '50%' }} />
    </div>
  );
}
