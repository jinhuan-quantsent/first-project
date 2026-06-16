/**
 * ExpandableReason 组件 — 信号理由三段式可展开
 *
 * V5.0 设计规格:
 * - 三段式结构：观察(青色竖线) → 分析(信号色竖线) → 行动(语义色竖线)
 * - 3种变体：inline(列表行内) / panel(详情面板) / compact(小卡片)
 * - 默认折叠只显示摘要，点击展开完整三段
 * - adaptReason() 向后兼容旧 string 格式
 */
import { useState, useCallback, useRef, useId } from 'react';
import { Eye, Zap, Target, ChevronDown } from 'lucide-react';
import { clsx } from 'clsx';

// ============================================================
// 类型定义
// ============================================================

/** 三段式理由数据 */
export interface ThreePartReason {
  observation: string;
  analysis: string;
  action: string;
}

/** 信号等级 */
export type SignalLevel = 'S+' | 'S' | 'A' | 'B' | 'C' | 'D' | 'E';

/** 操作建议类型 */
export type ActionAdvice = 'buy' | 'sell' | 'hold';

/** 显示变体 */
export type ReasonVariant = 'inline' | 'panel' | 'compact';

export interface ExpandableReasonProps {
  /** 三段式理由数据 */
  reason: ThreePartReason;

  /** 当前信号等级，用于"触发原因"段竖线着色 */
  signalLevel?: SignalLevel;

  /** 操作建议类型，用于"操作建议"段竖线着色 */
  actionAdvice?: ActionAdvice;

  /** 显示变体 */
  variant?: ReasonVariant;

  /** 初始展开状态 */
  defaultExpanded?: boolean;

  /** 展开状态变更回调 */
  onToggle?: (expanded: boolean) => void;

  /** 摘要最大字符数，默认 40 */
  summaryMaxLength?: number;

  /** 自定义类名 */
  className?: string;
}

// ============================================================
// 常量
// ============================================================

const SIGNAL_COLORS: Record<SignalLevel, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

const ACTION_COLORS: Record<ActionAdvice, string> = {
  buy: '#10B981',   // 绿色
  sell: '#EF4444',  // 红色
  hold: '#FBBF24',  // 黄色
};

const OBSERVE_COLOR = '#14B8A6'; // 品牌青色

// ============================================================
// 兼容函数
// ============================================================

/** 将旧 string reason 转为 ThreePartReason */
export function adaptReason(
  oldReason: string | ThreePartReason | undefined,
  signalLevel?: SignalLevel,
  actionAdvice?: ActionAdvice,
): ThreePartReason {
  if (!oldReason) {
    return {
      observation: '暂无市场现状数据',
      analysis: signalLevel ? `${signalLevel}级信号触发` : '暂无分析数据',
      action: '暂无操作建议',
    };
  }
  if (typeof oldReason === 'string') {
    return {
      observation: '—',
      analysis: oldReason,
      action: '—',
    };
  }
  return oldReason;
}

/** 从信号等级推断操作建议 */
export function inferActionAdvice(level?: SignalLevel): ActionAdvice {
  if (!level) return 'hold';
  if (level === 'S+' || level === 'S' || level === 'A') return 'buy';
  if (level === 'D' || level === 'E') return 'sell';
  return 'hold';
}

// ============================================================
// 子组件
// ============================================================

function ReasonSection({
  type,
  title,
  content,
  color,
  icon: Icon,
  isCompact,
}: {
  type: 'observe' | 'analysis' | 'action';
  title: string;
  content: string;
  color: string;
  icon: React.ComponentType<{ className?: string }>;
  isCompact: boolean;
}) {
  return (
    <div className="flex gap-2">
      {/* 左侧竖线 */}
      <div
        className="w-0.5 shrink-0 rounded-full self-stretch"
        style={{ backgroundColor: color }}
      />
      <div className={clsx('flex-1', isCompact ? 'py-0' : 'py-0.5')}>
        {/* 段标题 */}
        <div className="flex items-center gap-1 mb-0.5">
          <Icon className="w-3.5 h-3.5 text-gray-400" />
          <span className={clsx(
            'font-semibold text-gray-400',
            isCompact ? 'text-[10px]' : 'text-[11px]'
          )}>
            {title}
          </span>
        </div>
        {/* 段内容 */}
        <p className={clsx(
          'text-gray-600 leading-relaxed',
          isCompact ? 'text-[11px] leading-4' : 'text-xs leading-5'
        )}>
          {content || '—'}
        </p>
      </div>
    </div>
  );
}

function ReasonConnector({ isCompact }: { isCompact: boolean }) {
  return (
    <div className={clsx('flex justify-center', isCompact ? 'my-0' : 'my-0.5')}>
      <span className="text-gray-300 text-xs font-mono">→</span>
    </div>
  );
}

// ============================================================
// 主组件
// ============================================================

export default function ExpandableReason({
  reason,
  signalLevel,
  actionAdvice,
  variant = 'inline',
  defaultExpanded = false,
  onToggle,
  summaryMaxLength = 40,
  className,
}: ExpandableReasonProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const headerId = useId();
  const bodyId = useId();
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const isCompact = variant === 'compact';

  const handleToggle = useCallback(() => {
    const next = !expanded;
    setExpanded(next);
    onToggle?.(next);

    // compact 变体：5秒后自动折叠
    if (next && isCompact) {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setExpanded(false);
        onToggle?.(false);
      }, 5000);
    }
  }, [expanded, isCompact, onToggle]);

  // 推断操作建议
  const effectiveAction = actionAdvice ?? inferActionAdvice(signalLevel);

  // 摘要文本
  const summaryText = reason.observation && reason.observation !== '—'
    ? reason.observation.slice(0, summaryMaxLength) + (reason.observation.length > summaryMaxLength ? '...' : '')
    : reason.analysis?.slice(0, summaryMaxLength) + (reason.analysis && reason.analysis.length > summaryMaxLength ? '...' : '');

  // 分析段竖线颜色（信号等级色）
  const analysisColor = signalLevel ? SIGNAL_COLORS[signalLevel] : '#94A3B8';
  // 行动段竖线颜色（语义色）
  const actionColor = ACTION_COLORS[effectiveAction];

  return (
    <div
      className={clsx(
        'rounded-[10px] border border-gray-100 overflow-hidden transition-all duration-250',
        'bg-white',
        className,
      )}
    >
      {/* Header：折叠态摘要行 */}
      <button
        id={headerId}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={handleToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleToggle();
          }
        }}
        className={clsx(
          'w-full flex items-center gap-2 px-3 text-left',
          'hover:bg-black/[0.04] transition-colors duration-150 rounded-[10px]',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-300',
          isCompact ? 'py-1.5' : 'py-2',
        )}
      >
        {/* 摘要文本 */}
        <span className={clsx(
          'flex-1 text-gray-600 min-w-0 truncate',
          isCompact ? 'text-[11px]' : 'text-[13px]',
        )}>
          {summaryText}
        </span>
        {/* Chevron 箭头 */}
        <ChevronDown
          className={clsx(
            'w-3.5 h-3.5 shrink-0 text-gray-400 transition-transform duration-250',
            expanded && 'rotate-180',
          )}
        />
      </button>

      {/* Body：展开态内容区 */}
      <div
        id={bodyId}
        role="region"
        aria-labelledby={headerId}
        style={{
          maxHeight: expanded ? '500px' : '0px',
          opacity: expanded ? 1 : 0,
          overflow: 'hidden',
          transition: 'max-height 250ms cubic-bezier(0.4,0,0.2,1), opacity 250ms cubic-bezier(0.4,0,0.2,1)',
        }}
      >
        {/* 展开时 Header 底部分隔线 */}
        <div className="mx-3 border-t border-gray-100" />

        <div className={clsx(
          'px-3 bg-slate-50',
          isCompact ? 'pt-1.5 pb-2 gap-1' : 'pt-2 pb-3 gap-2',
          'flex flex-col',
        )}>
          {/* 市场现状（观察） */}
          <ReasonSection
            type="observe"
            title="市场现状"
            content={reason.observation}
            color={OBSERVE_COLOR}
            icon={Eye}
            isCompact={isCompact}
          />

          <ReasonConnector isCompact={isCompact} />

          {/* 触发原因（分析） */}
          <ReasonSection
            type="analysis"
            title="触发原因"
            content={reason.analysis}
            color={analysisColor}
            icon={Zap}
            isCompact={isCompact}
          />

          <ReasonConnector isCompact={isCompact} />

          {/* 操作建议（行动） */}
          <ReasonSection
            type="action"
            title="操作建议"
            content={reason.action}
            color={actionColor}
            icon={Target}
            isCompact={isCompact}
          />
        </div>
      </div>
    </div>
  );
}
