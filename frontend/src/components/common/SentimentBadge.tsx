import type { SignalLevel, SignalLabel } from '../../types';
import { mapOldToNew, SIGNAL_COLORS } from '../../types';
import { clsx } from 'clsx';

interface SignalBadgeProps {
  /** 支持新旧两套信号体系 */
  level: SignalLevel | SignalLabel;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'inline' | 'table' | 'standalone';
  showLabel?: boolean;
  className?: string;
}

const SIZE_CLASSES = {
  sm: { dot: 'w-2 h-2', badge: 'px-1.5 py-0.5 text-[10px]' },
  md: { dot: 'w-3 h-3', badge: 'px-2 py-1 text-xs' },
  lg: { dot: 'w-4 h-4', badge: 'px-3 py-1.5 text-sm' },
};

const LEVEL_CN: Record<SignalLevel, string> = {
  'S+': '极度恐惧',
  'S':  '恐惧',
  'A':  '偏恐惧',
  'B':  '中性',
  'C':  '偏贪婪',
  'D':  '贪婪',
  'E':  '极度贪婪',
};

function normalizeLevel(l: SignalLevel | SignalLabel): SignalLevel {
  if (typeof l === 'string' && ['S+', 'S', 'A', 'B', 'C', 'D', 'E'].includes(l)) {
    return l as SignalLevel;
  }
  // 尝试从旧标签映射，映射失败则回退到 'B'（中性）
  if (typeof l === 'string') {
    try {
      return mapOldToNew(l as SignalLabel);
    } catch {
      return 'B';
    }
  }
  return 'B';
}

export default function SignalBadge({
  level,
  size = 'md',
  variant = 'inline',
  showLabel = true,
  className,
}: SignalBadgeProps) {
  const lvl = normalizeLevel(level);
  const dotColor = SIGNAL_COLORS[lvl] || '#94A3B8';
  const label = LEVEL_CN[lvl] || lvl;
  const sizes = SIZE_CLASSES[size];

  if (variant === 'table') {
    return (
      <span className={clsx('inline-flex items-center gap-1.5', className)}>
        <span className={clsx('sentiment-dot', sizes.dot)} style={{ backgroundColor: dotColor }} />
        {showLabel && (
          <span className={clsx('font-medium', size === 'sm' ? 'text-xs' : 'text-sm')} style={{ color: dotColor }}>
            {label}
          </span>
        )}
      </span>
    );
  }

  if (variant === 'standalone') {
    return (
      <div className={clsx('flex flex-col items-center gap-1', className)}>
        <span className={clsx('rounded-full', sizes.dot)} style={{ backgroundColor: dotColor }} />
        {showLabel && (
          <span className={clsx('font-semibold text-sm')} style={{ color: dotColor }}>{label}</span>
        )}
      </div>
    );
  }

  // inline 模式
  return (
    <span className={clsx('inline-flex items-center gap-1', className)}>
      <span className={clsx('rounded-full', sizes.dot)} style={{ backgroundColor: dotColor }} />
      {showLabel && (
        <span className={clsx('text-xs font-medium')} style={{ color: dotColor }}>{label}</span>
      )}
    </span>
  );
}
