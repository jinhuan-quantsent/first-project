/**
 * 信号看板 — 跨指数信号矩阵 + MACD趋势 + 信号历史
 */
import { useEffect, useState } from 'react';
import { useAppStore } from '../store';
import LoadingSpinner from '../components/common/LoadingSpinner';
import DivergenceBanner from '../components/dashboard/DivergenceBanner';
import SignalVerifyBoard from '../components/dashboard/SignalVerifyBoard';
import {
  fetchV5Sentiment,
  fetchV5SignalLights,
  type V5MacdHistoryItem,
  type V5SignalLight,
  type V5MacdSnapshot,
} from '../api/marketV5';
import { Star } from 'lucide-react';
import { clsx } from 'clsx';
import { SIGNAL_COLORS_HEX as SIGNAL_COLORS, SIGNAL_LABELS } from '../types';
import type { SignalLevel } from '../types';

const INDEX_CODES = ['SH000001', 'SH000300', 'SZ399001', 'SZ399006'];

interface IndexCardData {
  index_code: string;
  index_name: string;
  composite_score: number;
  signal_level: string;
  confidence_stars: number;
  macd?: V5MacdSnapshot | null;
  macd_history?: V5MacdHistoryItem[];
  signals?: V5SignalLight[];
}

// ==================== 迷你 MACD SVG（简化版） ====================

function MiniMacdChart({ data }: { data: V5MacdHistoryItem[] }) {
  if (!data || data.length === 0) {
    return <span className="text-[9px] text-gray-400">无历史数据</span>;
  }

  const recent = data.slice(-20);
  const count = recent.length;
  const W = 100;
  const H = 30;
  const barW = 2;

  const allVals = recent.flatMap((d) => [d.dif, d.hist]);
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

  return (
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
    </svg>
  );
}

// ==================== 信号色块条 ====================

function SignalTimeline({ signals }: { signals: V5SignalLight[] }) {
  if (!signals || signals.length === 0) {
    return <span className="text-[10px] text-gray-400">无信号数据</span>;
  }

  // 信号按日期升序排列
  const sorted = [...signals].sort((a, b) => a.date.localeCompare(b.date));

  const formatDate = (dateStr: string) => {
    const parts = dateStr.split('-');
    return `${parts[1]}/${parts[2]}`;
  };

  return (
    <div className="flex items-start gap-2">
      {sorted.map((sig, i) => (
        <div key={i} className="flex flex-col items-center gap-1">
          <div
            className="flex items-center justify-center text-white font-bold"
            style={{
              width: 36,
              height: 28,
              background: (SIGNAL_COLORS as Record<string, string>)[sig.signal_level] || '#94A3B8',
              borderRadius: 4,
              fontSize: 10,
            }}
          >
            {sig.signal_level}
          </div>
          <span className="text-gray-400" style={{ fontSize: 9 }}>
            {formatDate(sig.date)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ==================== 指数信号卡片 ====================

function IndexSignalCard({ data }: { data: IndexCardData }) {
  const { macd } = data;
  const macdHistory = data.macd_history || [];

  const trendLabel = macd?.trend === 'bullish' ? '多头↑' : macd?.trend === 'bearish' ? '空头↓' : '震荡→';
  const trendColor = macd?.trend === 'bullish' ? 'text-green-600' : macd?.trend === 'bearish' ? 'text-red-500' : 'text-gray-500';

  return (
    <div className="card p-4">
      {/* 头部：指数名+代码 | 信号等级 badge */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-sm font-bold text-gray-700">{data.index_name}</span>
          <span className="text-xs text-gray-400 ml-2 font-mono">{data.index_code}</span>
        </div>
        <div
          className="flex items-center justify-center text-white font-bold rounded-full"
          style={{
            width: 28,
            height: 28,
            background: (SIGNAL_COLORS as Record<string, string>)[data.signal_level] || '#94A3B8',
            fontSize: 11,
          }}
        >
          {data.signal_level}
        </div>
      </div>

      {/* 分数 + 信号标签 + 置信度 */}
      <div className="flex items-center gap-3 mb-3">
        <div
          className="flex items-center justify-center text-white text-lg font-bold rounded-full shrink-0"
          style={{
            width: 48,
            height: 48,
            background: (SIGNAL_COLORS as Record<string, string>)[data.signal_level] || '#94A3B8',
          }}
        >
          {Math.round(data.composite_score)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-bold text-gray-700">
              {data.composite_score.toFixed(1)}
            </span>
            <span className="text-xs text-gray-400">综合分</span>
          </div>
          <p className="text-xs text-gray-500">
            {(SIGNAL_LABELS as Record<string, string>)[data.signal_level] || '未知'}
          </p>
          <div className="flex gap-0.5 mt-0.5">
            {[1, 2, 3, 4].map((s) => (
              <Star
                key={s}
                className={clsx(
                  'w-3 h-3',
                  s <= data.confidence_stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-200'
                )}
              />
            ))}
          </div>
        </div>
      </div>

      {/* MACD 趋势行 */}
      {macd && (
        <div className="mb-2">
          <div className="flex items-center gap-2 text-xs">
            <span className={clsx('font-bold', trendColor)}>{trendLabel}</span>
            <span className="text-gray-400">DIF</span>
            <span className="font-mono text-blue-500">{macd.macd_line.toFixed(2)}</span>
            <span className="text-gray-400">DEA</span>
            <span className="font-mono text-amber-500">{macd.signal_line.toFixed(2)}</span>
            <span className="text-gray-400">柱</span>
            <span
              className={clsx(
                'font-mono',
                macd.histogram >= 0 ? 'text-green-500' : 'text-red-500'
              )}
            >
              {macd.histogram.toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {/* 迷你 MACD 折线图 */}
      <div className="mb-3">
        <MiniMacdChart data={macdHistory} />
      </div>

      {/* 近3日信号色块 */}
      <div>
        <p className="text-[10px] text-gray-400 mb-1.5">近3日信号</p>
        {data.signals && data.signals.length > 0 ? (
          <SignalTimeline signals={data.signals} />
        ) : (
          <span className="text-[10px] text-gray-400">加载中...</span>
        )}
      </div>
    </div>
  );
}

// ==================== 主页面 ====================

export default function SignalBoard() {
  const { multiIndexData, loadMultiIndex, selectedIndex } = useAppStore();
  const [cardData, setCardData] = useState<IndexCardData[]>([]);
  const [loading, setLoading] = useState(true);

  // 加载多指数摘要
  useEffect(() => {
    loadMultiIndex();
  }, [loadMultiIndex]);

  // 当 multiIndexData 就绪后，并行获取每个指数的 sentiment + signalLights
  useEffect(() => {
    if (!multiIndexData || multiIndexData.length === 0) return;

    let cancelled = false;
    const loadAll = async () => {
      setLoading(true);
      try {
        // 为每个指数并行请求 sentiment + signalLights
        const results = await Promise.all(
          INDEX_CODES.map(async (code) => {
            const idx = multiIndexData.find(
              (i: any) => i.index_code === code,
            );

            const base: IndexCardData = {
              index_code: code,
              index_name: idx?.index_name || code,
              composite_score: idx?.composite_score ?? 0,
              signal_level: idx?.signal_level ?? 'B',
              confidence_stars: idx?.confidence_stars ?? 1,
            };

            // 并行获取 sentiment 和 signalLights
            const [sentimentRes, lightsRes] = await Promise.allSettled([
              fetchV5Sentiment(code),
              fetchV5SignalLights(code, 3),
            ]);

            if (sentimentRes.status === 'fulfilled') {
              base.macd = sentimentRes.value.macd || null;
              base.macd_history = sentimentRes.value.macd_history || [];
              // 用 sentiment 的最新数据覆盖（更准确）
              base.composite_score = sentimentRes.value.composite_score;
              base.signal_level = sentimentRes.value.signal_level;
              base.confidence_stars = sentimentRes.value.confidence_stars;
            }

            if (lightsRes.status === 'fulfilled') {
              base.signals = lightsRes.value.signals || [];
            }

            return base;
          }),
        );

        if (!cancelled) {
          setCardData(results);
        }
      } catch {
        // 静默失败，保留 base 数据
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadAll();
    return () => {
      cancelled = true;
    };
  }, [multiIndexData]);

  return (
    <div className="max-w-7xl mx-auto space-y-3 md:space-y-6 px-1">
      {/* Section 1: 页面标题 */}
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">信号看板</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-1">
          跨指数信号矩阵 | MACD趋势 | 信号历史
        </p>
      </div>

      {/* Section 2: 背离预警横幅 */}
      <DivergenceBanner />

      {/* Section 3: 多指数信号矩阵 */}
      {loading && cardData.length === 0 ? (
        <LoadingSpinner size="lg" text="加载信号数据..." />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {cardData.map((card) => (
            <IndexSignalCard key={card.index_code} data={card} />
          ))}
        </div>
      )}

      {/* Section 4: 信号验证看板 */}
      <div className="card p-5">
        <h3 className="text-sm font-bold text-gray-700 mb-3">信号历史验证</h3>
        <SignalVerifyBoard indexCode={selectedIndex || 'SH000300'} />
      </div>
    </div>
  );
}
