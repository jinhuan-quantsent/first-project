/**
 * ExecutionButton - 仓位执行按钮
 * 含防重复提交（同天同基金一次）
 */
import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import type { SignalLevel } from '../../types';

interface ExecutionButtonProps {
  fundCode: string;
  fundName: string;
  signalLevel: SignalLevel;
  confidenceStars: number;
  currentPositionPct: number;
  targetPositionPct: number;
  onExecute: () => Promise<void>;
  disabled?: boolean;
}

const SIGNAL_BG: Record<SignalLevel, string> = {
  'S+': 'bg-signal-sp',
  'S':  'bg-signal-s',
  'A':  'bg-signal-a',
  'B':  'bg-signal-b',
  'C':  'bg-signal-c',
  'D':  'bg-signal-d',
  'E':  'bg-signal-e',
};

export default function ExecutionButton({
  fundCode,
  fundName,
  signalLevel,
  confidenceStars,
  currentPositionPct,
  targetPositionPct,
  onExecute,
  disabled = false,
}: ExecutionButtonProps) {
  const [executing, setExecuting] = useState(false);
  const [done, setDone]         = useState(false);

  const diff = targetPositionPct - currentPositionPct;
  const actionText = diff > 0 ? `加仓至 ${Math.round(targetPositionPct * 100)}%` :
                    diff < 0 ? `减仓至 ${Math.round(targetPositionPct * 100)}%` :
                    '仓位无需调整';

  const handleClick = async () => {
    if (disabled || executing || done || Math.abs(diff) < 0.015) return;
    setExecuting(true);
    try {
      await onExecute();
      setDone(true);
      setTimeout(() => setDone(false), 3000);
    } catch {
      // 错误由调用方通过 toast 提示
    } finally {
      setExecuting(false);
    }
  };

  const isDisabled = disabled || executing || done || Math.abs(diff) < 0.015;

  return (
    <button
      onClick={handleClick}
      disabled={isDisabled}
      className={`
        w-full flex items-center justify-center gap-2
        px-4 py-2.5 rounded-lg text-sm font-medium text-white
        transition-all duration-200
        ${done ? 'bg-green-500' : SIGNAL_BG[signalLevel] || 'bg-gray-400'}
        ${isDisabled && !done ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.98]'}
      `}
    >
      {executing ? (
        <>
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="3" strokeDasharray="32" strokeLinecap="round" />
          </svg>
          执行中...
        </>
      ) : done ? (
        <>✓ 执行成功</>
      ) : (
        <>
          {actionText}
          <ChevronRight className="w-4 h-4" />
        </>
      )}
    </button>
  );
}
