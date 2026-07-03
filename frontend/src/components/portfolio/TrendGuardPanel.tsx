/**
 * TrendGuardPanel — 趋势卫士面板组件
 * V5.1: Gate1/2/E 结构化叠加展示 + 距离文字
 */
import { useMemo } from 'react';
import { Shield, TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import type { PositionDetailData, GateStructure } from './types';
import { getOverallStatus } from './types';

export default function TrendGuardPanel({ tg }: { tg: NonNullable<PositionDetailData['trendGuard']> }) {
  // 趋势方向图标和颜色
  const trendConfig = {
    '上升': { icon: TrendingUp, color: 'text-red-500', bg: 'bg-red-50', label: '上升趋势' },
    '下降': { icon: TrendingDown, color: 'text-green-500', bg: 'bg-green-50', label: '下降趋势' },
    '震荡': { icon: Minus, color: 'text-gray-500', bg: 'bg-gray-50', label: '震荡整理' },
  };
  const tc = trendConfig[tg.trend_signal as keyof typeof trendConfig] || trendConfig['震荡'];
  const TrendIcon = tc.icon;

  // MACD信号配置（6状态 + 兜底，中国惯例：红涨绿跌）
  const macdConfig = {
    '金叉':     { color: 'text-red-500',   bg: 'bg-red-50',   icon: '🔥', label: 'MACD金叉（趋势转多）' },
    '多头':     { color: 'text-red-500',   bg: 'bg-red-50',   icon: '📈', label: 'MACD多头运行' },
    '多头收敛': { color: 'text-amber-500', bg: 'bg-amber-50', icon: '⚡', label: 'MACD多头收敛（动能减弱）' },
    '死叉':     { color: 'text-green-500', bg: 'bg-green-50', icon: '💀', label: 'MACD死叉（趋势转空）' },
    '空头':     { color: 'text-green-500', bg: 'bg-green-50', icon: '📉', label: 'MACD空头运行' },
    '空头收敛': { color: 'text-teal-500',  bg: 'bg-teal-50',  icon: '🌱', label: 'MACD空头收敛（可能见底）' },
    '中性':     { color: 'text-gray-400',  bg: 'bg-gray-100', icon: '➖', label: '数据不足' },
  };
  const mc = macdConfig[tg.macd_signal as keyof typeof macdConfig] || macdConfig['中性'];

  // 结构化 Gate 数据
  const gates = tg.gates;
  const g1 = gates?.gate_1;
  const g2 = gates?.gate_2;
  const ge = gates?.gate_e;
  const overallStatus = getOverallStatus(gates);

  // Gate 距离文字格式化
  const fmtGateDist = (triggered: boolean | undefined, distPct: number | undefined, triggerPrice: number | null | undefined, label: string) => {
    if (triggered) return <span className="text-red-600 font-semibold">已触发</span>;
    if (distPct != null && triggerPrice != null) return <span className="text-gray-500">{label} {triggerPrice.toFixed(4)}（距触发 {distPct > 0 ? '+' : ''}{distPct.toFixed(1)}%）</span>;
    if (triggerPrice != null) return <span className="text-gray-500">{label} {triggerPrice.toFixed(4)}</span>;
    return null;
  };

  const anyGateTriggered = g1?.triggered || (g2?.triggered && !g2?.exempted) || ge?.triggered;

  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-3 space-y-2.5 border border-blue-100/50">
      {/* 标题行 */}
      <div className="flex items-center gap-2">
        <Shield className="w-3.5 h-3.5 text-blue-500" />
        <span className="text-xs font-medium text-gray-700">趋势卫士解读</span>
        <span className={clsx(
          'text-[10px] px-1.5 py-0.5 rounded font-medium ml-auto',
          overallStatus === 'stop_loss' ? 'bg-red-100 text-red-700' :
          overallStatus === 'warning' ? 'bg-amber-100 text-amber-700' :
          'bg-emerald-100 text-emerald-700'
        )}>
          {overallStatus === 'stop_loss' ? '🔴 止损线生效' :
           overallStatus === 'warning' ? '🟡 风险预警' : '🟢 风控正常'}
        </span>
      </div>

      {/* 趋势方向 + MACD信号 并排 */}
      <div className="grid grid-cols-2 gap-2">
        <div className={clsx('rounded-md p-2 flex items-center gap-2', tc.bg)}>
          <TrendIcon className={clsx('w-4 h-4 shrink-0', tc.color)} />
          <div className="min-w-0">
            <p className="text-[10px] text-gray-400">MA20趋势</p>
            <p className={clsx('text-xs font-bold', tc.color)}>{tc.label}</p>
          </div>
        </div>
        <div className={clsx('rounded-md p-2 flex items-center gap-2', mc.bg)}>
          <div className="min-w-0">
            <p className="text-[10px] text-gray-400">MACD指标</p>
            <p className={clsx('text-xs font-bold', mc.color)}>{mc.icon ? mc.icon + ' ' : ''}{mc.label}</p>
            {/* 新增：详情子行（仅在非 data_short 时显示） */}
            {tg.macd_detail && tg.macd_detail.reason !== 'data_short' && (
              <p className="text-[10px] text-gray-400 mt-0.5">
                第{tg.macd_detail.days}天 · 动能{tg.macd_detail.strength} · {tg.macd_detail.trend}
                {tg.macd_detail.last_cross_type && (
                  <> · {tg.macd_detail.last_cross_type === 'gold' ? '金叉' : '死叉'}{tg.macd_detail.last_cross_days}天前</>
                )}
              </p>
            )}
            {/* 新增：数据不足提示 */}
            {tg.macd_detail && tg.macd_detail.reason === 'data_short' && (
              <p className="text-[10px] text-gray-400 mt-0.5">净值数据不足，无法计算MACD</p>
            )}
          </div>
        </div>
      </div>

      {/* 震荡市静音状态 */}
      {tg.oscillation_silence && (
        <div className="flex items-center gap-2 bg-amber-50 rounded-md p-1.5">
          <Minus className="w-3 h-3 text-amber-500 shrink-0" />
          <span className="text-[10px] text-amber-700">震荡市静音：当前为震荡市，建议持仓观望，避免频繁交易</span>
        </div>
      )}

      {/* Gate1/2/E 结构化叠加展示 */}
      {anyGateTriggered ? (
        <div className="space-y-1.5">
          {g1?.triggered && (
            <div className={clsx('rounded-md p-2 flex items-center gap-2 bg-red-50')}>
              <AlertTriangle className="w-3.5 h-3.5 text-red-600 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-bold text-red-700">
                  止损线触发：回撤{(g1.drawdown ? (g1.drawdown * 100).toFixed(1) : '?')}%≥20%
                </p>
                {g1.trigger_price != null && (
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    触发价 {g1.trigger_price.toFixed(4)} {g1.current_distance_pct != null && `（距触发 ${g1.current_distance_pct > 0 ? '+' : ''}${g1.current_distance_pct.toFixed(1)}%）`}
                  </p>
                )}
              </div>
            </div>
          )}
          {g2?.triggered && !g2?.exempted && (
            <div className={clsx('rounded-md p-2 flex items-center gap-2 bg-red-50')}>
              <AlertTriangle className="w-3.5 h-3.5 text-red-600 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-bold text-red-700">趋势破位触发：跌破MA20</p>
                {g2.trigger_price != null && (
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    MA20价位 {g2.trigger_price.toFixed(4)} {g2.current_distance_pct != null && `（距触发 ${g2.current_distance_pct > 0 ? '+' : ''}${g2.current_distance_pct.toFixed(1)}%）`}
                  </p>
                )}
              </div>
            </div>
          )}
          {g2?.triggered && g2?.exempted && (
            <div className="rounded-md p-2 flex items-center gap-2 bg-gray-50">
              <Minus className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-600">MA20破位豁免（逆向轨道）</p>
                {g2.exempt_reason && <p className="text-[10px] text-gray-400 mt-0.5">{g2.exempt_reason}</p>}
              </div>
            </div>
          )}
          {ge?.triggered && (
            <div className="rounded-md p-2 flex items-center gap-2 bg-amber-50">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
              <div className="min-w-0">
                <p className="text-xs font-bold text-amber-700">过热预警：情绪过热，建议持有观望</p>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-md p-2 flex items-center gap-2 bg-emerald-50">
          <Shield className="w-3.5 h-3.5 shrink-0 text-emerald-500" />
          <span className="text-xs font-medium text-emerald-600">三阶闸门未触发（安全）</span>
          {(g1 || g2) && (
            <div className="ml-auto flex flex-wrap gap-x-2 text-[9px]">
              {g1 && !g1.triggered && g1.trigger_price != null && (
                <span className="text-gray-500">止损线 {g1.trigger_price.toFixed(4)}</span>
              )}
              {g2 && !g2.triggered && g2.trigger_price != null && (
                <span className="text-gray-500">MA20 {g2.trigger_price.toFixed(4)}</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* 操作建议 */}
      {tg.operation_suggestion && (
        <div className="flex items-start gap-2 bg-white/60 rounded-md p-2">
          <span className="text-[10px] text-gray-400 shrink-0 mt-0.5">操作建议</span>
          <span className="text-xs text-gray-700 font-medium leading-relaxed">{tg.operation_suggestion}</span>
        </div>
      )}

      {/* 趋势解读文案 */}
      {tg.trend_narrative && (
        <div className="flex items-start gap-2 bg-white/60 rounded-md p-2">
          <span className="text-[10px] text-gray-400 shrink-0 mt-0.5">综合解读</span>
          <span className="text-xs text-blue-600 font-medium leading-relaxed">{tg.trend_narrative}</span>
        </div>
      )}
    </div>
  );
}
