/**
 * SectorRadarPanel — 机会雷达面板（双轨制推荐）
 *
 * 展示双轨制推荐引擎结果:
 * - 逆向机会区: signal S+/S, 底部背离, 按分数升序, 红色系
 * - 趋势机会区: signal A/B/C, MA20上升, 按分数降序, 绿色系
 * - 排除区: 不符合双轨条件的板块列表（可折叠）
 *
 * V5.2 改造：
 * - 同区一起展开：点任意卡片→整区展开；再点→整区折叠
 * - 基金直接显示：展开时调用 /funds API 加载关联基金
 * - 删除"查看详情"跳转按钮
 */
import { useState, useEffect, useCallback } from 'react';
import { fetchSectorRadar } from '../../api/sectorV5';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { addWatchlistV5 } from '../../api/watchlistV5';
import { useWatchlistV5Store } from '../../stores/watchlistV5';
import { toast } from '../common/Toast';
import { Plus, Check } from 'lucide-react';
import { fetchSectorRatings, fetchSectorFunds } from '../../api/sectorDetailV5';
import type { SectorRadarData, SectorOpportunity } from '../../types/sector';
import type { PositionRating, SectorFund } from '../../types/positionRating';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';
import ConfidenceStars from '../common/ConfidenceStars';
import ExpandableReason from '../common/ExpandableReason';
import PositionRatingBadge from './PositionRatingBadge';
import { clsx } from 'clsx';
import {
  TrendingUp, TrendingDown, RefreshCw,
  ChevronDown, ChevronRight, Eye, Radar, Ban, Filter,
} from 'lucide-react';

// ============================================================
// 常量 & 工具
// ============================================================

function greedColor(v: number): string {
  if (v < 30) return '#22C55E';
  if (v < 50) return '#FBBF24';
  if (v < 70) return '#F59E0B';
  return '#EF4444';
}

const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', 'S': '恐惧', 'A': '偏恐惧', 'B': '中性',
  'C': '偏贪婪', 'D': '贪婪', 'E': '极度贪婪',
};

const SIGNAL_HEX: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

const FACTOR_LABELS: Record<string, string> = {
  TURN: '换手率', VOL: '波动率', NHNL: '新高占比', RSI: 'RSI', DIV: '离散度',
};

const FIT_LABELS: Record<number, string> = {
  1: '一级',
  2: '二级',
};

// ============================================================
// 推荐卡片（展开式，无跳转）
// ============================================================

function OpportunityCard({
  item,
  variant,
  rating,
  ratingType,
  expanded,
  onToggle,
  funds,
  fundsLoading,
  onAddWatchlist,
  addingFund,
}: {
  item: SectorOpportunity;
  variant: 'contrarian' | 'trend';
  rating?: PositionRating;
  ratingType?: string;
  expanded: boolean;
  onToggle: () => void;
  funds: SectorFund[];
  fundsLoading: boolean;
  onAddWatchlist: (fundCode: string, fundName: string) => void;
  addingFund: string | null;
}) {
  const isContrarian = variant === 'contrarian';
  const score = item.sentiment_score;
  const scoreColor = greedColor(score);
  const signalHex = SIGNAL_HEX[item.signal_level] || '#94A3B8';

  const cardBorder = expanded
    ? (isContrarian ? 'border-red-200 shadow-md' : 'border-green-200 shadow-md')
    : (isContrarian ? 'border-red-100' : 'border-green-100');
  const rankBg = isContrarian ? 'bg-red-500' : 'bg-green-500';
  const accentBar = isContrarian ? 'bg-red-400' : 'bg-green-400';

  const typeLabel = ratingType === 'contrarian' ? '逆向' : ratingType === 'trend' ? '顺势' : ratingType === 'forbidden' ? '禁止' : '';

  return (
    <div
      className={clsx('rounded-xl border overflow-hidden transition-all hover:shadow-md cursor-pointer', cardBorder)}
      style={{ background: '#fff' }}
      onClick={onToggle}
    >
      {/* 顶部色带 */}
      <div className={clsx('h-1', accentBar)} />

      <div className="p-3">
        {/* 头部: 排名 + 名称 + 评分 + 建仓评级 */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className={clsx('w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold', rankBg)}>
              {item.rank}
            </div>
            <div>
              <p className="text-sm font-bold text-gray-800">{item.sector_name}</p>
              <p className="text-[10px] text-gray-400 font-mono">{item.sector_code} · {item.sector_group}</p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            {rating && <PositionRatingBadge rating={rating} />}
            <div className="flex items-center gap-1">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
                style={{ background: scoreColor }}
              >
                {Math.round(score)}
              </div>
            </div>
            <span className="text-[10px] font-bold" style={{ color: signalHex }}>
              {item.signal_level}
            </span>
          </div>
        </div>

        {/* 置信度 + 动量 */}
        <div className="flex items-center justify-between mb-2">
          <ConfidenceStars stars={item.confidence_stars} size="sm" showLabel />
          <div className="flex items-center gap-2 text-[10px]">
            <span className={clsx(item.momentum_5d >= 0 ? 'text-red-400' : 'text-green-500')}>
              5D {item.momentum_5d >= 0 ? '+' : ''}{item.momentum_5d.toFixed(1)}%
            </span>
            <span className={clsx(item.momentum_20d >= 0 ? 'text-red-400' : 'text-green-500')}>
              20D {item.momentum_20d >= 0 ? '+' : ''}{item.momentum_20d.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* 因子条（收起时） */}
        <div className="flex items-end gap-1 h-6 mb-2">
          {Object.entries(item.factor_scores).map(([name, fs]) => {
            const s = fs.sigmoid_score ?? 0;
            const h = Math.max(4, (s / 100) * 100);
            return (
              <div key={name} className="flex-1 flex flex-col items-center justify-end"
                title={`${FACTOR_LABELS[name] || name}: ${s.toFixed(1)} (权重 ${(fs.weight * 100).toFixed(0)}%)`}
              >
                <div
                  className="w-full rounded-t-sm"
                  style={{ height: `${h}%`, background: greedColor(s), minHeight: '3px', maxHeight: '20px' }}
                />
                <span className="text-[7px] text-gray-300 mt-0.5">{name}</span>
              </div>
            );
          })}
        </div>

        {/* 推荐理由（收起时） */}
        {item.opportunity_reason && (
          <div className={clsx('rounded-lg p-2 mb-2', isContrarian ? 'bg-red-50' : 'bg-green-50')}>
            <p className="text-[11px] text-gray-600 leading-relaxed">
              {item.opportunity_reason}
            </p>
          </div>
        )}

        {/* ====== 展开区域 ====== */}
        <div
          style={{
            maxHeight: expanded ? '800px' : '0px',
            opacity: expanded ? 1 : 0,
            overflow: 'hidden',
            transition: 'max-height 250ms ease, opacity 200ms ease',
          }}
        >
          <div className="border-t border-gray-50 pt-2 space-y-2">

            {/* 因子明细网格 */}
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
              {Object.entries(item.factor_scores).map(([name, fs]) => (
                <div key={name} className="bg-gray-50 rounded-lg p-1.5 text-center">
                  <p className="text-[9px] text-gray-400">{FACTOR_LABELS[name] || name}</p>
                  <p className="text-xs font-bold" style={{ color: greedColor(fs.sigmoid_score ?? 0) }}>
                    {(fs.sigmoid_score ?? 0).toFixed(1)}
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

            {/* 建仓评级详情 */}
            {rating && (
              <div className={clsx('rounded-lg p-2', isContrarian ? 'bg-red-50' : 'bg-green-50')}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] text-gray-500">建仓评级:</span>
                  <PositionRatingBadge rating={rating} showLabel size="md" />
                  <span className="text-[10px] text-gray-400">({typeLabel}轨道)</span>
                </div>
              </div>
            )}

            {/* 推荐基金（直接显示完整信息） */}
            {fundsLoading ? (
              <div className="flex items-center gap-2 py-1">
                <div className="w-3 h-3 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                <span className="text-[10px] text-gray-400">加载基金...</span>
              </div>
            ) : funds.length > 0 ? (
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                <span className="text-[10px] text-gray-500 font-medium">关联基金:</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    funds.forEach(f => onAddWatchlist(f.fund_code, f.fund_name));
                  }}
                  className="flex items-center gap-0.5 text-[9px] text-brand-500 hover:text-brand-600 hover:bg-brand-50 px-1.5 py-0.5 rounded-full transition-colors"
                  title="将此板块所有基金加入自选"
                >
                  <Plus className="w-2.5 h-2.5" />
                  全部加自选
                </button>
              </div>
                {funds.map((f) => {
                  const isAdding = addingFund === f.fund_code;
                  return (
                  <div
                    key={f.fund_code}
                    className={clsx(
                      'flex items-center justify-between rounded-lg px-2 py-1.5',
                      f.fund_level === 1 ? 'bg-blue-50' : 'bg-gray-50',
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={clsx(
                          'text-[9px] px-1 py-0.5 rounded-full font-medium',
                          f.fund_level === 1 ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-500',
                        )}
                      >
                        {FIT_LABELS[f.fund_level] || `${f.fund_level}级`}
                      </span>
                      <span className="text-[11px] text-gray-700 font-medium">{f.fund_name}</span>
                      <span className="text-[9px] text-gray-400 font-mono">{f.fund_code}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] text-gray-400">拟合</span>
                      <span className="text-[10px] font-bold" style={{
                        color: f.fit_degree >= 90 ? '#16a34a' : f.fit_degree >= 70 ? '#eab308' : '#6b7280',
                      }}>
                        {f.fit_degree.toFixed(0)}%
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onAddWatchlist(f.fund_code, f.fund_name);
                        }}
                        disabled={isAdding}
                        className={clsx(
                          'flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded-full transition-colors',
                          isAdding
                            ? 'bg-green-100 text-green-600'
                            : 'bg-brand-50 text-brand-500 hover:bg-brand-100',
                        )}
                      >
                        {isAdding ? (
                          <>
                            <Check className="w-2.5 h-2.5" />
                            已加入
                          </>
                        ) : (
                          <>
                            <Plus className="w-2.5 h-2.5" />
                            加自选
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-gray-400">暂无关联基金</span>
              </div>
            )}

            {/* 数据质量 */}
            <div className="flex items-center gap-3 text-[10px] text-gray-400">
              <span>完整度: {(item.factor_completeness * 100).toFixed(0)}%</span>
              {item.cold_start && <span className="text-orange-400">冷启动</span>}
            </div>
          </div>
        </div>

        {/* 展开提示 */}
        <div className="flex items-center justify-center px-1 pb-1">
          <ChevronDown
            className={clsx('w-3.5 h-3.5 text-gray-300 transition-transform', expanded && 'rotate-180')}
          />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 空状态
// ============================================================

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-16 h-16 rounded-full bg-gray-50 flex items-center justify-center mb-3">
        <Eye className="w-7 h-7 text-gray-300" />
      </div>
      <p className="text-sm text-gray-400 text-center">{message}</p>
      <p className="text-[10px] text-gray-300 mt-1">建议观望，等待信号触发</p>
    </div>
  );
}

// ============================================================
// 主组件
// ============================================================

export default function SectorRadarPanel() {
  const [data, setData] = useState<SectorRadarData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showExcluded, setShowExcluded] = useState(false);
  const [ratingFilter, setRatingFilter] = useState<'all' | 'trend' | 'contrarian' | 'strong'>('all');
  const [ratings, setRatings] = useState<Record<string, { rating: PositionRating; type: string; reason: string }>>({});

  // 展开状态：按区域分组，'contrarian' 或 'trend' 表示该区全部展开
  const [expandedZone, setExpandedZone] = useState<'contrarian' | 'trend' | null>(null);

  // 基金数据缓存：sector_code → SectorFund[]
  const [sectorFunds, setSectorFunds] = useState<Record<string, SectorFund[]>>({});
  const [fundsLoading, setFundsLoading] = useState(false);
  const [addingFund, setAddingFund] = useState<string | null>(null);

    const handleAddWatchlist = useCallback(async (fundCode: string, fundName: string) => {
    setAddingFund(fundCode);
    console.log(`[Watchlist] Adding ${fundName} (${fundCode})...`);
    try {
      const result = await addWatchlistV5({ fund_code: fundCode });
      console.log(`[Watchlist] Success: ${fundName} added`);
      toast.success(`已添加「${fundName}」到自选`);
      // 乐观更新：立即往store追加，不等loadAll（关键修复！确保切到自选页能看到）
      useWatchlistV5Store.getState().addFundOptimistic({
        fund_code: fundCode,
        fund_name: fundName,
        id: result?.id,
      });
      // 再异步loadAll刷新完整数据（含评级等）
      useWatchlistV5Store.getState().loadAll().catch(e => console.warn("[Watchlist] loadAll refresh failed:", e));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '添加失败';
      console.error(`[Watchlist] Failed:`, e);
      toast.error(String(msg));
    } finally {
      setTimeout(() => setAddingFund(null), 1500);
    }
  }, []);
  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [radarRes, ratingsRes] = await Promise.all([
        fetchSectorRadar(),
        fetchSectorRatings().catch(() => ({})),
      ]);
      setData(radarRes);
      setRatings(ratingsRes);
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

  useAutoRefresh(['sector'], () => loadData());

  // 区域展开时，批量加载该区域所有板块的基金数据
  const loadFundsForZone = useCallback(async (zone: 'contrarian' | 'trend') => {
    if (!data) return;
    const items = zone === 'contrarian'
      ? (data.contrarian_opportunities || [])
      : (data.trend_follow_opportunities || []);

    // 只加载还没缓存的板块基金
    const codesToLoad = items
      .map(i => i.sector_code)
      .filter(code => !sectorFunds[code]);

    if (codesToLoad.length === 0) return;

    setFundsLoading(true);
    try {
      const results = await Promise.all(
        codesToLoad.map(code => fetchSectorFunds(code).catch(() => [])),
      );
      const newFunds: Record<string, SectorFund[]> = {};
      codesToLoad.forEach((code, idx) => {
        newFunds[code] = results[idx];
      });
      setSectorFunds(prev => ({ ...prev, ...newFunds }));
    } finally {
      setFundsLoading(false);
    }
  }, [data, sectorFunds]);

  // 点击卡片时：如果该区已展开→折叠；否则→展开并加载基金
  const handleZoneToggle = useCallback((zone: 'contrarian' | 'trend') => {
    if (expandedZone === zone) {
      setExpandedZone(null);
    } else {
      setExpandedZone(zone);
      loadFundsForZone(zone);
    }
  }, [expandedZone, loadFundsForZone]);

  // 筛选函数
  const filterOpportunities = useCallback((items: SectorOpportunity[]) => {
    if (ratingFilter === 'all') return items;
    return items.filter((item) => {
      const r = ratings[item.sector_code];
      if (!r) return false;
      if (ratingFilter === 'strong') return r.rating === 'strong';
      if (ratingFilter === 'trend') return r.type === 'trend';
      if (ratingFilter === 'contrarian') return r.type === 'contrarian';
      return true;
    });
  }, [ratings, ratingFilter]);

  const RATING_FILTERS: { value: typeof ratingFilter; label: string }[] = [
    { value: 'all', label: '全部' },
    { value: 'trend', label: '仅顺势' },
    { value: 'contrarian', label: '仅逆向' },
    { value: 'strong', label: '仅强烈建仓' },
  ];

  if (loading) {
    return <LoadingSpinner size="lg" text="生成双轨制推荐中..." />;
  }

  if (error) {
    if (error.includes('均未通过') || error.includes('无推荐')) {
      return (
        <div className="space-y-4">
          <div className="card p-4">
            <EmptyState message={error} />
          </div>
          {data && (
            <div className="card p-4">
              <p className="text-xs text-gray-400">统计: 共 {data.total_count} 个板块，排除 {data.excluded_count} 个</p>
            </div>
          )}
        </div>
      );
    }
    return <ErrorMessage message={error} onRetry={loadData} />;
  }

  if (!data) {
    return <ErrorMessage message="暂无数据" onRetry={loadData} />;
  }

  const contrarian = filterOpportunities(data.contrarian_opportunities || []);
  const trend = filterOpportunities(data.trend_follow_opportunities || []);

  const contrarianExpanded = expandedZone === 'contrarian';
  const trendExpanded = expandedZone === 'trend';

  return (
    <div className="space-y-4">
      {/* 统计摘要 */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Radar className="w-4 h-4 text-brand-500" />
            <h3 className="text-sm font-bold text-gray-700">机会雷达</h3>
          </div>
          <button
            onClick={loadData}
            className="flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600"
          >
            <RefreshCw className="w-3 h-3" />
            刷新
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="bg-gray-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-gray-400">总板块</p>
            <p className="text-lg font-bold text-gray-700">{data.total_count}</p>
          </div>
          <div className="bg-red-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-red-400">逆向机会</p>
            <p className="text-lg font-bold text-red-600">{data.contrarian_count}</p>
          </div>
          <div className="bg-green-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-green-400">趋势机会</p>
            <p className="text-lg font-bold text-green-600">{data.trend_follow_count}</p>
          </div>
          <div className="bg-gray-50 rounded-lg p-2.5 text-center">
            <p className="text-[10px] text-gray-400">排除区</p>
            <p className="text-lg font-bold text-gray-500">{data.excluded_count}</p>
          </div>
        </div>

        {data.summary && (
          <p className="text-[11px] text-gray-400 mt-2 leading-relaxed">{data.summary}</p>
        )}
      </div>

      {/* 建仓评级筛选器 */}
      <div className="flex items-center gap-2">
        <Filter className="w-3.5 h-3.5 text-gray-400" />
        {RATING_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setRatingFilter(f.value)}
            className={clsx(
              'px-2.5 py-1 rounded-lg text-xs font-medium transition-colors',
              ratingFilter === f.value
                ? 'bg-brand-500 text-white'
                : 'bg-gray-50 text-gray-500 hover:bg-gray-100',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 逆向机会区 */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <TrendingDown className="w-4 h-4 text-red-500" />
          <h3 className="text-sm font-bold text-gray-700">逆向机会</h3>
          <span className="text-[10px] text-gray-400">底部区域 · 按恐惧度升序</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-600 font-medium">
            {contrarian.length}
          </span>
          {contrarianExpanded && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-50 text-red-400">
              点击折叠
            </span>
          )}
        </div>
        {contrarian.length === 0 ? (
          <div className="card p-4">
            <EmptyState message="当前无逆向机会" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {contrarian.map((item) => (
              <OpportunityCard
                key={item.sector_code}
                item={item}
                variant="contrarian"
                rating={ratings[item.sector_code]?.rating}
                ratingType={ratings[item.sector_code]?.type}
                expanded={contrarianExpanded}
                onToggle={() => handleZoneToggle('contrarian')}
                funds={sectorFunds[item.sector_code] || []}
                fundsLoading={fundsLoading && !sectorFunds[item.sector_code]}
                onAddWatchlist={handleAddWatchlist}
                addingFund={addingFund}
              />
            ))}
          </div>
        )}
      </div>

      {/* 趋势机会区 */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <TrendingUp className="w-4 h-4 text-green-500" />
          <h3 className="text-sm font-bold text-gray-700">趋势机会</h3>
          <span className="text-[10px] text-gray-400">MA20上升 · 按贪婪度降序</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-600 font-medium">
            {trend.length}
          </span>
          {trendExpanded && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-50 text-green-400">
              点击折叠
            </span>
          )}
        </div>
        {trend.length === 0 ? (
          <div className="card p-4">
            <EmptyState message="当前无趋势机会" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {trend.map((item) => (
              <OpportunityCard
                key={item.sector_code}
                item={item}
                variant="trend"
                rating={ratings[item.sector_code]?.rating}
                ratingType={ratings[item.sector_code]?.type}
                expanded={trendExpanded}
                onToggle={() => handleZoneToggle('trend')}
                funds={sectorFunds[item.sector_code] || []}
                fundsLoading={fundsLoading && !sectorFunds[item.sector_code]}
                onAddWatchlist={handleAddWatchlist}
                addingFund={addingFund}
              />
            ))}
          </div>
        )}
      </div>

      {/* 排除区（可折叠） */}
      {data.excluded_count > 0 && (
        <div>
          <button
            onClick={() => setShowExcluded(!showExcluded)}
            className="flex items-center gap-2 mb-2 text-gray-500 hover:text-gray-700"
          >
            {showExcluded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            <Ban className="w-4 h-4 text-gray-400" />
            <h3 className="text-sm font-bold">排除区板块</h3>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 font-medium">
              {data.excluded_count}
            </span>
          </button>
          {showExcluded && (
            <div className="card p-3">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {(data.all_recommendations || [])
                  .filter((s) => s.track === 'excluded')
                  .map((s) => (
                    <div key={s.sector_code} className="flex items-center justify-between bg-gray-50 rounded-lg px-2 py-1.5">
                      <div>
                        <span className="text-xs text-gray-600">{s.sector_name}</span>
                        <span className="text-[9px] text-gray-300 ml-1">{s.sector_code}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span
                          className="text-[10px] font-bold"
                          style={{ color: greedColor(s.sentiment_score) }}
                        >
                          {s.sentiment_score.toFixed(0)}
                        </span>
                        <span
                          className="text-[9px]"
                          style={{ color: SIGNAL_HEX[s.signal_level] || '#94A3B8' }}
                        >
                          {s.signal_level}
                        </span>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
