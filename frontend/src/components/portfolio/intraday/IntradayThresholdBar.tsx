/**
 * IntradayThresholdBar -- 阈值进度条（重点创新组件）
 * 
 * 可视化展示：
 * - 当前情绪分位置（蓝色指针）
 * - 闸门触发区间（红色/橙色区域标记）
 * - 安全区间标注
 * - 向上/向下触发阈值百分比
 */
import React from 'react';
import { IntradayThresholdData, IntradayGateZone } from '../types';

interface Props {
  thresholds: IntradayThresholdData;
  previewScore: number;
  yesterdayScore: number;
}

export default function IntradayThresholdBar({ thresholds, previewScore, yesterdayScore }: Props) {
  const { gate_zones, safe_zone_note, up_trigger_pct, down_trigger_pct } = thresholds;

  // 闸门颜色映射
  const GATE_COLORS: Record<string, { triggered: string; safe: string; label: string }> = {
    'gate-p': { triggered: '#DC2626', safe: '#FCA5A5', label: '恐慌闸门' },
    'gate-1': { triggered: '#EA580C', safe: '#FDBA74', label: '回撤闸门' },
    'gate-2': { triggered: '#D97706', safe: '#FDE68A', label: '趋势闸门' },
    'gate-e': { triggered: '#7C3AED', safe: '#C4B5FD', label: '过热闸门' },
  };

  return (
    <div className="rounded-lg border border-dashed border-blue-200 bg-[#EFF6FF] p-3">
      {/* 标题 */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold text-blue-700">阈值进度条</span>
        <span className="text-xs text-gray-500">{safe_zone_note}</span>
      </div>

      {/* 进度条本体 */}
      <div className="relative h-6 bg-gray-100 rounded-full overflow-hidden">
        {/* 闸门区间标记 */}
        {gate_zones.map((zone) => {
          const colors = GATE_COLORS[zone.id] || { triggered: '#999', safe: '#ddd', label: zone.id };
          const pos = zone.position;
          
          if (zone.triggered) {
            // 闸门已触发：全条高亮
            return (
              <div
                key={zone.id}
                className="absolute top-0 h-full opacity-30"
                style={{
                  left: '0%',
                  right: '0%',
                  backgroundColor: colors.triggered,
                }}
              />
            );
          }

          if (pos !== null && pos !== undefined) {
            // 闸门价位映射到进度条
            const barPos = Math.max(0, Math.min(100, 50 + pos * 3));
            return (
              <div
                key={zone.id}
                className="absolute top-0 h-1 rounded"
                style={{
                  left: `${barPos}%`,
                  width: '2px',
                  backgroundColor: colors.safe,
                  transform: 'translateX(-1px)',
                }}
                title={`${colors.label}: ${zone.triggered ? '已触发' : '未触发'} ${zone.current_distance_pct ? `距${zone.current_distance_pct}%` : ''}`}
              />
            );
          }

          return null;
        })}

        {/* 当前情绪分指针 */}
        <div
          className="absolute top-0 h-full w-1 bg-blue-500 rounded shadow-sm z-10"
          style={{ left: `${Math.max(0, Math.min(100, previewScore))}%`, transform: 'translateX(-0.5px)' }}
          title={`盘中预演: ${previewScore.toFixed(1)}分`}
        />

        {/* 昨日情绪分指针（灰色） */}
        <div
          className="absolute top-0 h-full w-1 bg-gray-400 rounded opacity-60 z-5"
          style={{ left: `${Math.max(0, Math.min(100, yesterdayScore))}%`, transform: 'translateX(-0.5px)' }}
          title={`昨日收盘: ${yesterdayScore.toFixed(1)}分`}
        />

        {/* 信号边界刻度线 */}
        {[12, 25, 38, 52, 65, 80].map((b) => (
          <div
            key={b}
            className="absolute top-0 h-full w-px bg-gray-300 opacity-40"
            style={{ left: `${b}%` }}
          />
        ))}
      </div>

      {/* 刻度标注 */}
      <div className="flex justify-between mt-1 text-xs text-gray-400">
        <span>0 (S+)</span>
        <span>25 (S)</span>
        <span>38 (A)</span>
        <span>52 (B)</span>
        <span>65 (C)</span>
        <span>80 (D)</span>
        <span>100 (E)</span>
      </div>

      {/* 闸门状态列表 */}
      <div className="mt-2 space-y-1">
        {gate_zones.map((zone) => {
          const colors = GATE_COLORS[zone.id] || { triggered: '#999', safe: '#ddd', label: zone.id };
          return (
            <div key={zone.id} className="flex items-center gap-2 text-xs">
              <span
                className={`inline-block w-2 h-2 rounded-full ${zone.triggered ? 'ring-2 ring-offset-1' : ''}`}
                style={{ backgroundColor: zone.triggered ? colors.triggered : colors.safe }}
              />
              <span className={zone.triggered ? 'font-semibold text-red-700' : 'text-gray-600'}>
                {zone.label}
              </span>
              {zone.triggered && <span className="text-red-600 font-medium">⚠ 已触发</span>}
              {zone.exempted && <span className="text-amber-600">(逆向豁免)</span>}
              {zone.status_text && !zone.triggered && (
                <span className={zone.current_distance_pct !== null && zone.current_distance_pct !== undefined && zone.current_distance_pct < 0 ? 'text-red-500 font-medium' : 'text-gray-400'}>
                  {zone.status_text}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* 触发阈值 */}
      {(up_trigger_pct || down_trigger_pct) && (
        <div className="mt-2 flex gap-4 text-xs">
          {up_trigger_pct && (
            <span className="text-emerald-600">
              ↗ 升级需涨 {up_trigger_pct}%
            </span>
          )}
          {down_trigger_pct && (
            <span className="text-red-600">
              ↘ 降级需跌 {down_trigger_pct}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
