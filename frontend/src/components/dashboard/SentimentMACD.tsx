/**
 * 情绪 MACD 历史曲线 — ECharts 可视化
 *
 * 数据来源：/api/v5/market/signal-lights/{index_code}?days=N
 *   - 取最近 N 天 composite_score
 *   - 客户端计算 MACD（EMA12 - EMA26 = DIF；DIF 的 EMA9 = DEA；柱=DIF-DEA）
 *
 * 设计：参考用户提供的"参考布局"（fund-search-v5.html）—— 浅色极简 + 趋势线
 */
import { useEffect, useRef, useState } from 'react';
import { fetchV5SignalLights } from '../../api/marketV5';
import LoadingSpinner from '../common/LoadingSpinner';

interface Props {
  indexCode?: string;
  days?: number;  // 默认 60 天
}

export default function SentimentMACD({ indexCode = 'SH000300', days = 60 }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [scores, setScores] = useState<number[]>([]);
  const [dates, setDates] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchV5SignalLights(indexCode, days);
        if (cancelled) return;
        const sorted = [...data.signals].sort((a, b) => a.date.localeCompare(b.date));
        setDates(sorted.map((s) => s.date));
        setScores(sorted.map((s) => s.composite_score));
      } catch (e: any) {
        if (!cancelled) setError(e.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [indexCode, days]);

  useEffect(() => {
    if (!chartRef.current || scores.length < 26) return;

    import('echarts').then((echarts) => {
      if (!chartRef.current) return;
      const chart = echarts.init(chartRef.current);

      // 客户端计算 MACD
      const dif = calcEMA(scores, 12).map((v, i) => v - calcEMA(scores, 26)[i]);
      const dea = calcEMA(dif, 9);
      const macd = dif.map((v, i) => (v - dea[i]) * 2);  // 柱状图 ×2 放大

      chart.setOption({
        backgroundColor: 'transparent',
        grid: { left: 50, right: 30, top: 30, bottom: 40 },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'cross' },
          backgroundColor: 'rgba(255,255,255,0.95)',
          borderColor: '#e5e7eb',
          textStyle: { color: '#1f2937' },
        },
        legend: {
          data: ['情绪分', 'DIF', 'DEA'],
          top: 0,
          textStyle: { color: '#6b7280' },
        },
        xAxis: {
          type: 'category',
          data: dates,
          axisLine: { lineStyle: { color: '#e5e7eb' } },
          axisLabel: { color: '#6b7280', fontSize: 11 },
        },
        yAxis: [
          {
            type: 'value',
            name: '情绪分',
            min: 0,
            max: 100,
            position: 'left',
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280' },
            splitLine: { lineStyle: { color: '#f3f4f6' } },
          },
          {
            type: 'value',
            name: 'MACD',
            position: 'right',
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280' },
            splitLine: { show: false },
          },
        ],
        series: [
          {
            name: '情绪分',
            type: 'line',
            data: scores,
            smooth: true,
            lineStyle: { color: '#6366f1', width: 2 },
            areaStyle: {
              color: {
                type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(99,102,241,0.2)' },
                  { offset: 1, color: 'rgba(99,102,241,0)' },
                ],
              },
            },
            showSymbol: false,
          },
          {
            name: 'DIF',
            type: 'line',
            yAxisIndex: 1,
            data: dif,
            smooth: true,
            lineStyle: { color: '#f59e0b', width: 1.5 },
            showSymbol: false,
          },
          {
            name: 'DEA',
            type: 'line',
            yAxisIndex: 1,
            data: dea,
            smooth: true,
            lineStyle: { color: '#ef4444', width: 1.5 },
            showSymbol: false,
          },
          {
            name: '柱',
            type: 'bar',
            yAxisIndex: 1,
            data: macd,
            itemStyle: {
              color: (params: any) => (params.value >= 0 ? '#10b981' : '#ef4444'),
              opacity: 0.5,
            },
          },
        ],
      });

      // 自适应
      const handleResize = () => chart.resize();
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
    });
  }, [scores, dates]);

  if (loading) return <LoadingSpinner />;
  if (error) return <div className="text-red-500 text-sm p-4">错误: {error}</div>;
  if (scores.length < 26) {
    return <div className="text-gray-400 text-sm p-4 text-center">数据不足（需 ≥ 26 天才能计算 MACD）</div>;
  }

  return <div ref={chartRef} className="w-full h-80" />;
}

// ===== 工具函数（纯函数，可单测）=====

/**
 * 计算 EMA（指数移动平均）
 * @param data 原始数据数组
 * @param period 周期（默认 12）
 * @returns EMA 数组（前 period-1 个为 NaN）
 */
export function calcEMA(data: number[], period: number = 12): number[] {
  const k = 2 / (period + 1);
  const ema: number[] = [];

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      ema.push(NaN);
    } else if (i === period - 1) {
      // 第一个 EMA = 前 period 个数据的简单平均
      const slice = data.slice(0, period);
      ema.push(slice.reduce((a, b) => a + b, 0) / period);
    } else {
      ema.push(data[i] * k + ema[i - 1] * (1 - k));
    }
  }
  return ema;
}
