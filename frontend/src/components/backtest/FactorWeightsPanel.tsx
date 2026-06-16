import { useMemo } from 'react';
import type { ModelParams } from '../../../api/backtest';
import { FACTOR_NAMES, FACTOR_LABELS } from './constants';

/** Category 2: 因子权重 */
export function FactorWeightsPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  const enabledWeight = useMemo(() => {
    return FACTOR_NAMES.reduce((sum, n) => {
      return sum + (params.factor_enabled[n] ? (params.factor_weights[n] || 0) : 0);
    }, 0);
  }, [params]);

  return (
    <div className="space-y-1.5">
      <p className="text-xs text-gray-400">开关因子 + 滑块调节权重，有效权重总和应≈1.0</p>
      {FACTOR_NAMES.map(name => {
        const enabled = params.factor_enabled[name] ?? true;
        const weight = params.factor_weights[name] ?? parseFloat((1 / FACTOR_NAMES.length).toFixed(3));
        return (
          <div key={name} className={`flex items-center gap-2 text-xs ${!enabled ? 'opacity-40' : ''}`}>
            <button onClick={() => onChange({ ...params, factor_enabled: { ...params.factor_enabled, [name]: !enabled } })}
              className={`w-7 h-4 rounded-full transition-colors relative ${enabled ? 'bg-brand-500' : 'bg-gray-300'}`}>
              <span className={`absolute top-0.5 ${enabled ? 'right-0.5' : 'left-0.5'} w-3 h-3 bg-white rounded-full shadow transition-all`} />
            </button>
            <span className="w-8 shrink-0 font-mono text-xs text-gray-500">{name}</span>
            <span className="w-12 shrink-0 text-xs text-gray-600">{FACTOR_LABELS[name]}</span>
            <input type="range" min={0} max={0.5} step={0.005} value={weight}
              disabled={!enabled}
              onChange={e => onChange({ ...params, factor_weights: { ...params.factor_weights, [name]: parseFloat(e.target.value) } })}
              className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500 disabled:opacity-30
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                         [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                         [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
            <span className="w-10 text-right text-xs font-mono text-gray-400 tabular-nums">{weight.toFixed(3)}</span>
          </div>
        );
      })}
      <p className="text-xs text-gray-400 pt-1 border-t border-gray-100">
        有效总和：
        <span className={`font-mono ${Math.abs(enabledWeight - 1.0) > 0.05 ? 'text-red-500 font-bold' : 'text-green-500'}`}>
          {enabledWeight.toFixed(3)}
        </span>
      </p>
    </div>
  );
}
