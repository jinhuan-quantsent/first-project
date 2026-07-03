/**
 * StarRating — 星级显示组件
 */
import { Star } from 'lucide-react';
import { clsx } from 'clsx';

export default function StarRating({ value, max = 4 }: { value: number; max?: number }) {
  const clamped = Math.max(0, Math.min(max, value));
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: max }, (_, i) => (
        <Star
          key={i}
          className={clsx(
            'w-3 h-3',
            i < Math.floor(clamped)
              ? 'text-yellow-400 fill-yellow-400'
              : i < clamped
                ? 'text-yellow-400 fill-yellow-400/50'
                : 'text-gray-200'
          )}
        />
      ))}
      <span className="text-[10px] text-gray-400 ml-0.5">{clamped.toFixed(1)}</span>
    </div>
  );
}
