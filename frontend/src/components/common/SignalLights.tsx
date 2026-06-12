import type { SentimentLabel } from '../../types';

interface SignalLightsProps {
  /** 三周期标签 */
  shortTerm?: SentimentLabel;
  midTerm?: SentimentLabel;
  longTerm?: SentimentLabel;
  /** 背离标记 */
  hasDivergence?: boolean;
  divergenceType?: 'bullish' | 'bearish'; // bullish=底背离 bearish=顶背离
  /** 尺寸 */
  size?: 'sm' | 'md';
}

const SIGNAL_COLORS: Record<SentimentLabel, string> = {
  extreme_fear: '#00A86B',
  fear: '#4CAF50',
  neutral: '#9E9E9E',
  greed: '#FF9800',
  extreme_greed: '#F44336',
};

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
            divergenceType === 'bullish' ? 'text-green-500' : 'text-red-500'
          }`}
          title={divergenceType === 'bullish' ? '底背离 - 可能反弹' : '顶背离 - 注意风险'}
        >
          {divergenceType === 'bullish' ? '↑' : '↓'}
        </span>
      )}
    </div>
  );
}
