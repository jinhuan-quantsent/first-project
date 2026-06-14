import type { SignalLevel } from '../../types';
import { SIGNAL_COLORS } from '../../types';

interface SignalLightsProps {
  /** 三周期信号等级 */
  shortTerm?: SignalLevel;
  midTerm?: SignalLevel;
  longTerm?: SignalLevel;
  /** 背离标记 */
  hasDivergence?: boolean;
  divergenceType?: 'bullish' | 'bearish';
  /** 尺寸 */
  size?: 'sm' | 'md';
}

export default function SignalLights({
  shortTerm,
  midTerm,
  longTerm,
  hasDivergence = false,
  divergenceType,
  size = 'md',
}: SignalLightsProps) {
  const dotSize = size === 'sm' ? 'w-2 h-2' : 'w-3 h-3';
  const gap = size === 'sm' ? 'gap-1' : 'gap-1.5';

  return (
    <div className={`flex items-center ${gap}`}>
      {/* 三周期信号灯 */}
      {shortTerm && (
        <span
          className={`${dotSize} rounded-full`}
          style={{ backgroundColor: SIGNAL_COLORS[shortTerm] }}
          title={`短期: ${shortTerm}`}
        />
      )}
      {midTerm && (
        <span
          className={`${dotSize} rounded-full`}
          style={{ backgroundColor: SIGNAL_COLORS[midTerm] }}
          title={`中期: ${midTerm}`}
        />
      )}
      {longTerm && (
        <span
          className={`${dotSize} rounded-full`}
          style={{ backgroundColor: SIGNAL_COLORS[longTerm] }}
          title={`长期: ${longTerm}`}
        />
      )}

      {/* 背离信号 */}
      {hasDivergence && divergenceType && (
        <span
          className={`text-xs font-bold ml-1 ${
            divergenceType === 'bullish' ? 'text-signal-sp' : 'text-signal-d'
          }`}
          title={divergenceType === 'bullish' ? '底背离 - 可能反弹' : '顶背离 - 注意风险'}
        >
          {divergenceType === 'bullish' ? '↑' : '↓'}
        </span>
      )}
    </div>
  );
}
