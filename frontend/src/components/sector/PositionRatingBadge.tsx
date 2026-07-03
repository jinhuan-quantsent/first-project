/**
 * PositionRatingBadge — 建仓评级小标签
 *
 * 用于机会雷达卡片右上角、自选列表等紧凑场景
 */
import { clsx } from 'clsx';
import { POSITION_RATING_CONFIG } from '../../types/positionRating';
import type { PositionRating } from '../../types/positionRating';

interface PositionRatingBadgeProps {
  rating: PositionRating;
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

export default function PositionRatingBadge({
  rating,
  showLabel = true,
  size = 'sm',
}: PositionRatingBadgeProps) {
  const cfg = POSITION_RATING_CONFIG[rating];

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border font-bold',
        cfg.bg,
        cfg.text,
        cfg.border,
        size === 'sm' ? 'text-[9px] px-1.5 py-0.5' : 'text-[10px] px-2 py-1',
      )}
    >
      <span
        className="inline-block rounded-full"
        style={{
          width: size === 'sm' ? '6px' : '8px',
          height: size === 'sm' ? '6px' : '8px',
          background: cfg.color,
        }}
      />
      {showLabel && cfg.shortLabel}
    </span>
  );
}

/**
 * PositionRatingDot — 建仓评级小圆点
 *
 * 用于自选列表行内标识
 */
export function PositionRatingDot({ rating }: { rating: PositionRating }) {
  const cfg = POSITION_RATING_CONFIG[rating];
  return (
    <span
      className={clsx('inline-block rounded-full', cfg.dot)}
      style={{ width: '8px', height: '8px' }}
      title={cfg.label}
    />
  );
}
