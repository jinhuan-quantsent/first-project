import type { ModelParams } from '../../../api/backtest';
import { RangeSlider } from './RangeSlider';

/** Category 4: 因子引擎 */
export function FactorEnginePanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400">全局因子引擎参数，替代每因子单独Sigmoid设置</p>
      <RangeSlider label="分位数窗口" value={params.quantile_window} min={60} max={504} step={1} unit="天"
        onChange={v => onChange({ ...params, quantile_window: v })} />
      <RangeSlider label="Sigmoid陡峭度" value={params.sigmoid_k} min={0.5} max={10} step={0.5}
        onChange={v => onChange({ ...params, sigmoid_k: v })} />
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
