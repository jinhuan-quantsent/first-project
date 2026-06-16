import type { ModelParams } from '../../api/backtest';
import { RangeSlider } from './RangeSlider';
import { FACTOR_LABELS, FACTOR_NAMES } from '../../utils/paramsMapper';

/** Category 4: 因子引擎 */
export function FactorEnginePanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  const sigmoidK = params.sigmoid_k;

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400">因子引擎参数，与后端 config.py V5_FACTOR_CONFIG 对齐</p>
      <RangeSlider label="分位数窗口" value={params.quantile_window} min={252} max={2520} step={252} unit="天"
        onChange={v => onChange({ ...params, quantile_window: v })} />

      {/* 每因子 Sigmoid K 值 */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">📐 Sigmoid 陡峭度（每因子）</p>
        <div className="space-y-0.5 max-h-40 overflow-y-auto">
          {FACTOR_NAMES.map(name => (
            <div key={name} className="flex items-center gap-2">
              <span className="w-16 shrink-0 text-[10px] text-gray-500 truncate">{FACTOR_LABELS[name]}</span>
              <input
                type="range"
                min={0.5}
                max={8}
                step={0.5}
                value={sigmoidK[name] ?? 3.0}
                onChange={e => onChange({
                  ...params,
                  sigmoid_k: { ...sigmoidK, [name]: parseFloat(e.target.value) },
                })}
                className="flex-1 h-1 accent-brand-500"
              />
              <span className="w-6 text-right text-[10px] text-gray-400 font-mono">
                {sigmoidK[name]?.toFixed(1) ?? '3.0'}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span className="w-24 shrink-0 text-gray-500 text-xs">聚合方式</span>
        <select value={params.composite_method}
          onChange={e => onChange({ ...params, composite_method: e.target.value })}
          className="flex-1 px-2 py-0.5 border border-gray-200 rounded text-xs bg-white">
          <option value="weighted_sum">加权求和 (weighted_sum)</option>
          <option value="geometric_mean">几何平均 (geometric_mean)</option>
        </select>
      </div>
      <RangeSlider label="中性分数" value={params.neutral_score} min={30} max={70} step={1}
        onChange={v => onChange({ ...params, neutral_score: v })} />
    </div>
  );
}
