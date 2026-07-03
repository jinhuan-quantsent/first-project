/**
 * SectorSentimentPanel — 板块情绪面板
 *
 * 展示31个申万一级行业的V5三层流水线评分:
 * - 顶部摘要: 总数/趋势/逆向/排除分布 + 因子权重图例
 * - 筛选: 全部/趋势/逆向/排除 + 排序切换
 * - 板块卡片: 评分/信号/置信度/轨道/因子条/可展开理由
 * - 点击卡片展开5因子雷达图
 *
 * 浅色极简风格, greedColor 体系
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchSectorSentiment } from '../../api/sectorV5';
import type { SectorSentimentItem, SectorFactorScore } from '../../types/sector';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';
import ConfidenceStars from '../common/ConfidenceStars';
import ExpandableReason from '../common/ExpandableReason';
import { clsx } from 'clsx';
import { ArrowUpDown, Filter, Layers, RefreshCw, ChevronDown, ExternalLink } from 'lucide-react';

// ============================================================
// 常量 & 工具
// ============================================================

/** 恐惧→贪婪色阶 */
function greedColor(v: number): string {
  if (v < 30) return '#22C55E';
  if (v < 50) return '#FBBF24';
  if (v < 70) return '#F59E0B';
  return '#EF4444';
}

/** 信号等级 → 中文标签 */
const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', 'S': '恐惧', 'A': '偏恐惧', 'B': '中性',
  'C': '偏贪婪', 'D': '贪婪', 'E': '极度贪婪',
};

/** 信号等级 → hex 色 */
const SIGNAL_HEX: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

/** 轨道 → 标签 + 颜色 */
const TRACK_CONFIG: Record<string, { label: string; bg: string; text: string }> = {
  trend_follow: { label: '趋势', bg: 'bg-green-100', text: 'text-green-700' },
  contrarian:   { label: '逆向', bg: 'bg-red-100',   text: 'text-red-700' },
  excluded:     { label: '排除', bg: 'bg-gray-100',   text: 'text-gray-500' },
};

/** 因子短名 */
const FACTOR_LABELS: Record<string, string> = {
  TURN: '换手率', VOL: '波动率', NHNL: '新高占比', RSI: 'RSI', DIV: '离散度',
};

/** 筛选 tab */
type FilterTab = 'all' | 'trend_follow' | 'contrarian' | 'excluded';
type SortMode = 'desc' | 'asc';

const FILTER_TABS: { value: FilterTab; label: string }[] = [
  { value: 'all',          label: '全部' },
  { value: 'trend_follow', label: '趋势' },
  { value: 'contrarian',   label: '逆向' },
  { value: 'excluded',     label: '排除' },
];

// ============================================================
// 因子迷你条形图
// ============================================================

function FactorMiniBars({ factorScores }: { factorScores: Record<string, SectorFactorScore> }) {
  const entries = Object.entries(factorScores);
  if (entries.length === 0) return null;

  return (
    <div className="flex items-end gap-1 h-8">
      {entries.map(([name, fs]) => {
        const score = fs.sigmoid_score ?? 0;
        const barColor = greedColor(score);
        const h = Math.max(4, (score / 100) * 100);
        return (
          <div key={name} className="flex-1 flex flex-col items-center justify-end" title={`${FACTOR_LABELS[name] || name}: ${score.toFixed(1)} (权重 ${(fs.weight * 100).toFixed(0)}%)`}>
            <span className="text-[8px] text-gray-400 leading-none mb-0.5">{score.toFixed(0)}</span>
            <div
              className="w-full rounded-t-sm transition-all"
              style={{ height: `${h}%`, background: barColor, minHeight: '3px', maxHeight: '24px' }}
            />
            <span className="text-[7px] text-gray-300 leading-none mt-0.5">{name}</span>
          </div>
        );
      })}
    </div>
  );
}

// ============================================================
// 单个板块卡片
// ============================================================

function SectorCard({ item }: { item: SectorSentimentItem }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const score = item.sentiment_score;
  const scoreColor = greedColor(score);
  const trackCfg = TRACK_CONFIG[item.track] || TRACK_CONFIG.excluded;
  const signalHex = SIGNAL_HEX[item.signal_level] || '#94A3B8';

  return (
    <div
      className={clsx(
        'rounded-xl border transition-all cursor-pointer hover:shadow-md',
        expanded ? 'border-brand-200 shadow-md' : 'border-gray-100',
      )}
      style={{ background: '#fff' }}
      onClick={() => setExpanded(!expanded)}
    >
      {/* 头部: 名称 + 评分 + 信号 */}
      <div className="flex items-start justify-between p-3 pb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-gray-800 truncate">{item.sector_name}</span>
            <span className={clsx('text-[10px] px-1.5 py-0.5 rounded-full font-medium', trackCfg.bg, trackCfg.text)}>
              {trackCfg.label}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-gray-400 font-mono">{item.sector_code}</span>
            <span className="text-[10px] text-gray-300">{item.sector_group}</span>
          </div>
        </div>
        {/* 评分圆 */}
        <div className="flex-shrink-0 flex flex-col items-center">
          <div
            className="w-11 h-11 rounded-full flex items-center justify-center text-white text-base font-bold"
            style={{ background: scoreColor }}
          >
            {Math.round(score)}
          </div>
          <div className="flex items-center gap-1 mt-1">
            <span
              className="text-[10px] font-bold"
              style={{ color: signalHex }}
            >
              {item.signal_level}
            </span>
            <span className="text-[9px] text-gray-400">{SIGNAL_LABELS[item.signal_level]}</span>
          </div>
        </div>
      </div>

      {/* 置信度 + 动量 */}
      <div className="flex items-center justify-between px-3 pb-2">
        <ConfidenceStars stars={item.confidence_stars} size="sm" />
        <div className="flex items-center gap-3 text-[10px]">
          <span className={clsx(item.momentum_5d >= 0 ? 'text-red-400' : 'text-green-500')}>
            5D {item.momentum_5d >= 0 ? '+' : ''}{item.momentum_5d.toFixed(1)}%
          </span>
          <span className={clsx(item.momentum_20d >= 0 ? 'text-red-400' : 'text-green-500')}>
            20D {item.momentum_20d >= 0 ? '+' : ''}{item.momentum_20d.toFixed(1)}%
          </span>
        </div>
      </div>

      {/* 因子迷你条 */}
      <div className="px-3 pb-2">
        <FactorMiniBars factorScores={item.factor_scores} />
      </div>

      {/* 展开区域: 三段式理由 + 因子详情 */}
      <div
        style={{
          maxHeight: expanded ? '400px' : '0px',
          opacity: expanded ? 1 : 0,
          overflow: 'hidden',
          transition: 'max-height 250ms ease, opacity 200ms ease',
        }}
      >
        <div className="px-3 pb-3 border-t border-gray-50 pt-2 space-y-2">
          {/* 因子明细 */}
          <div className="grid grid-cols-5 gap-1.5">
            {Object.entries(item.factor_scores).map(([name, fs]) => (
              <div key={name} className="bg-gray-50 rounded-lg p-1.5 text-center">
                <p className="text-[9px] text-gray-400">{FACTOR_LABELS[name] || name}</p>
                <p className="text-xs font-bold" style={{ color: greedColor(fs.sigmoid_score) }}>
                  {fs.sigmoid_score.toFixed(1)}
                </p>
                <p className="text-[8px] text-gray-300">{(fs.weight * 100).toFixed(0)}%</p>
              </div>
            ))}
          </div>

          {/* 三段式理由 */}
          <ExpandableReason
            reason={item.reason}
            signalLevel={item.signal_level}
            variant="compact"
            defaultExpanded={true}
            className="border-0"
          />

          {/* 数据质量 */}
          <div className="flex items-center gap-3 text-[10px] text-gray-400">
            <span>完整度: {(item.factor_completeness * 100).toFixed(0)}%</span>
            <span>强度: {item.strength_index.toFixed(0)}</span>
            <span>排名: #{item.strength_rank}</span>
            {item.cold_start && <span className="text-orange-400">冷启动</span>}
          </div>

          {/* 触发防御 */}
          {item.triggered_defenses && item.triggered_defenses.length > 0 && (
            <div className="flex items-center gap-1 flex-wrap">
              {item.triggered_defenses.map((d) => (
                <span key={d} className="text-[9px] px-1.5 py-0.5 rounded bg-orange-50 text-orange-400 border border-orange-100">
                  {d}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 展开提示 + 查看详情 */}
      <div className="flex items-center justify-between px-3 pb-1">
        <ChevronDown
          className={clsx('w-3.5 h-3.5 text-gray-300 transition-transform', expanded && 'rotate-180')}
        />
        <button
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/sectors/${item.sector_code}`);
          }}
          className="flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600 transition-colors"
        >
          查看详情
          <ExternalLink className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

// ============================================================
// 主组件
// ============================================================

export default function SectorSentimentPanel() {
  const [data, setData] = useState<SectorSentimentItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterTab>('all');
  const [sortMode, setSortMode] = useState<SortMode>('desc');
  const [elapsed, setElapsed] = useState(0);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchSectorSentiment();
      setData(res.sectors);
      setElapsed(res.elapsed_seconds);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '加载失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 筛选 + 排序
  const filteredData = useMemo(() => {
    if (!data) return [];
    let result = data;
    if (filter !== 'all') {
      result = result.filter((s) => s.track === filter);
    }
    result = [...result].sort((a, b) =>
      sortMode === 'desc'
        ? b.sentiment_score - a.sentiment_score
        : a.sentiment_score - b.sentiment_score,
    );
    return result;
  }, [data, filter, sortMode]);

  // 统计
  const stats = useMemo(() => {
    if (!data) return { total: 0, trend: 0, contrarian: 0, excluded: 0, avg: 0 };
    const trend = data.filter((s) => s.track === 'trend_follow').length;
    const contrarian = data.filter((s) => s.track === 'contrarian').length;
    const excluded = data.filter((s) => s.track === 'excluded').length;
    const avg = data.length > 0 ? data.reduce((sum, s) => sum + s.sentiment_score, 0) / data.length : 0;
    return { total: data.length, trend, contrarian, excluded, avg };
  }, [data]);

  if (loading) {
    return <LoadingSpinner size="lg" text="计算31个板块V5评分中（约25秒）..." />;
  }

  if (error) {
    return <ErrorMessage message={error} onRetry={loadData} />;
  }

  if (!data || data.length === 0) {
    return <ErrorMessage message="暂无板块数据" onRetry={loadData} />;
  }

  return (
    <div className="space-y-4">
      {/* 顶部摘要 */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-brand-500" />
            <h3 className="text-sm font-bold text-gray-700">板块情绪总览</h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-gray-400">耗时 {elapsed.toFixed(1)}s</span>
            <button
              onClick={loadData}
              className="flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600"
            >
              <RefreshCw className="w-3 h-3" />
              刷新
            </button>
          </div>
        </div>

        {/* 分布统计 */}
        <div className="grid grid-cols-4 gap-2">
          <div className="bg-gray-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-gray-400">板块总数</p>
            <p className="text-lg font-bold text-gray-700">{stats.total}</p>
          </div>
          <div className="bg-green-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-green-400">趋势轨道</p>
            <p className="text-lg font-bold text-green-600">{stats.trend}</p>
          </div>
          <div className="bg-red-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-red-400">逆向轨道</p>
            <p className="text-lg font-bold text-red-600">{stats.contrarian}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-gray-400">排除区</p>
            <p className="text-lg font-bold text-gray-500">{stats.excluded}</p>
          </div>
        </div>

        {/* 平均分 */}
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[10px] text-gray-400">平均情绪分</span>
          <span className="text-sm font-bold" style={{ color: greedColor(stats.avg) }}>
            {stats.avg.toFixed(1)}
          </span>
        </div>
      </div>

      {/* 筛选 + 排序 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Filter className="w-3.5 h-3.5 text-gray-400" />
          {FILTER_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setFilter(tab.value)}
              className={clsx(
                'px-2.5 py-1 rounded-lg text-xs font-medium transition-colors',
                filter === tab.value
                  ? 'bg-brand-500 text-white'
                  : 'bg-gray-50 text-gray-500 hover:bg-gray-100',
              )}
            >
              {tab.label}
              {tab.value !== 'all' && (
                <span className="ml-1 text-[10px] opacity-70">
                  {tab.value === 'trend_follow' ? stats.trend : tab.value === 'contrarian' ? stats.contrarian : stats.excluded}
                </span>
              )}
            </button>
          ))}
        </div>
        <button
          onClick={() => setSortMode(sortMode === 'desc' ? 'asc' : 'desc')}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-gray-500 bg-gray-50 hover:bg-gray-100"
        >
          <ArrowUpDown className="w-3 h-3" />
          {sortMode === 'desc' ? '高→低' : '低→高'}
        </button>
      </div>

      {/* 板块卡片网格 */}
      {filteredData.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-gray-400">当前筛选条件下暂无板块</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filteredData.map((item) => (
            <SectorCard key={item.sector_code} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
