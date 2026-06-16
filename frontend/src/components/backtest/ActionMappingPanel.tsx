import type { ModelParams, ActionRule } from '../../api/backtest';
import { SIGNAL_LEVELS, SIGNAL_BG, ACTION_TYPE_OPTIONS, DEFAULT_ACTION_MAPPING } from './constants';

/** Category 3: 行动映射 */
export function ActionMappingPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs text-gray-400">7级信号 → 行动类型 + 操作倍数</p>
      {SIGNAL_LEVELS.map(sig => {
        const rule = params.action_mapping[sig] || DEFAULT_ACTION_MAPPING[sig];
        return (
          <div key={sig} className="flex items-center gap-2 text-xs">
            <span className={`px-1.5 py-0.5 text-xs font-bold rounded ${SIGNAL_BG[sig]}`}>{sig}</span>
            <select value={rule.type}
              onChange={e => {
                const newType = e.target.value as ActionRule['type'];
                const autoLabel = ACTION_TYPE_OPTIONS.find(o => o.value === newType)?.label || '';
                const newMapping = { ...params.action_mapping, [sig]: { ...rule, type: newType, label: autoLabel } };
                onChange({ ...params, action_mapping: newMapping });
              }}
              className="px-2 py-0.5 border border-gray-200 rounded text-xs bg-white">
              {ACTION_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <input type="range" min={0} max={3} step={0.1} value={rule.mult}
              onChange={e => {
                const newMapping = { ...params.action_mapping, [sig]: { ...rule, mult: parseFloat(e.target.value) } };
                onChange({ ...params, action_mapping: newMapping });
              }}
              className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                         [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                         [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
            <span className="w-6 text-right text-xs font-mono text-gray-400 tabular-nums">{rule.mult.toFixed(1)}</span>
            <span className="w-14 text-xs text-gray-500">{rule.label}</span>
          </div>
        );
      })}
    </div>
  );
}
