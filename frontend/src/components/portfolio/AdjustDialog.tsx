/**
 * AdjustDialog — 手动加仓/减仓对话框组件
 */
import { useState, useEffect } from 'react';
import { Play, Loader2, X } from 'lucide-react';
import { clsx } from 'clsx';
import type { PositionDetailData } from './types';
import { formatMoney } from './utils';

interface AdjustDialogProps {
  open: boolean;
  mode: 'increase' | 'decrease';
  data: PositionDetailData;
  onConfirm: (amount: number, date: string) => Promise<void>;
  onCancel: () => void;
}

export default function AdjustDialog({ open, mode, data, onConfirm, onCancel }: AdjustDialogProps) {
  const [amount, setAmount] = useState('');
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(false);

  // 每次打开重置
  useEffect(() => {
    if (open) {
      setAmount('');
      setDate(new Date().toISOString().slice(0, 10));
    }
  }, [open]);

  const handleConfirm = async () => {
    const amt = parseFloat(amount);
    if (isNaN(amt) || amt <= 0) return;
    setLoading(true);
    try {
      await onConfirm(amt, date);
      onCancel();  // 关闭对话框
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => !loading && onCancel()}>
      <div className="bg-white rounded-xl shadow-xl p-5 w-80 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-gray-800">
            {mode === 'increase' ? '手动加仓' : '手动减仓'} - {data.fundName}
          </h3>
          <button
            onClick={() => !loading && onCancel()}
            className="text-gray-300 hover:text-gray-500 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-500">
            {mode === 'increase' ? '加仓金额' : '减仓金额'}
            {mode === 'increase' && data.cashAmount !== undefined && (
              <span className="ml-2 text-gray-400">可用 {formatMoney(data.cashAmount)}</span>
            )}
            {mode === 'decrease' && (
              <span className="ml-2 text-gray-400">持仓 {formatMoney(data.marketValue)}</span>
            )}
          </label>
          <div className="flex items-center gap-1">
            <span className="text-sm text-gray-400">¥</span>
            <input
              type="text"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))}
              placeholder="输入金额"
              autoFocus
              className="flex-1 text-sm font-mono border border-gray-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-[var(--brand-cyan)]"
            />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-500">操作日期</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            max={new Date().toISOString().slice(0, 10)}
            className="w-full text-sm border border-gray-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-[var(--brand-cyan)]"
          />
        </div>

        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 transition-all disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            disabled={!amount || parseFloat(amount) <= 0 || loading}
            className={clsx(
              'flex-1 flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
              mode === 'increase'
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-green-500 text-white hover:bg-green-600',
              (!amount || parseFloat(amount) <= 0 || loading) && 'opacity-50 cursor-not-allowed'
            )}
          >
            {loading ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                处理中...
              </>
            ) : (
              <>
                <Play className="w-3 h-3" />
                确认{mode === 'increase' ? '加仓' : '减仓'}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
