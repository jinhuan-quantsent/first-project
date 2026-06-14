/**
 * SignalRibbon - 7级信号色带
 * 页面顶部通栏，等宽7段，对应 S+/S/A/B/C/D/E
 */
import type { SignalLevel } from '../../types';

const SIGNAL_SEGMENTS: { level: SignalLevel; label: string; color: string }[] = [
  { level: 'S+', label: '极度恐惧', color: 'var(--signal-sp)' },
  { level: 'S',  label: '恐惧',   color: 'var(--signal-s)' },
  { level: 'A',  label: '偏恐惧', color: 'var(--signal-a)' },
  { level: 'B',  label: '中性',   color: 'var(--signal-b)' },
  { level: 'C',  label: '偏贪婪', color: 'var(--signal-c)' },
  { level: 'D',  label: '贪婪',   color: 'var(--signal-d)' },
  { level: 'E',  label: '极度贪婪', color: 'var(--signal-e)' },
];

interface SignalRibbonProps {
  /** 当前激活的信号等级（可选，有则高亮对应段） */
  activeLevel?: SignalLevel | null;
  /** 是否显示标签文字 */
  showLabels?: boolean;
  /** 高度 px */
  height?: number;
}

export default function SignalRibbon({
  activeLevel,
  showLabels = false,
  height = 8,
}: SignalRibbonProps) {
  return (
    <div
      className="w-full flex"
      style={{ height, borderRadius: height / 2, overflow: 'hidden' }}
      title="7级信号色带：S+极度恐惧 → E极度贪婪"
    >
      {SIGNAL_SEGMENTS.map((seg, i) => {
        const isActive = activeLevel === seg.level;
        const isLeftmost  = i === 0;
        const isRightmost = i === SIGNAL_SEGMENTS.length - 1;
        return (
          <div
            key={seg.level}
            className="flex-1 transition-all duration-300"
            style={{
              backgroundColor: seg.color,
              opacity: activeLevel && !isActive ? 0.45 : 1,
              borderLeft:  isLeftmost  ? 'none' : '1px solid rgba(255,255,255,0.25)',
              borderRight: isRightmost ? 'none' : undefined,
            }}
          >
            {showLabels && (
              <div className="text-[8px] text-white text-center leading-none mt-[2px] font-medium select-none">
                {seg.label}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
