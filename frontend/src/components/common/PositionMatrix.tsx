/**
 * 仓位矩阵可视化组件 — V5.0
 * 5×7 仓位矩阵（当前仓位行 × 信号等级列）
 */
import { clsx } from 'clsx';

interface PositionMatrixProps {
  currentLevel: string;
  signalLevel: string;
  className?: string;
}

const ROWS = ['空仓', '轻仓', '半仓', '重仓', '满仓'];
const COLS = ['S+', 'S', 'A', 'B', 'C', 'D', 'E'];

const MATRIX: string[][] = [
  ['轻仓', '轻仓', '半仓', '半仓', '半仓', '轻仓', '空仓'],
  ['轻仓', '半仓', '半仓', '重仓', '半仓', '轻仓', '空仓'],
  ['半仓', '半仓', '重仓', '重仓', '重仓', '半仓', '轻仓'],
  ['半仓', '重仓', '重仓', '满仓', '满仓', '重仓', '半仓'],
  ['重仓', '重仓', '满仓', '满仓', '满仓', '重仓', '半仓'],
];

const CELL_COLORS: Record<string, string> = {
  '空仓': '#DC2626',
  '轻仓': '#EF4444',
  '半仓': '#FBBF24',
  '重仓': '#10B981',
  '满仓': '#059669',
};

const SIGNAL_BG: Record<string, string> = {
  'S+': '#05966915',
  'S': '#10B98115',
  'A': '#6EE7B715',
  'B': '#FBBF2415',
  'C': '#FCA5A515',
  'D': '#EF444415',
  'E': '#DC262615',
};

const ROW_MAP: Record<string, number> = {
  'empty': 0, 'light': 1, 'mid': 2, 'heavy': 3, 'full': 4,
};

const SIGNAL_MAP: Record<string, number> = {
  'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5, 'E': 6,
};

export default function PositionMatrix({
  currentLevel,
  signalLevel,
  className,
}: PositionMatrixProps) {
  const rowIdx = ROW_MAP[currentLevel] ?? 2;
  const colIdx = SIGNAL_MAP[signalLevel] ?? 3;

  return (
    <div className={clsx('space-y-1', className)}>
      {/* 列标题 */}
      <div className="flex items-center">
        <div className="w-10 shrink-0" />
        {COLS.map((col) => (
          <div
            key={col}
            className={clsx(
              'flex-1 text-center text-[10px] font-bold py-1 rounded',
              SIGNAL_MAP[col] === colIdx && 'bg-brand-100 text-brand-700'
            )}
            style={SIGNAL_MAP[col] !== colIdx ? { color: SIGNAL_COLORS[col] || '#94A3B8' } : undefined}
          >
            {col}
          </div>
        ))}
      </div>

      {/* 矩阵行 */}
      {MATRIX.map((row, ri) => (
        <div key={ri} className="flex items-center">
          <div className={clsx(
            'w-10 shrink-0 text-[10px] text-right pr-1',
            ri === rowIdx && 'font-bold text-gray-700'
          )}>
            {ROWS[ri]}
          </div>
          {row.map((cell, ci) => {
            const isCurrent = ri === rowIdx && ci === colIdx;
            const isTarget = ri === rowIdx;
            const cellColor = CELL_COLORS[cell] || '#94A3B8';
            return (
              <div
                key={ci}
                className={clsx(
                  'flex-1 text-center text-[10px] py-1.5 mx-0.5 rounded border transition-all',
                  isCurrent
                    ? 'border-brand-500 ring-2 ring-brand-200 font-bold'
                    : 'border-gray-100',
                  isTarget && !isCurrent && 'border-brand-300'
                )}
                style={{
                  backgroundColor: isCurrent ? cellColor + '30' : cellColor + '10',
                  color: cellColor,
                }}
                title={`${ROWS[ri]} × ${COLS[ci]} → ${cell}`}
              >
                {isCurrent ? cell : ''}
              </div>
            );
          })}
        </div>
      ))}

      {/* 图例 */}
      <div className="flex items-center gap-3 mt-2 justify-center">
        {Object.entries(CELL_COLORS).map(([label, color]) => (
          <div key={label} className="flex items-center gap-1">
            <div className="w-2 h-2 rounded" style={{ backgroundColor: color }} />
            <span className="text-[9px] text-gray-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};
