/**
 * SignalAnalysisPanel — 信号分析 Tab
 * 信号绩效统计 + 板块情绪热力图
 */
import { useState, useEffect } from 'react';
import { Activity, Grid3X3, RefreshCw } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { PieChart, BarChart, HeatmapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  TitleComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { fetchSignalPerformance } from '../../api/backtest';
import type { SignalPerformanceData } from '../../api/backtest';
import { fetchSectorHeatmap } from '../../api/market';
import type { SectorHeatmapItem, GroupSummary } from '../../types';
import { SIGNAL_COLORS, SIGNAL_LABELS, SIGNAL_LEVELS } from '../../utils/paramsMapper';

echarts.use([
  PieChart, BarChart, HeatmapChart, GridComponent, TooltipComponent,
  LegendComponent, VisualMapComponent, TitleComponent, CanvasRenderer,
]);

/* ============================================================
   信号绩效统计子组件
   ============================================================ */
function SignalPerformanceSection() {
  const [data, setData] = useState<SignalPerformanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState(30);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchSignalPerformance('SH000300', days);
      setData(res);
    } catch (err: any) {
      setError(err?.message || '加载信号绩效失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [days]);

  // 信号分布饼图
  const pieOption = (() => {
    if (!data?.signal_distribution) return null;
    const dist = data.signal_distribution;
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c}次 ({d}%)' },
      legend: { bottom: 0, textStyle: { fontSize: 10, color: '#9CA3AF' }, itemWidth: 10, itemHeight: 10 },
      series: [{
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 1 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 12, fontWeight: 'bold' } },
        data: SIGNAL_LEVELS
          .filter(l => (dist[l] ?? 0) > 0)
          .map(l => ({
            name: `${l} ${SIGNAL_LABELS[l]}`,
            value: dist[l],
            itemStyle: { color: SIGNAL_COLORS[l] },
          })),
      }],
    };
  })();

  // 信号趋势柱状图
  const barOption = (() => {
    if (!data?.signals || data.signals.length === 0) return null;
    const sigs = [...data.signals].reverse(); // 按日期正序
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: Array<{ dataIndex: number; value: number }>) => {
          const idx = params[0]?.dataIndex ?? 0;
          const s = sigs[idx];
          if (!s) return '';
          return `<div style="font-weight:600">${s.date}</div>
            <div>信号: <span style="color:${SIGNAL_COLORS[s.signal_level] || '#333'}">${s.signal_level} ${SIGNAL_LABELS[s.signal_level] || ''}</span></div>
            <div>评分: ${s.composite_score?.toFixed(1)}</div>`;
        },
      },
      grid: { left: 40, right: 10, top: 20, bottom: 30 },
      xAxis: {
        type: 'category',
        data: sigs.map(s => s.date.length === 8 ? `${s.date.slice(4, 6)}-${s.date.slice(6, 8)}` : s.date.slice(5)),
        axisLabel: { fontSize: 9, color: '#9CA3AF' },
        axisLine: { lineStyle: { color: '#E5E7EB' } },
      },
      yAxis: {
        type: 'value',
        min: 0, max: 100,
        axisLabel: { fontSize: 9, color: '#9CA3AF' },
        splitLine: { lineStyle: { color: '#F3F4F6' } },
      },
      series: [{
        type: 'bar',
        data: sigs.map(s => ({
          value: s.composite_score,
          itemStyle: { color: SIGNAL_COLORS[s.signal_level] || '#94A3B8', borderRadius: [2, 2, 0, 0] },
        })),
        barMaxWidth: 12,
      }],
    };
  })();

  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-700 flex items-center gap-1.5">
          <Activity className="w-4 h-4 text-brand-500" />
          信号绩效统计
        </h3>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
          >
            <option value={7}>近7天</option>
            <option value={15}>近15天</option>
            <option value={30}>近30天</option>
            <option value={60}>近60天</option>
            <option value={90}>近90天</option>
          </select>
          <button onClick={loadData} className="p-1 text-gray-400 hover:text-brand-500 transition-colors">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading && !data && (
        <div className="text-center text-gray-400 text-xs py-8">加载中...</div>
      )}
      {error && (
        <div className="text-center text-red-500 text-xs py-8">{error}</div>
      )}

      {data && (
        <>
          {/* 概要指标 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="bg-gray-50 rounded-lg p-2.5">
              <p className="text-xs text-gray-400">信号总数</p>
              <p className="text-base font-bold text-gray-700">{data.total_signals}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5">
              <p className="text-xs text-gray-400">加仓信号</p>
              <p className="text-base font-bold text-green-600">{data.buy_signals}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5">
              <p className="text-xs text-gray-400">减仓信号</p>
              <p className="text-base font-bold text-red-500">{data.sell_signals}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-2.5">
              <p className="text-xs text-gray-400">持有信号</p>
              <p className="text-base font-bold text-gray-500">{data.hold_signals}</p>
            </div>
          </div>

          {/* 图表区域 */}
          <div className="grid md:grid-cols-2 gap-4">
            {pieOption && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">信号分布</p>
                <ReactEChartsCore echarts={echarts} option={pieOption} style={{ height: 220 }} notMerge lazyUpdate />
              </div>
            )}
            {barOption && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">信号评分趋势</p>
                <ReactEChartsCore echarts={echarts} option={barOption} style={{ height: 220 }} notMerge lazyUpdate />
              </div>
            )}
          </div>

          {/* 最近信号列表 */}
          {data.signals.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-gray-600 mb-1.5">最近信号（{data.signals.length}条）</h4>
              <div className="overflow-x-auto border border-gray-200 rounded-lg max-h-48 overflow-y-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr className="text-gray-400">
                      <th className="px-2 py-1">日期</th>
                      <th className="px-2 py-1">信号</th>
                      <th className="px-2 py-1">评分</th>
                      <th className="px-2 py-1">置信度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.signals.map((s, i) => (
                      <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                        <td className="px-2 py-1 font-mono text-gray-600">{s.date}</td>
                        <td className="px-2 py-1">
                          <span
                            className="px-1 py-0.5 rounded text-[10px] font-bold"
                            style={{ backgroundColor: `${SIGNAL_COLORS[s.signal_level]}20`, color: SIGNAL_COLORS[s.signal_level] }}
                          >
                            {s.signal_level} {SIGNAL_LABELS[s.signal_level] || ''}
                          </span>
                        </td>
                        <td className="px-2 py-1 font-mono text-gray-700">{s.composite_score?.toFixed(1)}</td>
                        <td className="px-2 py-1 text-gray-500">{s.confidence ? `${s.confidence}星` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ============================================================
   板块情绪热力图子组件
   ============================================================ */
function SectorHeatmapSection() {
  const [sectors, setSectors] = useState<SectorHeatmapItem[]>([]);
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetchSectorHeatmap();
        setSectors(res.sectors || []);
        setGroups(res.group_summary || []);
      } catch (err: any) {
        setError(err?.message || '加载热力图失败');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // 评分 → 颜色
  const scoreToColor = (score: number) => {
    if (score >= 75) return 'bg-red-500 text-white';
    if (score >= 60) return 'bg-orange-400 text-white';
    if (score >= 45) return 'bg-yellow-300 text-gray-800';
    if (score >= 30) return 'bg-lime-300 text-gray-800';
    if (score >= 15) return 'bg-cyan-300 text-gray-800';
    return 'bg-blue-400 text-white';
  };

  // 按分组组织
  const grouped = groups.length > 0
    ? groups.map(g => ({
        name: g.group_name,
        items: sectors.filter(s => s.sector_group === g.group_name),
      }))
    : [{ name: '全部板块', items: sectors }];

  return (
    <div className="card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-gray-700 flex items-center gap-1.5">
          <Grid3X3 className="w-4 h-4 text-brand-500" />
          板块情绪热力图
        </h3>
        <div className="flex items-center gap-1 text-[10px] text-gray-400">
          <span className="w-3 h-3 rounded bg-blue-400" />恐惧
          <span className="w-3 h-3 rounded bg-lime-300" />中性
          <span className="w-3 h-3 rounded bg-red-500" />贪婪
        </div>
      </div>

      {loading && <div className="text-center text-gray-400 text-xs py-8">加载中...</div>}
      {error && <div className="text-center text-red-500 text-xs py-8">{error}</div>}

      {!loading && !error && sectors.length === 0 && (
        <div className="text-center text-gray-400 text-xs py-8">暂无板块数据</div>
      )}

      {grouped.map(g => (
        <div key={g.name}>
          {g.name !== '全部板块' && (
            <p className="text-xs font-medium text-gray-500 mb-1.5">{g.name}（{g.items.length}个板块）</p>
          )}
          <div className="flex flex-wrap gap-1.5">
            {g.items.map(s => (
              <div
                key={s.sector_code}
                className={`px-2 py-1.5 rounded text-[10px] font-medium min-w-[56px] text-center cursor-default transition-transform hover:scale-105 ${scoreToColor(s.sentiment_score)}`}
                title={`${s.sector_name}: 情绪${s.sentiment_score}·涨幅${(s.sector_return ?? 0).toFixed(2)}%·5日动量${(s.momentum_5d ?? 0).toFixed(2)}%`}
              >
                <div className="truncate max-w-[60px]">{s.sector_name}</div>
                <div className="font-bold">{s.sentiment_score}</div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ============================================================
   信号分析 Tab 主组件
   ============================================================ */
export function SignalAnalysisPanel() {
  return (
    <div className="space-y-4">
      <SignalPerformanceSection />
      <SectorHeatmapSection />
    </div>
  );
}
