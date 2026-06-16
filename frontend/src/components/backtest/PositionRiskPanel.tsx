import type { ModelParams } from '../../api/backtest';
import { RangeSlider } from './RangeSlider';

/** Category 5: 仓位风控 */
export function PositionRiskPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  const u = (key: keyof ModelParams, v: number) => onChange({ ...params, [key]: v });
  return (
    <div className="space-y-3">
      {/* 仓位限制 */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">📏 仓位限制</p>
        <RangeSlider label="最大仓位" value={params.max_position} min={0.5} max={1.0} step={0.05} unit=""
          onChange={v => u('max_position', v)} />
        <div className="mt-1">
          <RangeSlider label="最小仓位" value={params.min_position} min={0} max={0.3} step={0.05} unit=""
            onChange={v => u('min_position', v)} />
        </div>
      </div>

      {/* 回撤加仓（替代原止损——基金回撤时应加仓而非清仓） */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">🛡️ 回撤加仓</p>
        <RangeSlider label="加仓触发线" value={params.pullback_add} min={-0.30} max={-0.05} step={0.01} unit=""
          onChange={v => u('pullback_add', v)} />
        <div className="mt-1"><RangeSlider label="加仓比例" value={params.pullback_add_pct} min={0.05} max={0.50} step={0.05} unit=""
          onChange={v => u('pullback_add_pct', v)} /></div>
      </div>

      {/* 止盈 */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">💰 止盈</p>
        <RangeSlider label="止盈线" value={params.take_profit} min={0.10} max={1.0} step={0.05} unit=""
          onChange={v => u('take_profit', v)} />
        <div className="mt-1"><RangeSlider label="止盈回撤触发" value={params.take_profit_drawdown} min={0.03} max={0.30} step={0.01} unit=""
          onChange={v => u('take_profit_drawdown', v)} /></div>
      </div>

      {/* 过热 */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">🔥 过热检测</p>
        <RangeSlider label="连续天数" value={params.overheat_days} min={3} max={30} step={1} unit="天"
          onChange={v => u('overheat_days', v)} />
        <div className="mt-1"><RangeSlider label="减仓系数" value={params.overheat_factor} min={0.3} max={1.0} step={0.05}
          onChange={v => u('overheat_factor', v)} /></div>
      </div>

      {/* 回调/偏离 */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">📉 回调/偏离加仓</p>
        <RangeSlider label="回调下限" value={params.pullback_lower} min={-0.20} max={-0.02} step={0.01}
          onChange={v => u('pullback_lower', v)} />
        <div className="mt-1"><RangeSlider label="回调加仓倍数" value={params.pullback_buy_mult} min={0.1} max={1.0} step={0.1}
          onChange={v => u('pullback_buy_mult', v)} /></div>
        <div className="mt-1"><RangeSlider label="偏离下限" value={params.position_dev_lower} min={-0.20} max={-0.01} step={0.01}
          onChange={v => u('position_dev_lower', v)} /></div>
        <div className="mt-1"><RangeSlider label="偏离加仓倍数" value={params.position_dev_buy_mult} min={0.1} max={1.0} step={0.1}
          onChange={v => u('position_dev_buy_mult', v)} /></div>
      </div>

      {/* 基础金额 */}
      <div>
        <p className="text-xs text-gray-500 font-medium mb-1">💵 基础金额</p>
        <RangeSlider label="单次加仓金额" value={params.base_buy_amount} min={1000} max={50000} step={1000} unit="元"
          onChange={v => u('base_buy_amount', v)} />
      </div>
    </div>
  );
}
