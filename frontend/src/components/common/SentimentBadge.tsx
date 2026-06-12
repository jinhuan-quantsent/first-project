import type { SentimentLabel } from '../../types';
import { clsx } from 'clsx';

interface SentimentBadgeProps {
  sentiment: SentimentLabel;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'inline' | 'table' | 'standalone';
  showLabel?: boolean;
  className?: string;
}

const SENTIMENT_CONFIG: Record<SentimentLabel, { bg: string; text: string; cn: string }> = {
  extreme_fear: {
    bg: 'bg-sentiment-extreme_fear',
    text: 'text-sentiment-extreme_fear',
    cn: '极度恐慌',
  },
  fear: {
    bg: 'bg-sentiment-fear',
    text: 'text-sentiment-fear',
    cn: '恐慌',
  },
  neutral: {
    bg: 'bg-sentiment-neutral',
    text: 'text-sentiment-neutral',
    cn: '中性',
  },
  greed: {
    bg: 'bg-sentiment-greed',
    text: 'text-sentiment-greed',
    cn: '乐观',
  },
  extreme_greed: {
    bg: 'bg-sentiment-extreme_greed',
    text: 'text-sentiment-extreme_greed',
    cn: '极度乐观',
  },
};

const SIZE_CLASSES = {
  sm: {
    dot: 'w-2 h-2',
    badge: 'px-1.5 py-0.5 text-[10px]',
  },
  md: {
    dot: 'w-3 h-3',
    badge: 'px-2 py-1 text-xs',
  },
  lg: {
    dot: 'w-4 h-4',
    badge: 'px-3 py-1.5 text-sm',
  },
};

export default function SentimentBadge({
  sentiment,
  size = 'md',
  variant = 'inline',
  showLabel = true,
  className,
}: SentimentBadgeProps) {
  const config = SENTIMENT_CONFIG[sentiment] || SENTIMENT_CONFIG.neutral;
  const sizes = SIZE_CLASSES[size];

  if (variant === 'table') {
    // 表格模式：色块 + 文字
    return (
      <span className={clsx('inline-flex items-center gap-1.5', className)}>
        <span className={clsx('sentiment-dot', sizes.dot, config.bg)} />
        {showLabel && (
          <span className={clsx('font-medium', config.text, size === 'sm' ? 'text-xs' : 'text-sm')}>
            {config.cn}
          </span>
        )}
      </span>
    );
  }

  if (variant === 'standalone') {
    // 独立模式：大色块
    return (
      <div className={clsx('flex flex-col items-center gap-1', className)}>
        <span className={clsx('rounded-full', sizes.dot, config.bg)} />
        {showLabel && (
          <span className={clsx('font-semibold', config.text, 'text-sm')}>{config.cn}</span>
        )}
      </div>
    );
  }

  // inline 模式：小色块 + 文字同行
  return (
    <span className={clsx('inline-flex items-center gap-1', className)}>
      <span className={clsx('rounded-full', sizes.dot, config.bg)} />
      {showLabel && (
        <span className={clsx('text-xs font-medium', config.text)}>{config.cn}</span>
      )}
    </span>
  );
}
