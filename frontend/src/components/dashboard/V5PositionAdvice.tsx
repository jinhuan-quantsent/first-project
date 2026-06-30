/**
 * V5PositionAdvice — Dashboard 仓位建议卡片（接V5后端 position_v5.py）
 *
 * 替代硬编码 POSITION_ADVICE 映射表，展示基于5×7矩阵+置信度修正的个性化建议。
 * 数据来源: /api/v5/market/multi-index 返回的 position_advice 字段。
 */
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { clsx } from 'clsx';

interface PositionAdviceProps {
  suggestedPosition: number;
  cashReserve: number;
  action: string;
  reason: string;
  riskLevel: string;
  signalLevel?: string;
  confidenceStars?: number;
}

/** action → 标签映射 */
const ACTION_LABELS: Record<string, string> = {
  increase: '加仓',
  reduce: '减仓',
  heavy_reduce: '大幅减仓',
  hold: '持有观望',
};

const RISK_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  extreme: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-600' },
  high: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-600' },
  medium: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-600' },
  low: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-600' },
};

export default function V5PositionAdvice({
  suggestedPosition,
  cashReserve,
  action,
  reason,
  riskLevel,
  signalLevel,
  confidenceStars,
}: PositionAdviceProps) {
  const isBuy = ['increase'].includes(action);
  const isSell = ['reduce', 'heavy_reduce'].includes(action);
  const riskStyle = RISK_COLORS[riskLevel] || RISK_COLORS.medium;

  return (
    <div className={clsx(
      'rounded-lg p-4 border',
      isBuy ? 'bg-green-50 border-green-200'
      : isSell ? 'bg-red-50 border-red-200'
      : 'bg-gray-50 border-gray-200'
    )}>
      {/* 操作图标 + 标签 */}
      <div className="flex items-center gap-2 mb-2">
        {isBuy ? (
          <TrendingUp className="w-5 h-5 text-green-500" />
        ) : isSell ? (
          <TrendingDown className="w-5 h-5 text-red-500" />
        ) : (
          <Minus className="w-5 h-5 text-gray-400" />
        )}
        <span className="font-bold text-gray-800">
          {ACTION_LABELS[action] || action}
        </span>
        <span className={clsx('text-xs px-1.5 py-0.5 rounded-full', riskStyle.bg, riskStyle.text)}>
          {riskLevel === 'extreme' ? '极高风险' : riskLevel === 'high' ? '高风险' : riskLevel === 'medium' ? '中风险' : '低风险'}
        </span>
      </div>

      {/* 建议仓位 */}
      <div className="flex items-baseline gap-4 mb-2">
        <div>
          <span className="text-xs text-gray-400">建议仓位</span>
          <p className="text-lg font-bold text-gray-800">{suggestedPosition}%</p>
        </div>
        <div>
          <span className="text-xs text-gray-400">现金储备</span>
          <p className="text-lg font-bold text-gray-500">{cashReserve}%</p>
        </div>
      </div>

      {/* 理由 */}
      <p className="text-xs text-gray-500 leading-relaxed">{reason}</p>

      {/* 信号等级 + 置信度 */}
      {(signalLevel || confidenceStars !== undefined) && (
        <p className="text-xs text-gray-400 mt-1.5">
          {signalLevel && `信号 ${signalLevel}`}
          {signalLevel && confidenceStars !== undefined && ' · '}
          {confidenceStars !== undefined && `置信度 ${confidenceStars} 星`}
        </p>
      )}
    </div>
  );
}
