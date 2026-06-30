/**
 * EquityChart — ECharts 权益曲线共享组件
 * 替代 BacktestResultPanel / DailyTrackingResultPanel 中的手绘 SVG
 */
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DataZoomComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart, GridComponent, TooltipComponent, LegendComponent,
  MarkLineComponent, DataZoomComponent, CanvasRenderer,
]);

interface CurvePoint {
  date: string;
  value: number;
  position_pct?: number;
  signal_level?: string;
}

interface EquityChartProps {
  /** 策略曲线 */
  curve: CurvePoint[];
  /** 基准曲线 */
  benchmarkCurve?: CurvePoint[];
  /** 操作标记（加仓/减仓日） */
  actionMarkers?: { date: string; type: 'buy' | 'sell' }[];
  /** 高度 px */
  height?: number;
}

/** 日期格式化：20260115 → 2026-01-15 */
function fmtDate(d: string) {
  if (d.length === 8) return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  return d;
}

export function EquityChart({ curve, benchmarkCurve, actionMarkers, height = 280 }: EquityChartProps) {
  if (!curve || curve.length < 2) {
    return (
      <div className="flex items-center justify-center text-gray-400 text-xs" style={{ height }}>
        暂无曲线数据
      </div>
    );
  }

  const dates = curve.map(p => fmtDate(p.date));
  const strategyValues = curve.map(p => p.value);
  const benchmarkValues = benchmarkCurve?.map(p => p.value) ?? [];

  // 操作标记线
  const buyMarkLines = actionMarkers
    ?.filter(m => m.type === 'buy')
    .map(m => {
      const idx = dates.indexOf(fmtDate(m.date));
      return idx >= 0 ? { xAxis: idx } : null;
    })
    .filter(Boolean) ?? [];

  const sellMarkLines = actionMarkers
    ?.filter(m => m.type === 'sell')
    .map(m => {
      const idx = dates.indexOf(fmtDate(m.date));
      return idx >= 0 ? { xAxis: idx } : null;
    })
    .filter(Boolean) ?? [];

  const option: Record<string, unknown> = {
    animation: true,
    animationDuration: 600,
    grid: { left: 50, right: 20, top: 30, bottom: actionMarkers ? 60 : 40 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#E5E7EB',
      textStyle: { color: '#374151', fontSize: 11 },
      formatter: (params: Array<{ seriesName: string; value: number; dataIndex: number }>) => {
        const idx = params[0]?.dataIndex ?? 0;
        const date = dates[idx] ?? '';
        let html = `<div style="font-weight:600;margin-bottom:2px">${date}</div>`;
        for (const p of params) {
          const color = p.seriesName === '策略' ? '#14B8A6' : '#94A3B8';
          html += `<div><span style="color:${color}">●</span> ${p.seriesName}: ¥${p.value?.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</div>`;
        }
        return html;
      },
    },
    legend: {
      data: benchmarkValues.length > 0 ? ['策略', '基准'] : ['策略'],
      top: 4,
      right: 20,
      textStyle: { fontSize: 11, color: '#9CA3AF' },
      itemWidth: 16,
      itemHeight: 2,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#E5E7EB' } },
      axisTick: { show: false },
      axisLabel: {
        fontSize: 9,
        color: '#9CA3AF',
        formatter: (v: string) => v.slice(5), // 只显示 MM-DD
      },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#F3F4F6' } },
      axisLabel: {
        fontSize: 9,
        color: '#9CA3AF',
        formatter: (v: number) => v >= 10000 ? `${(v / 10000).toFixed(1)}万` : v.toFixed(0),
      },
    },
    dataZoom: dates.length > 60 ? [{
      type: 'inside',
      start: Math.max(0, 100 - 60 / dates.length * 100),
      end: 100,
    }] : undefined,
    series: [
      {
        name: '策略',
        type: 'line',
        data: strategyValues,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#14B8A6', width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(20,184,166,0.25)' },
            { offset: 1, color: 'rgba(20,184,166,0.02)' },
          ]),
        },
        markLine: buyMarkLines.length > 0 || sellMarkLines.length >  0 ? {
          silent: true,
          symbol: 'none',
          lineStyle: { width: 1 },
          data: [
            ...buyMarkLines.map(ml => ({
              ...ml,
              lineStyle: { color: '#22C55E', opacity: 0.4 },
              label: { show: false },
            })),
            ...sellMarkLines.map(ml => ({
              ...ml,
              lineStyle: { color: '#EF4444', opacity: 0.4 },
              label: { show: false },
            })),
          ],
        } : undefined,
      },
      ...(benchmarkValues.length > 0 ? [{
        name: '基准',
        type: 'line' as const,
        data: benchmarkValues,
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#94A3B8', width: 1.5, type: 'dashed' as const },
      }] : []),
    ],
  };

  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
      lazyUpdate
    />
  );
}
