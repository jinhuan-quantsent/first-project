/**
 * 因子热力图组件 — V5.0
 * 显示11因子的 Sigmoid 分数热力图
 */
import { clsx } from 'clsx';

interface FactorHeatmapProps {
  factors: {
    factor_name: string;
    label: string;
    sigmoid_score: number;
    direction: string;
    weight: number;
  }[];
  className?: string;
}

const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

function scoreToColor(score: number): string {
  if (score < 20) return SIGNAL_COLORS['S+'];
  if (score < 30) return SIGNAL_COLORS['S'];
  if (score < 40) return SIGNAL_COLORS['A'];
  if (score < 55) return SIGNAL_COLORS['B'];
  if (score < 70) return SIGNAL_COLORS['C'];
  if (score < 80) return SIGNAL_COLORS['D'];
  return SIGNAL_COLORS['E'];
}

function scoreToSignal(score: number): string {
  if (score < 20) return 'S+';
  if (score < 30) return 'S';
  if (score < 40) return 'A';
  if (score < 55) return 'B';
  if (score < 70) return 'C';
  if (score < 80) return 'D';
  return 'E';
}

export default function FactorHeatmap({ factors, className }: FactorHeatmapProps) {
  return (
    <div className={clsx('grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2', className)}>
      {factors.map((f) => {
        const color = scoreToColor(f.sigmoid_score);
        const signal = scoreToSignal(f.sigmoid_score);
        return (
          <div
            key={f.factor_name}
            className="rounded-lg p-2.5 text-center border border-gray-100"
            style={{ backgroundColor: color + '15' }}
          >
            <p className="text-[10px] text-gray-400">{f.label}</p>
            <p className="text-xs font-bold mt-0.5" style={{ color }}>
              {f.sigmoid_score.toFixed(1)}
            </p>
            <div className="flex items-center justify-center gap-1 mt-0.5">
              <span className="text-[10px] font-bold" style={{ color }}>
                {signal}
              </span>
              <span className={clsx(
                'text-[8px] px-0.5 rounded',
                f.direction === 'fear'
                  ? 'bg-red-100 text-red-500'
                  : 'bg-green-100 text-green-500'
              )}>
                {f.direction === 'fear' ? '恐' : '贪'}
              </span>
            </div>
            <p className="text-[9px] text-gray-300 mt-0.5">w={f.weight}</p>
          </div>
        );
      })}
    </div>
  );
}
