/**
 * 14因子雷达图 — 增强版 ECharts radar 可视化
 *
 * 增强1: 双接口数据合并 (factor-radar + sentiment)
 * 增强2: 中心叠加显示 (聚合分 + 信号标签 + 置信度星标)
 * 增强3: 颜色编码 + 权重气泡 (径向渐变 + custom series)
 * 增强4: MACD 信号条 (趋势chip + DIF/DEA/柱状 + 动量 + 同向 + 交叉 + 迷你柱)
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { fetchFactorRadar, fetchV5Sentiment, type FactorRadarItem, type V5MacdHistoryItem } from '../../api/marketV5';
import LoadingSpinner from '../common/LoadingSpinner';
import DivergenceBadge from '../common/DivergenceBadge';

interface Props {
  indexCode?: string;
}

// ==================== 常量 ====================

/** 信号语义色（复用 DashboardV5 token） */
const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

/** 信号中文标签 */
const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', 'S': '恐惧', 'A': '偏恐惧', 'B': '中性',
  'C': '偏贪婪', 'D': '贪婪', 'E': '极度贪婪',
};

/** 14 因子短码映射（轴标签用短码避免拥挤） */
const SHORT_CODES: Record<string, string> = {
  VOL: 'VOL', ADR: 'ADR', ERP: 'ERP', FLOW: 'FLOW',
  ETF: 'ETF', NHNL: 'NHNL', TURN: 'TURN', POS: 'POS',
  NBF: 'NBF', PCR: 'PCR', NEWF: 'NEWF', MARGIN: 'MARGIN',
  RSI: 'RSI', INDUSTRY_DIVERGENCE: 'DIVERGE',
};

/** 因子数（固定14轴） */
const FACTOR_COUNT = 14;

// ==================== 类型 ====================

interface MacdSnapshot {
  macd_line: number;
  signal_line: number;
  histogram: number;
  trend: string;
  cross: string | null;
  same_direction_days: number;
  momentum: number;
}

interface DivergenceInfo {
  type: string;
  strength: number;
  window: number;
  price_macd_trend: string;
  sentiment_macd_trend: string;
  signal: string | null;
  confidence: string;
}

interface SentimentData {
  composite_score: number;
  signal_level: string;
  confidence_stars: number;
  macd: MacdSnapshot | null;
  macd_history: V5MacdHistoryItem[];
  price_macd: MacdSnapshot | null;
  price_macd_history: V5MacdHistoryItem[];
  divergence: DivergenceInfo | null;
}

interface EnhancedFactor extends FactorRadarItem {
  sigmoid_score: number;
  contribution: number;
}

// ==================== 工具函数 ====================

/** 恐惧→贪婪色阶：绿(恐惧) → 黄(中性) → 琥珀(偏热) → 红(贪婪) */
function greedColor(v: number): string {
  if (v < 30) return '#22C55E';
  if (v < 50) return '#FBBF24';
  if (v < 70) return '#F59E0B';
  return '#EF4444';
}

/** 信号色（用于描边/中心叠加），黄色信号用深一档提升可读性 */
function signalColor(level: string): string {
  if (level === 'B') return '#F59E0B';
  return SIGNAL_COLORS[level] || '#94A3B8';
}

/** 信号标签文字色（黄底用深棕保证对比度） */
function signalTextColor(level: string): string {
  if (level === 'B' || level === 'A') return '#92400E';
  if (level === 'S+' || level === 'S') return '#065F46';
  if (level === 'D' || level === 'E') return '#991B1B';
  return '#475569';
}

// ==================== MACD 子组件 ====================

/** 迷你 MACD 折线图（纯 SVG，最近 20 条） */
function MiniMacdChart({ data }: { data: V5MacdHistoryItem[] }) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return <span className="text-[9px] text-gray-400 leading-tight">无历史数据</span>;
  }

  const recent = data.slice(-20);
  const count = recent.length;
  const W = 120;
  const H = 40;
  const barW = 2;

  const allVals = recent.flatMap((d) => [d.dif, d.dea, d.hist]);
  let minVal = Math.min(...allVals, 0);
  let maxVal = Math.max(...allVals, 0);
  const range = maxVal - minVal || 1;
  minVal -= range * 0.05;
  maxVal += range * 0.05;
  const paddedRange = maxVal - minVal || 1;

  const xScale = (i: number) => (count === 1 ? W / 2 : (i / (count - 1)) * W);
  const yScale = (v: number) => ((maxVal - v) / paddedRange) * H;

  const zeroY = yScale(0);

  const difPoints = recent.map((d, i) => `${xScale(i)},${yScale(d.dif)}`).join(' ');
  const deaPoints = recent.map((d, i) => `${xScale(i)},${yScale(d.dea)}`).join(' ');

  const hoverItem = hoverIdx !== null ? recent[hoverIdx] : null;

  return (
    <div className="relative" style={{ width: W, height: H }} onMouseLeave={() => setHoverIdx(null)}>
      <svg width={W} height={H} style={{ display: 'block' }}>
        {/* 零线 */}
        {zeroY >= 0 && zeroY <= H && (
          <line x1={0} y1={zeroY} x2={W} y2={zeroY} stroke="#CBD5E1" strokeWidth={0.5} strokeDasharray="2,2" />
        )}
        {/* HIST 柱状 */}
        {recent.map((d, i) => {
          const x = xScale(i) - barW / 2;
          const y = Math.min(yScale(d.hist), zeroY);
          const h = Math.abs(yScale(d.hist) - zeroY);
          return (
            <rect
              key={`h${i}`}
              x={x}
              y={y}
              width={barW}
              height={Math.max(0.5, h)}
              fill={d.hist >= 0 ? '#22C55E' : '#EF4444'}
              opacity={0.55}
            />
          );
        })}
        {/* DIF 线 */}
        <polyline points={difPoints} fill="none" stroke="#3B82F6" strokeWidth={1} />
        {/* DEA 线 */}
        <polyline points={deaPoints} fill="none" stroke="#F59E0B" strokeWidth={1} />
        {/* Hover 区域 */}
        {recent.map((_, i) => (
          <rect
            key={`hover${i}`}
            x={xScale(i) - 3}
            y={0}
            width={6}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHoverIdx(i)}
          />
        ))}
      </svg>
      {/* Tooltip */}
      {hoverItem && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 rounded bg-gray-800 text-white text-[9px] whitespace-nowrap pointer-events-none z-20">
          {hoverItem.date} | DIF:{hoverItem.dif.toFixed(2)} DEA:{hoverItem.dea.toFixed(2)} HIST:{hoverItem.hist.toFixed(2)}
        </div>
      )}
    </div>
  );
}

/** 单行 MACD 数据条 */
function MacdRow({ macd, history }: { macd: MacdSnapshot; history: V5MacdHistoryItem[] }) {
  const isBull = macd.trend === 'bullish';
  const isBear = macd.trend === 'bearish';

  const crossConfig = macd.cross === 'golden'
    ? { label: '金叉', bg: 'bg-green-100', text: 'text-green-700' }
    : macd.cross === 'death'
      ? { label: '死叉', bg: 'bg-red-100', text: 'text-red-700' }
      : { label: '无', bg: 'bg-gray-100', text: 'text-gray-500' };

  const valColor = (v: number) => v >= 0 ? 'text-green-600' : 'text-red-600';

  return (
    <div className="flex items-center gap-2 sm:gap-3 h-10 px-2 sm:px-3 rounded-lg bg-gray-50 border border-gray-200 overflow-x-auto">
      {/* 趋势 chip */}
      <div
        className={`flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
          isBull ? 'bg-green-100 text-green-700' : isBear ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-500'
        }`}
      >
        {isBull ? '多头↑' : isBear ? '空头↓' : '震荡'}
      </div>

      {/* DIF */}
      <div className="flex-shrink-0 flex flex-col items-center">
        <span className="text-[9px] text-gray-400 leading-tight">DIF</span>
        <span className={`text-xs font-mono font-medium ${valColor(macd.macd_line)}`}>
          {macd.macd_line.toFixed(2)}
        </span>
      </div>

      {/* DEA */}
      <div className="flex-shrink-0 flex flex-col items-center">
        <span className="text-[9px] text-gray-400 leading-tight">DEA</span>
        <span className={`text-xs font-mono font-medium ${valColor(macd.signal_line)}`}>
          {macd.signal_line.toFixed(2)}
        </span>
      </div>

      {/* 柱状 */}
      <div className="flex-shrink-0 flex flex-col items-center">
        <span className="text-[9px] text-gray-400 leading-tight">柱状</span>
        <span className={`text-xs font-mono font-medium ${valColor(macd.histogram)}`}>
          {macd.histogram.toFixed(2)}
        </span>
      </div>

      {/* 动量 */}
      <div className="flex-shrink-0 flex flex-col items-center">
        <span className="text-[9px] text-gray-400 leading-tight">动量</span>
        <span className={`text-xs font-mono font-medium ${valColor(macd.momentum)}`}>
          {macd.momentum.toFixed(0)}
        </span>
      </div>

      {/* 同向 N 日 */}
      <div className="flex-shrink-0 flex flex-col items-center">
        <span className="text-[9px] text-gray-400 leading-tight">同向</span>
        <span className="text-xs font-mono font-medium text-gray-600">
          {macd.same_direction_days}日
        </span>
      </div>

      {/* 交叉状态 */}
      <div className={`flex-shrink-0 px-2 py-0.5 rounded text-[10px] font-medium ${crossConfig.bg} ${crossConfig.text}`}>
        {crossConfig.label}
      </div>

      {/* 迷你 MACD 折线图 */}
      <div className="flex-shrink-0 ml-auto">
        <MiniMacdChart data={history} />
      </div>
    </div>
  );
}

function MacdSignalBar({
  macd,
  macdHistory,
  priceMacd,
  priceMacdHistory,
}: {
  macd: MacdSnapshot | null;
  macdHistory: V5MacdHistoryItem[];
  priceMacd: MacdSnapshot | null;
  priceMacdHistory: V5MacdHistoryItem[];
}) {
  const unavailable = (
    <div className="flex items-center justify-center h-10 rounded-lg bg-gray-50 border border-gray-200">
      <span className="text-xs text-gray-400">数据不足</span>
    </div>
  );

  return (
    <div className="space-y-1.5">
      {/* 情绪MACD (5/20/9) */}
      <div>
        <p className="text-[10px] text-gray-400 mb-0.5">情绪MACD (5/20/9)</p>
        {macd ? <MacdRow macd={macd} history={macdHistory} /> : unavailable}
      </div>
      {/* 价格MACD (12/26/9) */}
      <div>
        <p className="text-[10px] text-gray-400 mb-0.5">价格MACD (12/26/9)</p>
        {priceMacd ? <MacdRow macd={priceMacd} history={priceMacdHistory} /> : unavailable}
      </div>
    </div>
  );
}

// ==================== 背离信号面板 ====================

function DivergencePanel({ divergence }: { divergence: DivergenceInfo | null }) {
  if (!divergence || divergence.type === 'insufficient_data') {
    return (
      <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-50 border border-gray-200">
        <DivergenceBadge divergence={null} />
      </div>
    );
  }

  const trendArrow = (t: string) => t === 'up' ? '\u2191' : t === 'down' ? '\u2193' : '\u2192';
  const trendLabel = (t: string) => t === 'up' ? '上升' : t === 'down' ? '下降' : '平稳';
  const trendColor = (t: string) => t === 'up' ? 'text-green-600' : t === 'down' ? 'text-red-600' : 'text-gray-500';
  const barColor = divergence.type === 'top' ? '#ef4444' : '#10b981';

  return (
    <div className="px-2 py-1.5 rounded-lg bg-gray-50 border border-gray-200 space-y-1">
      {/* Badge */}
      <DivergenceBadge divergence={divergence} />
      {divergence.type !== 'none' && (
        <>
          {/* Strength progress bar */}
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-gray-400 shrink-0">强度</span>
            <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${divergence.strength * 100}%`,
                  background: barColor,
                }}
              />
            </div>
            <span className="text-[9px] font-mono text-gray-500 shrink-0">{(divergence.strength * 100).toFixed(0)}%</span>
          </div>
          {/* Trend comparison */}
          <div className="flex items-center gap-1.5 text-[10px] flex-wrap">
            <span className="text-gray-400">价格MACD</span>
            <span className={trendColor(divergence.price_macd_trend)}>
              {trendLabel(divergence.price_macd_trend)} {trendArrow(divergence.price_macd_trend)}
            </span>
            <span className="text-gray-300">vs</span>
            <span className="text-gray-400">情绪MACD</span>
            <span className={trendColor(divergence.sentiment_macd_trend)}>
              {trendLabel(divergence.sentiment_macd_trend)} {trendArrow(divergence.sentiment_macd_trend)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

// ==================== 中心叠加子组件 ====================

function CenterOverlay({
  compositeScore,
  signalLevel,
  confidenceStars,
}: {
  compositeScore: number;
  signalLevel: string;
  confidenceStars: number;
}) {
  const sColor = signalColor(signalLevel);
  const sTextColor = signalTextColor(signalLevel);
  const sLabel = SIGNAL_LABELS[signalLevel] || '未知';

  return (
    <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-10">
      <div
        className="flex flex-col items-center justify-center rounded-[10px] px-3 py-2"
        style={{
          background: 'rgba(255,255,255,0.92)',
          border: '1px solid #E2E8F0',
          backdropFilter: 'blur(4px)',
          minWidth: '90px',
        }}
      >
        {/* 聚合分 */}
        <span
          className="font-mono font-bold leading-none"
          style={{ fontSize: '26px', color: sColor }}
        >
          {compositeScore.toFixed(1)}
        </span>
        {/* 信号标签 */}
        <span
          className="mt-1 font-medium leading-tight"
          style={{ fontSize: '12px', color: sTextColor }}
        >
          {signalLevel} · {sLabel}
        </span>
        {/* 置信度星标（4颗） */}
        <div className="mt-0.5" style={{ fontSize: '13px', letterSpacing: '1px' }}>
          {Array.from({ length: 4 }, (_, i) => (
            <span
              key={i}
              style={{ color: i < confidenceStars ? '#FBBF24' : '#CBD5E1' }}
            >
              ★
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ==================== 色阶图例 ====================

function ColorLegend() {
  const items = [
    { color: '#22C55E', label: '恐惧·买' },
    { color: '#FBBF24', label: '中性' },
    { color: '#F59E0B', label: '偏热' },
    { color: '#EF4444', label: '贪婪·卖' },
  ];
  return (
    <div className="flex items-center gap-3 text-[10px] text-gray-500">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: item.color }}
          />
          <span>{item.label}</span>
        </div>
      ))}
      <div className="flex items-center gap-1 ml-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400" />
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-500" />
        <span>气泡=权重</span>
      </div>
    </div>
  );
}

// ==================== 主组件 ====================

export default function FactorRadarChart({ indexCode = 'SH000300' }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<unknown>(null);
  const [mergedFactors, setMergedFactors] = useState<EnhancedFactor[]>([]);
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chartHeight, setChartHeight] = useState(340);

  // 响应式高度
  useEffect(() => {
    const updateHeight = () => {
      const w = window.innerWidth;
      if (w >= 1024) setChartHeight(340);
      else if (w >= 640) setChartHeight(320);
      else setChartHeight(280);
    };
    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => window.removeEventListener('resize', updateHeight);
  }, []);

  // 数据加载：双接口合并
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        // 并行调用两个接口
        const [radarRes, sentimentRes] = await Promise.all([
          fetchFactorRadar(indexCode),
          fetchV5Sentiment(indexCode).catch(() => null),
        ]);

        if (cancelled) return;

        // 解析 sentiment
        let sData: SentimentData | null = null;
        if (sentimentRes) {
          const raw = sentimentRes as Record<string, unknown>;
          sData = {
            composite_score: raw.composite_score as number,
            signal_level: raw.signal_level as string,
            confidence_stars: raw.confidence_stars as number,
            macd: (raw.macd as MacdSnapshot) ?? null,
            macd_history: (raw.macd_history as V5MacdHistoryItem[]) ?? [],
            price_macd: (raw.price_macd as MacdSnapshot) ?? null,
            price_macd_history: (raw.price_macd_history as V5MacdHistoryItem[]) ?? [],
            divergence: (raw.divergence as DivergenceInfo) ?? null,
          };
        }

        // 解析 sigmoid_score（API 现在返回标准 JSON 对象）
        const sigmoidMap = new Map<string, number>();
        if (sentimentRes) {
          const details = (sentimentRes as Record<string, unknown>).factor_details;
          if (Array.isArray(details)) {
            for (const item of details) {
              if (typeof item === 'object' && item !== null && 'factor_name' in item) {
                const obj = item as Record<string, unknown>;
                if (typeof obj.sigmoid_score === 'number') {
                  sigmoidMap.set(obj.factor_name as string, obj.sigmoid_score);
                }
              }
            }
          }
        }

        // 合并数据
        const merged: EnhancedFactor[] = radarRes.factors.map((r) => {
          const sigmoid = sigmoidMap.get(r.name) ?? r.percentile;
          return {
            ...r,
            sigmoid_score: sigmoid,
            contribution: sigmoid * r.weight,
          };
        });

        if (!cancelled) {
          setMergedFactors(merged);
          setSentiment(sData);
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : '加载失败';
        if (!cancelled) setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [indexCode]);

  // ECharts 渲染
  useEffect(() => {
    if (!chartRef.current || mergedFactors.length === 0) return;

    let chart: ReturnType<typeof import('echarts')['init']> | null = null;
    let cleanup: (() => void) | null = null;

    import('echarts').then((echarts) => {
      if (!chartRef.current || mergedFactors.length === 0) return;

      // 销毁旧实例
      if (chartInstance.current) {
        (chartInstance.current as { dispose: () => void }).dispose();
      }

      chart = echarts.init(chartRef.current);
      chartInstance.current = chart;

      const factors = mergedFactors;
      const sLevel = sentiment?.signal_level || 'B';
      const sColor = signalColor(sLevel);

      // 指标定义（短码）
      const indicator = factors.map((f) => ({
        name: SHORT_CODES[f.name] || f.name,
        max: 100,
      }));

      // 绘图值 = sigmoid_score
      const values = factors.map((f) => f.sigmoid_score);

      // tooltip formatter for custom series (individual factor)
      const factorTooltip = (f: EnhancedFactor) => {
        const dirText = f.direction === 'fear' ? '恐惧向（超买）' : '贪婪向（超卖）';
        const interp =
          f.sigmoid_score < 30 ? '恐惧·买入区' :
          f.sigmoid_score < 50 ? '中性' :
          f.sigmoid_score < 70 ? '偏热' : '贪婪·卖出区';
        const c = greedColor(f.sigmoid_score);
        return `
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">${f.name} · ${f.label}</div>
          <div style="display:grid;grid-template-columns:auto auto;gap:2px 12px;font-size:12px">
            <span style="color:#6B7280">方向</span><span>${dirText}</span>
            <span style="color:#6B7280">原始分位</span><span style="font-family:monospace">${f.percentile.toFixed(1)}%</span>
            <span style="color:#6B7280">Sigmoid</span><span style="font-family:monospace;color:${c};font-weight:600">${f.sigmoid_score.toFixed(1)}</span>
            <span style="color:#6B7280">权重</span><span style="font-family:monospace">${f.weight.toFixed(2)}</span>
            <span style="color:#6B7280">贡献度</span><span style="font-family:monospace">${f.contribution.toFixed(2)}</span>
            <span style="color:#6B7280">解读</span><span style="color:${c};font-weight:600">${interp}</span>
          </div>
        `;
      };

      // 主雷达 + 权重气泡 custom series
      const series: Record<string, unknown>[] = [
        {
          type: 'radar',
          symbol: 'none',
          lineStyle: { color: sColor, width: 1.5 },
          areaStyle: {
            color: {
              type: 'radial',
              x: 0.5,
              y: 0.5,
              r: 0.5,
              colorStops: [
                { offset: 0, color: 'rgba(34,197,94,0.30)' },
                { offset: 0.5, color: 'rgba(251,191,36,0.22)' },
                { offset: 1, color: 'rgba(239,68,68,0.16)' },
              ],
            },
          },
          data: [{ value: values, name: '情绪贪婪度' }],
          animationDuration: 600,
          animationEasing: 'cubicOut',
          z: 2,
        },
        // 权重气泡 custom series
        {
          type: 'custom',
          coordinateSystem: 'radar',
          renderItem: (params: { coordSys: { cx: number; cy: number; r: number } }, api: { value: (i: number) => number }) => {
            const cs = params.coordSys;
            const idx = api.value(0);
            const f = factors[idx];
            if (!f) return { type: 'circle', shape: { cx: 0, cy: 0, r: 0 } };
            const angle = (-90 + idx * (360 / FACTOR_COUNT)) * Math.PI / 180;
            const rr = cs.r * (f.sigmoid_score / 100);
            const x = cs.cx + rr * Math.cos(angle);
            const y = cs.cy + rr * Math.sin(angle);
            // 气泡半径: weight 0.02→3px, 0.12→8px
            const size = 3 + ((f.weight - 0.02) / 0.10) * 5;
            return {
              type: 'circle',
              shape: { cx: x, cy: y, r: Math.max(3, size) },
              style: {
                fill: greedColor(f.sigmoid_score),
                stroke: '#fff',
                lineWidth: 1.5,
              },
              transition: 'scale',
              enterFrom: { scale: 0 },
              animationDuration: 400,
            };
          },
          data: factors.map((_, i) => [i]),
          tooltip: {
            formatter: (p: { dataIndex: number }) => factorTooltip(factors[p.dataIndex]),
          },
          z: 10,
        },
      ];

      chart.setOption({
        tooltip: {
          trigger: 'item',
          backgroundColor: 'rgba(255,255,255,0.96)',
          borderColor: '#E2E8F0',
          borderWidth: 1,
          textStyle: { color: '#0F172A', fontSize: 12 },
          extraCssText: 'box-shadow:0 4px 12px rgba(0,0,0,0.08);border-radius:8px;',
        },
        radar: {
          center: ['50%', '50%'],
          radius: '62%',
          indicator,
          shape: 'polygon',
          splitNumber: 4,
          axisName: {
            color: '#6B7280',
            fontSize: 11,
          },
          splitArea: {
            areaStyle: {
              color: ['#F9FAFB', '#F3F4F6', '#E5E7EB', '#D1D5DB'],
            },
          },
          splitLine: { lineStyle: { color: '#E5E7EB' } },
          axisLine: { lineStyle: { color: '#D1D5DB' } },
        },
        series,
      });

      const handleResize = () => chart?.resize();
      window.addEventListener('resize', handleResize);
      cleanup = () => {
        window.removeEventListener('resize', handleResize);
        chart?.dispose();
        chartInstance.current = null;
      };
    });

    return () => {
      cleanup?.();
    };
  }, [mergedFactors, sentiment, chartHeight]);

  // ==================== 渲染 ====================

  if (loading) return <LoadingSpinner size="sm" text="雷达图加载中..." />;
  if (error) return <p className="text-xs text-red-400">{error}</p>;
  if (mergedFactors.length === 0) return <p className="text-xs text-gray-400">暂无数据</p>;

  const compositeScore = sentiment?.composite_score ?? 0;
  const signalLevel = sentiment?.signal_level ?? 'B';
  const confidenceStars = sentiment?.confidence_stars ?? 0;
  const macd = sentiment?.macd ?? null;
  const priceMacd = sentiment?.price_macd ?? null;
  const divergence = sentiment?.divergence ?? null;

  return (
    <div className="space-y-2">
      {/* 雷达图 + 中心叠加 */}
      <div className="relative" style={{ height: chartHeight }}>
        <div ref={chartRef} style={{ width: '100%', height: '100%' }} />
        {sentiment && (
          <CenterOverlay
            compositeScore={compositeScore}
            signalLevel={signalLevel}
            confidenceStars={confidenceStars}
          />
        )}
      </div>

      {/* 色阶图例 */}
      <ColorLegend />

      {/* 因子分位数列表（保留现有功能，颜色改用 sigmoid 分档） */}
      <div className="grid grid-cols-4 sm:grid-cols-7 gap-1">
        {mergedFactors.map((f) => {
          const barColor = greedColor(f.sigmoid_score);
          return (
            <div key={f.name} className="text-center">
              <p className="text-[9px] text-gray-400 truncate" title={f.label}>
                {SHORT_CODES[f.name] || f.name}
              </p>
              <div className="h-1 bg-gray-100 rounded-full mt-0.5">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.max(5, f.sigmoid_score)}%`,
                    background: barColor,
                  }}
                />
              </div>
              <p className="text-[9px] font-mono text-gray-500">
                {f.sigmoid_score.toFixed(0)}
              </p>
            </div>
          );
        })}
      </div>

      {/* MACD 信号条 */}
      <MacdSignalBar macd={macd} macdHistory={sentiment?.macd_history ?? []} priceMacd={priceMacd} priceMacdHistory={sentiment?.price_macd_history ?? []} />

      {/* 背离信号 */}
      <DivergencePanel divergence={divergence} />
    </div>
  );
}
