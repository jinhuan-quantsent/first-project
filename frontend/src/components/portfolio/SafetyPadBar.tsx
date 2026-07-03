/**
 * SafetyPadBar — 安全垫可视化进度条组件
 * V5.1: 结构化 Gate 数据 + 距离文字
 */
import { clsx } from 'clsx';
import type { PositionDetailData, GateStructure } from './types';

interface SafetyPadBarProps {
  data: PositionDetailData;
}

export default function SafetyPadBar({ data }: SafetyPadBarProps) {
  const currentPct = data.currentPositionPct != null ? data.currentPositionPct / 100 : (data.totalAssets ? data.marketValue / data.totalAssets : 0);  // V5.1 fix: API发送×100格式(0.16=0.16%%)，需/100转回0-1小数，与targetPct一致
  const targetPct = data.targetPositionPct! / 100;
  const gates = data.trendGuard?.gates;
  const g1 = gates?.gate_1;
  const g2 = gates?.gate_2;
  const ge = gates?.gate_e;
  const isClearLine = (g1?.triggered) || (g2?.triggered && !g2?.exempted);
  const isOverTarget = currentPct > targetPct;
  const clampedCurrent = Math.min(currentPct, 1);
  const clampedTarget = Math.min(targetPct, 1);

  // Gate 距离文字格式化
  const fmtGateDist = (triggered: boolean | undefined, distPct: number | undefined, triggerPrice: number | null | undefined, label: string) => {
    if (triggered) return <span className="text-red-600 font-semibold">已触发</span>;
    if (distPct != null && triggerPrice != null) return <span className="text-gray-500">{label} {triggerPrice.toFixed(4)}（距触发 {distPct > 0 ? '+' : ''}{distPct.toFixed(1)}%）</span>;
    if (triggerPrice != null) return <span className="text-gray-500">{label} {triggerPrice.toFixed(4)}</span>;
    return null;
  };

  return (
    <div className="bg-white/60 rounded-md p-2 mt-1">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[10px] text-gray-400">安全垫可视化</span>
        {isClearLine && <span className="text-[10px] text-red-600 font-semibold">⚠ Gate清仓线生效</span>}
        {isOverTarget && <span className="text-[10px] text-red-600 font-semibold">⚠ 超目标仓位</span>}
      </div>
      {/* 进度条 */}
      <div className="relative h-4 bg-gray-100 rounded-full">
        <div
          className={clsx('absolute h-full rounded-full transition-all', isOverTarget ? 'bg-red-300' : 'bg-teal-400')}
          style={{ width: `${Math.max(clampedTarget, 0.02) * 100}%`, left: '0' }}
        />
        <div
          className="absolute h-5 w-[2px] bg-gray-800 -top-[2px] rounded-sm shadow-sm z-10 transition-all"
          style={{ left: `${clampedCurrent * 100}%` }}
        />
        {g1?.triggered && (
          <div className="absolute h-5 w-0 border-l-2 border-red-500 -top-[2px] z-20" style={{ left: '0%' }} />
        )}
        {g2?.triggered && !g2?.exempted && (
          <div className="absolute h-5 w-0 border-l-2 border-red-500 -top-[2px] z-20" style={{ left: '0%' }} />
        )}
      </div>
      {/* 标注行 */}
      <div className="flex items-center justify-between mt-1 text-[9px]">
        <span className={clsx('text-gray-500', isClearLine && 'text-red-600 font-semibold')}>
          {isClearLine ? '清仓线 0%' : '0%'}
        </span>
        <span className={clsx('font-mono', isOverTarget ? 'text-red-600 font-bold' : 'text-gray-700')}>
          当前 {(currentPct * 100).toFixed(1)}%
        </span>
        <span className="text-teal-600 font-mono">
          目标 {(targetPct * 100).toFixed(1)}%
        </span>
        <span className="text-gray-400">100%</span>
      </div>
      {/* Gate距离文字展示 */}
      {(g1 || g2 || ge) && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[9px]">
          {g1 && fmtGateDist(g1.triggered, g1.current_distance_pct, g1.trigger_price, '止损线')}
          {g2?.triggered && !g2?.exempted && fmtGateDist(true, g2.current_distance_pct, g2.trigger_price, '趋势破位')}
          {g2?.exempted && <span className="text-gray-400">MA20破位豁免(逆向轨道)</span>}
          {!g2?.triggered && !g2?.exempted && g2 && fmtGateDist(false, g2.current_distance_pct, g2.trigger_price, 'MA20线')}
          {ge?.triggered && <span className="text-amber-600">情绪过热预警</span>}
        </div>
      )}
    </div>
  );
}
