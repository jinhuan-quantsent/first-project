/**
 * 背离预警 Badge — 顶背离/底背离/无背离/数据不足
 */

export interface DivergenceData {
  type: string;           // "top" | "bottom" | "none" | "insufficient_data"
  strength: number;       // 0.0-1.0
  signal: string | null;  // "buy" | "sell" | null
  confidence: string;     // "high" | "low"
}

interface DivergenceBadgeProps {
  divergence: DivergenceData | null;
}

export default function DivergenceBadge({ divergence }: DivergenceBadgeProps) {
  if (!divergence || divergence.type === 'insufficient_data') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold bg-gray-100 text-gray-400">
        数据不足
      </span>
    );
  }

  const isTop = divergence.type === 'top';
  const isBottom = divergence.type === 'bottom';

  const config = isTop
    ? { label: '顶背离 \u26A0\uFE0F', bg: 'bg-red-100', text: 'text-red-700', signal: '卖出参考' }
    : isBottom
      ? { label: '底背离 \uD83D\uDD14', bg: 'bg-green-100', text: 'text-green-700', signal: '买入参考' }
      : { label: '无背离', bg: 'bg-gray-100', text: 'text-gray-500', signal: '' };

  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1.5">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${config.bg} ${config.text}`}>
          {config.label}
        </span>
        {config.signal && (
          <span className={`text-[10px] font-medium ${config.text}`}>{config.signal}</span>
        )}
        {divergence.confidence === 'low' && (
          <span className="text-[9px] text-gray-400">(低置信度)</span>
        )}
      </div>
      <p className="text-[9px] text-gray-400">辅助参考，非独立交易建议</p>
    </div>
  );
}
