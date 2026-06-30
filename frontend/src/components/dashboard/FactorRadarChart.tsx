/**
 * 14因子雷达图 — ECharts radar 可视化
 * 展示各因子当前分位数值，直观看到各维度情绪贡献
 */
import { useEffect, useRef, useState } from 'react';
import { fetchFactorRadar, type FactorRadarItem } from '../../api/marketV5';
import LoadingSpinner from '../common/LoadingSpinner';

interface Props {
  indexCode?: string;
}

export default function FactorRadarChart({ indexCode = 'SH000300' }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [factors, setFactors] = useState<FactorRadarItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchFactorRadar(indexCode);
        if (!cancelled) setFactors(data.factors);
      } catch (e: any) {
        if (!cancelled) setError(e.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [indexCode]);

  useEffect(() => {
    if (!chartRef.current || factors.length === 0) return;

    // Lazy load echarts
    import('echarts').then((echarts) => {
      if (!chartRef.current) return;
      const chart = echarts.init(chartRef.current);

      const indicator = factors.map((f) => ({
        name: f.label,
        max: 100,
      }));

      const values = factors.map((f) => f.percentile);

      chart.setOption({
        tooltip: {
          trigger: 'item',
          formatter: (params: any) => {
            const idx = params.dataIndex ?? params.value?.[0];
            if (params.data?.value) {
              const vals = params.data.value as number[];
              let html = '';
              factors.forEach((f, i) => {
                const color = f.direction === 'fear'
                  ? (vals[i] > 70 ? '#EF4444' : '#10B981')
                  : (vals[i] > 70 ? '#10B981' : '#EF4444');
                html += `<div style="display:flex;justify-content:space-between;gap:12px">
                  <span>${f.label}</span>
                  <span style="color:${color};font-weight:bold">${vals[i].toFixed(1)}%</span>
                </div>`;
              });
              return html;
            }
            return `${params.name}: ${params.value}`;
          },
        },
        radar: {
          indicator,
          shape: 'polygon',
          splitNumber: 4,
          axisName: {
            color: '#6B7280',
            fontSize: 10,
          },
          splitArea: {
            areaStyle: {
              color: ['#F9FAFB', '#F3F4F6', '#E5E7EB', '#D1D5DB'],
            },
          },
          splitLine: {
            lineStyle: { color: '#E5E7EB' },
          },
          axisLine: {
            lineStyle: { color: '#D1D5DB' },
          },
        },
        series: [{
          type: 'radar',
          data: [{
            value: values,
            name: '情绪分位数',
            symbol: 'circle',
            symbolSize: 5,
            lineStyle: {
              color: '#6366F1',
              width: 2,
            },
            areaStyle: {
              color: {
                type: 'radial',
                x: 0.5,
                y: 0.5,
                r: 0.5,
                colorStops: [
                  { offset: 0, color: 'rgba(99,102,241,0.25)' },
                  { offset: 1, color: 'rgba(99,102,241,0.05)' },
                ],
              },
            },
            itemStyle: {
              color: '#6366F1',
            },
          }],
        }],
      });

      const handleResize = () => chart.resize();
      window.addEventListener('resize', handleResize);
      return () => {
        window.removeEventListener('resize', handleResize);
        chart.dispose();
      };
    });
  }, [factors]);

  if (loading) return <LoadingSpinner size="sm" text="雷达图加载中..." />;
  if (error) return <p className="text-xs text-red-400">{error}</p>;

  return (
    <div>
      <div ref={chartRef} style={{ width: '100%', height: 320 }} />
      {/* 因子分位数列表 */}
      <div className="grid grid-cols-7 gap-1 mt-2">
        {factors.map((f) => {
          const isHigh = f.percentile > 70;
          const isLow = f.percentile < 30;
          const barColor = f.direction === 'fear'
            ? (isHigh ? 'bg-red-400' : isLow ? 'bg-green-400' : 'bg-gray-300')
            : (isHigh ? 'bg-green-400' : isLow ? 'bg-red-400' : 'bg-gray-300');
          return (
            <div key={f.name} className="text-center">
              <p className="text-[9px] text-gray-400 truncate">{f.label}</p>
              <div className="h-1 bg-gray-100 rounded-full mt-0.5">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${Math.max(5, f.percentile)}%` }}
                />
              </div>
              <p className="text-[9px] font-mono text-gray-500">{f.percentile.toFixed(0)}%</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
