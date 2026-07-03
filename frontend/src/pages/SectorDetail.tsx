/**
 * SectorDetail — 板块详情页
 *
 * 路由: /sectors/:code
 *
 * 对接 API: GET /api/v5/sector/position-rating/{sector_code}
 *
 * 页面结构:
 *  - 顶部信息区: 板块名称/评级标签/轨道/信号/置信度/综合评分/仓位建议
 *  - 评级原因
 *  - 指标卡: 综合评分/仓位建议/换手分位/底背离
 *  - 双Tab: 一级基金 / 二级基金
 *  - 基金卡片: SectorFundCard 组件
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchSectorDetail } from '../api/sectorDetailV5';
import type { PositionRatingItem, SectorFund } from '../types/positionRating';
import { POSITION_RATING_CONFIG } from '../types/positionRating';
import SectorFundCard from '../components/sector/SectorFundCard';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import ConfidenceStars from '../components/common/ConfidenceStars';
import { clsx } from 'clsx';
import {
  ArrowLeft,
  RefreshCw,
  Layers,
  ChevronRight,
  Target,
  TrendingUp,
  AlertTriangle,
} from 'lucide-react';

// ============================================================
// 常量 & 工具
// ============================================================

const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', 'S': '恐惧', 'A': '偏恐惧', 'B': '中性',
  'C': '偏贪婪', 'D': '贪婪', 'E': '极度贪婪',
};

const SIGNAL_HEX: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

const TRACK_LABELS: Record<string, string> = {
  trend_follow: '顺势建仓',
  contrarian: '逆向建仓',
};

function scoreColor(v: number): string {
  if (v < 30) return '#22C55E';
  if (v < 50) return '#FBBF24';
  if (v < 70) return '#F59E0B';
  return '#EF4444';
}

// ============================================================
// 顶部信息区
// ============================================================

function SectorHeader({ data, onRefresh }: { data: PositionRatingItem; onRefresh: () => void }) {
  const ratingCfg = POSITION_RATING_CONFIG[data.rating];
  const signalHex = SIGNAL_HEX[data.signal_level] || '#94A3B8';
  const trackLabel = TRACK_LABELS[data.track] || data.track;
  const posPct = Math.round(data.position_suggestion * 100);

  return (
    <div className="card p-4 md:p-5">
      {/* 返回 + 刷新 */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => window.history.back()}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          返回板块列表
        </button>
        <button
          onClick={onRefresh}
          className="flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600"
        >
          <RefreshCw className="w-3 h-3" />
          刷新
        </button>
      </div>

      {/* 主信息区 */}
      <div className="flex flex-col md:flex-row md:items-start gap-4">
        {/* 左: 板块名称 + 综合评分圆 */}
        <div className="flex items-center gap-3">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center text-white text-xl font-bold shrink-0"
            style={{ background: scoreColor(data.composite_score) }}
          >
            {Math.round(data.composite_score)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg md:text-xl font-bold text-gray-800">{data.sector_name}</h1>
              <span className="text-[10px] text-gray-400 font-mono">{data.sector_code}</span>
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 rounded text-white"
                style={{ background: signalHex }}
              >
                {data.signal_level} {SIGNAL_LABELS[data.signal_level]}
              </span>
              <ConfidenceStars stars={data.confidence_stars} size="sm" showLabel />
            </div>
          </div>
        </div>

        {/* 右: 建仓评级 + 轨道 */}
        <div className="flex-1 flex flex-col gap-2 md:items-end">
          {/* 建仓评级标签 */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-gray-400">建仓评级</span>
            <span
              className={clsx(
                'text-sm font-bold px-3 py-1 rounded-full border',
                ratingCfg.bg,
                ratingCfg.text,
                ratingCfg.border,
              )}
            >
              {ratingCfg.label}
            </span>
            <span className="text-[10px] text-gray-400">({trackLabel})</span>
          </div>
          {/* 仓位建议 */}
          <div className="flex items-center gap-2 text-[10px]">
            <Target className="w-3 h-3 text-gray-400" />
            <span className="text-gray-400">建议仓位:</span>
            <span className="font-bold text-gray-700">{posPct}%</span>
          </div>
        </div>
      </div>

      {/* 评级原因 */}
      <div className={clsx('rounded-lg p-3 mt-4', ratingCfg.bg)}>
        <p className={clsx('text-xs leading-relaxed', ratingCfg.text)}>
          <span className="font-bold">判定原因: </span>
          {data.reason}
        </p>
      </div>

      {/* 指标卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
        {/* 综合评分 */}
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <p className="text-[9px] text-gray-400">综合评分</p>
          <p className="text-sm font-bold font-mono" style={{ color: scoreColor(data.composite_score) }}>
            {data.composite_score.toFixed(1)}
          </p>
        </div>
        {/* 仓位建议 */}
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <p className="text-[9px] text-gray-400">仓位建议</p>
          <p className="text-sm font-bold text-gray-700">{posPct}%</p>
        </div>
        {/* 换手分位 */}
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <p className="text-[9px] text-gray-400">换手分位</p>
          <p className="text-sm font-bold text-gray-700">
            {data.turn_percentile != null ? `${(data.turn_percentile * 100).toFixed(0)}%` : '—'}
          </p>
        </div>
        {/* 底背离 */}
        <div className="bg-gray-50 rounded-lg p-2 text-center">
          <p className="text-[9px] text-gray-400">底背离</p>
          <p className={clsx('text-sm font-bold', data.bottom_divergence ? 'text-green-600' : 'text-gray-400')}>
            {data.bottom_divergence ? '是' : '否'}
          </p>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 主页面
// ============================================================

export default function SectorDetail() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<PositionRatingItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'primary' | 'secondary'>('primary');

  const loadData = useCallback(async () => {
    if (!code) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchSectorDetail(code);
      setData(res);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '加载失败';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 按基金级别分组
  const { primaryFunds, secondaryFunds, hasSecondary } = useMemo(() => {
    if (!data?.funds) return { primaryFunds: [], secondaryFunds: [], hasSecondary: false };
    const primary = data.funds.filter((f) => f.fund_level === 1);
    const secondary = data.funds.filter((f) => f.fund_level === 2);
    return {
      primaryFunds: primary,
      secondaryFunds: secondary,
      hasSecondary: secondary.length > 0,
    };
  }, [data]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto">
        <LoadingSpinner size="lg" text="加载板块评级中..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto">
        <ErrorMessage message={error} onRetry={loadData} />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-5xl mx-auto">
        <ErrorMessage message="暂无板块数据" onRetry={loadData} />
      </div>
    );
  }

  const funds = tab === 'primary' ? primaryFunds : secondaryFunds;

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* 顶部信息区 */}
      <SectorHeader data={data} onRefresh={loadData} />

      {/* 双Tab: 一级行业基金 / 二级细分基金 */}
      <div className="flex items-center gap-2 border-b border-gray-100">
        <button
          onClick={() => setTab('primary')}
          className={clsx(
            'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
            tab === 'primary'
              ? 'text-brand-600 border-brand-500'
              : 'text-gray-400 border-transparent hover:text-gray-600',
          )}
        >
          <Layers className="w-4 h-4" />
          一级行业基金
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
            {primaryFunds.length}
          </span>
        </button>
        <button
          disabled={!hasSecondary}
          onClick={() => hasSecondary && setTab('secondary')}
          className={clsx(
            'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
            tab === 'secondary'
              ? 'text-brand-600 border-brand-500'
              : 'text-gray-400 border-transparent hover:text-gray-600',
            !hasSecondary && 'opacity-40 cursor-not-allowed',
          )}
        >
          <ChevronRight className="w-4 h-4" />
          二级细分基金
          {!hasSecondary && (
            <span className="text-[9px] text-gray-300">(暂无)</span>
          )}
          {hasSecondary && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
              {secondaryFunds.length}
            </span>
          )}
        </button>
      </div>

      {/* 二级赛道提示条 */}
      {tab === 'secondary' && data.level2_hint && (
        <div className={clsx(
          'rounded-lg px-3 py-2 text-xs flex items-center gap-2',
          hasSecondary ? 'bg-blue-50 text-blue-600' : 'bg-gray-50 text-gray-400',
        )}>
          <ChevronRight className="w-3.5 h-3.5 shrink-0" />
          {data.level2_hint}
          {hasSecondary && (
            <span className="text-[10px] text-blue-400 ml-auto">
              {secondaryFunds.length} 只二级赛道基金
            </span>
          )}
        </div>
      )}

      {/* 基金列表 */}
      {funds.length === 0 ? (
        <div className="card p-8 text-center">
          <div className="w-14 h-14 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3">
            <Layers className="w-6 h-6 text-gray-300" />
          </div>
          <p className="text-sm text-gray-400">该板块暂无关联基金</p>
          <p className="text-[10px] text-gray-300 mt-1">
            后续将补充更多板块关联基金数据
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {funds.map((fund) => (
            <SectorFundCard
              key={fund.fund_code}
              fund={fund}
              onViewDetail={(fundCode) => navigate(`/?fund=${fundCode}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
