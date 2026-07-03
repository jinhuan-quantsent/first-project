/**
 * 置信度星级组件 — V5.0
 * 显示1-4星置信度评级
 */
import { Star } from 'lucide-react';
import { clsx } from 'clsx';

interface ConfidenceStarsProps {
  stars: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

const SIZE_MAP = {
  sm: 'w-3 h-3',
  md: 'w-4 h-4',
  lg: 'w-5 h-5',
};

const LABEL_MAP: Record<number, string> = {
  1: '低',
  2: '中',
  3: '高',
  4: '极高',
};

export default function ConfidenceStars({
  stars,
  size = 'sm',
  showLabel = false,
  className,
}: ConfidenceStarsProps) {
  const clamped = Math.max(1, Math.min(4, stars));

  return (
    <div className={clsx('flex items-center gap-0.5', className)}>
      {[1, 2, 3, 4].map((s) => (
        <Star
          key={s}
          className={clsx(
            SIZE_MAP[size],
            s <= clamped
              ? 'text-yellow-400 fill-yellow-400'
              : 'text-gray-200'
          )}
        />
      ))}
      {showLabel && (
        <span className="text-[10px] text-gray-400 ml-1">
          {LABEL_MAP[clamped]}
        </span>
      )}
    </div>
  );
}
