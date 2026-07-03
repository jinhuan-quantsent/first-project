/**
 * PositionDetailPanel 共享工具函数
 */

/** 格式化金额 */
export function formatMoney(v: number): string {
  if (Math.abs(v) >= 10000) {
    return `¥${(v / 10000).toFixed(2)}万`;
  }
  return `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 格式化涨跌（A股习惯：红涨绿跌） */
export function formatChange(v: number, showPercent = false): { text: string; className: string } {
  const sign = v >= 0 ? '+' : '';
  const cls = v >= 0 ? 'text-red-500' : 'text-green-500';
  const text = showPercent ? `${sign}${v.toFixed(2)}%` : `${sign}¥${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return { text, className: cls };
}
