import type { ModelParams } from '../../../api/backtest';
import { SIGNAL_LEVELS, SIGNAL_BG, SIGNAL_LABELS } from './constants';
import { RangeSlider } from './RangeSlider';

/** Category 1: 信号映射 */
export function SignalMappingPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400">调整6个信号分界线，分数低于边界→对应信号</p>
      {params.signal_boundaries.map((v, i) => {
        const sig = SIGNAL_LEVELS[i];
        return (
          <div key={i} className="flex items-center gap-2">
            <span className={`px-1.5 py-0.5 text-xs font-bold rounded ${SIGNAL_BG[sig]}`}>{sig}</span>
            <span className="text-[10px] text-gray-400 w-12">{SIGNAL_LABELS[sig]}</span>
            <input type="range" min={0} max={100} step={1} value={v}
              onChange={e => {
                const next = [...params.signal_boundaries];
                next[i] = parseInt(e.target.value);
                onChange({ ...params, signal_boundaries: next });
              }}
              className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                         [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                         [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
            <span className="w-8 text-right text-xs font-mono text-gray-600 tabular-nums">{v}</span>
          </div>
        );
      })}
      <div className="pt-1 border-t border-gray-100">
        <RangeSlider label="信号滞后天数" value={params.signal_lag_days} min={0} max={5} step={1} unit="天"
          onChange={v => onChange({ ...params, signal_lag_days: v })} />
      </div>
    </div>
  );
}
