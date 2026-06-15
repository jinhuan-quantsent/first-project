/**
 * FundSearchV5 - V5.0 基金查询页（默认首页）
 * 集成：SignalRibbon · MarketInfoBar · SearchBox · ResultList(卡片式)
 *          SectorCards · OpportunityRadar · FundDetailPanel(右侧面板)
 * 布局：左右分栏 — 左侧搜索结果 + 右侧详情面板(条件渲染)
 */
import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import { clsx } from 'clsx';

import SignalRibbon  from '../components/fundsearch/SignalRibbon';
import MarketInfoBar from '../components/fundsearch/MarketInfoBar';
import SearchBox     from '../components/fundsearch/SearchBox';
import FundResultList from '../components/fundsearch/FundResultList';
import SectorCards    from '../components/fundsearch/SectorCards';
import OpportunityRadarPanel from '../components/fundsearch/OpportunityRadarPanel';
import FundDetailPanel from '../components/fundsearch/FundDetailPanel';

import { searchFunds, fetchFundDetail } from '../api/fund';
import { fetchV5Sentiment } from '../api/marketV5';
import { addWatchlistV5 } from '../api/watchlistV5';
import { addPortfolioV5 } from '../api/portfolioV5';
import type {
  FundSearchItem,
  FundDetail,
  SignalLevel,
} from '../types';
import { SIGNAL_LABELS } from '../types';

/** 合法的 SignalLevel 值集合 */
const VALID_SIGNAL_LEVELS: Set<string> = new Set(['S+', 'S', 'A', 'B', 'C', 'D', 'E']);

/** 安全地将字符串转为 SignalLevel，非法值回退到 'B' */
const toSignalLevel = (v: string | undefined | null): SignalLevel =>
  (v && VALID_SIGNAL_LEVELS.has(v)) ? (v as SignalLevel) : 'B';

/** V5 情绪缓存结构 */
interface FundSentiment {
  score: number;
  signalLevel: SignalLevel;
  confidenceStars: number;
  shortTerm: SignalLevel;
  midTerm: SignalLevel;
  longTerm: SignalLevel;
  hasDivergence: boolean;
  divergenceType: 'bullish' | 'bearish' | undefined;
  advice: { action: string; level: string; reason: string; targetPositionPct: number };
  /** 从因子明细推导的推荐理由，如"波动率82分+北向资金78分触发极度恐慌" */
  reason?: string;
}

/**
 * 从 V5 因子明细构建推荐理由文案
 * 取 sigmoid_score 最高的 2 个因子，拼接为 "因子A XX分+因子B XX分触发<信号描述>"
 */
function buildReasonFromFactors(
  factorDetails: { factor_name: string; sigmoid_score: number }[] | undefined,
  signalLevel: SignalLevel,
): string {
  if (!factorDetails || factorDetails.length === 0) return '';
  const sorted = [...factorDetails].sort((a, b) => b.sigmoid_score - a.sigmoid_score);
  const top2 = sorted.slice(0, 2);
  const parts = top2.map((f) => {
    const display = f.sigmoid_score <= 1
      ? Math.round(f.sigmoid_score * 100)
      : Math.round(f.sigmoid_score);
    return `${f.factor_name}${display}分`;
  });
  return `${parts.join('+')}触发${SIGNAL_LABELS[signalLevel]}`;
}

/* ============================================================
   主组件
   ============================================================ */
export default function FundSearchV5() {
  const navigate = useNavigate();

  // —— 搜索参数 ——
  const [keyword,  setKeyword]  = useState('');
  const [fundType, setFundType] = useState('');
  const [page,     setPage]     = useState(1);
  const [loading,  setLoading]  = useState(false);
  const [results,  setResults]  = useState<FundSearchItem[]>([]);
  const [total,    setTotal]    = useState(0);
  const [searchError, setSearchError] = useState<string | null>(null);

  // —— 选中与详情 ——
  const [selectedFund, setSelectedFund]   = useState<FundSearchItem | null>(null);
  const [detailData,   setDetailData]   = useState<FundDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // —— 缓存每只基金的 V5 情绪 ——
  const [sentimentCache, setSentimentCache] = useState<Record<string, FundSentiment>>({});

  // —— 右侧面板打开/关闭 ———
  const [panelOpen, setPanelOpen] = useState(false);

  /** 构造传给子组件的 sentimentMap */
  const sentimentMap = useMemo(() => {
    const m: Record<string, FundSentiment> = {};
    results.forEach((f) => { if (sentimentCache[f.fund_code]) m[f.fund_code] = sentimentCache[f.fund_code]; });
    return m;
  }, [results, sentimentCache]);

  /** 搜索 */
  const handleSearch = useCallback(async (p: number = 1) => {
    if (!keyword.trim()) return;
    setLoading(true);
    setSearchError(null);
    setPage(p);
    setSelectedFund(null);
    setDetailData(null);
    setPanelOpen(false);
    try {
      const data = await searchFunds({ keyword, fund_type: fundType || undefined, page: p });
      setResults(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setResults([]);
      setTotal(0);
      setSearchError(err?.message || '搜索失败，请检查网络或稍后重试');
    } finally {
      setLoading(false);
    }
  }, [keyword, fundType]);

  /** 选中/取消选中 */
  const handleSelect = useCallback(async (fund: FundSearchItem) => {
    if (selectedFund?.fund_code === fund.fund_code) {
      setSelectedFund(null);
      setDetailData(null);
      setPanelOpen(false);
      return;
    }
    setSelectedFund(fund);
    setDetailLoading(true);
    setDetailError(null);
    setPanelOpen(true);

    // 并行获取详情 + V5 情绪
    try {
      const [detail] = await Promise.all([
        fetchFundDetail(fund.fund_code).catch(() => null),
        fetchV5Sentiment(fund.fund_code).then((s) => {
          const resolvedLevel = toSignalLevel(s.signal_level);
          const reason = buildReasonFromFactors(s.factor_details, resolvedLevel);
          setSentimentCache((prev) => ({
            ...prev,
            [fund.fund_code]: {
              score:           s.composite_score ?? 0,
              signalLevel:     resolvedLevel,
              confidenceStars:  s.confidence_stars ?? 0,
              shortTerm:      toSignalLevel(s.signal_level),
              midTerm:        toSignalLevel(s.signal_level),
              longTerm:        toSignalLevel(s.signal_level),
              hasDivergence:  false,
              divergenceType:  undefined,
              advice:          { action: '', level: '', reason: '', targetPositionPct: 0.5 },
              reason,
            },
          }));
        }).catch(() => {
          // 情绪数据获取失败时不影响详情显示
        }),
      ]);

      if (detail) {
        setDetailData(detail);
      } else {
        setDetailError('获取基金详情失败');
      }
    } catch {
      setDetailError('加载详情数据失败');
    } finally {
      setDetailLoading(false);
    }
  }, [selectedFund]);

  /** 关闭面板 */
  const handleClosePanel = useCallback(() => {
    setPanelOpen(false);
    setSelectedFund(null);
  }, []);

  /** 添加到自选 */
  const handleAddWatchlist = useCallback(async (fund: FundSearchItem) => {
    try {
      await addWatchlistV5({ fund_code: fund.fund_code });
      alert(`已将 ${fund.fund_short_name || fund.fund_name} 添加到自选`);
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '添加自选失败';
      alert(msg);
    }
  }, []);

  /** 添加到持仓 */
  const handleAddPortfolio = useCallback(async (fund: FundSearchItem) => {
    try {
      await addPortfolioV5({
        fund_code: fund.fund_code,
        fund_name: fund.fund_short_name || fund.fund_name,
        fund_type: fund.fund_type,
        current_nav: fund.nav,
      });
      alert(`已将 ${fund.fund_short_name || fund.fund_name} 添加到持仓`);
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '添加持仓失败';
      alert(msg);
    }
  }, []);

  const activeSignal = selectedFund ? (sentimentCache[selectedFund.fund_code]?.signalLevel ?? null) : null;

  return (
    <div className="relative max-w-5xl mx-auto space-y-4 pb-8">
      {/* ======== 1. 7级信号色带（页面最顶部）======= */}
      <SignalRibbon activeLevel={activeSignal} height={8} />

      {/* ======== 2. 页面标题 ======= */}
      <div className="px-1">
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">基金查询 V5.0</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-0.5">
          搜索基金，查看 V5.0 情绪分析（11因子 · 7级信号 · 4星置信度）
        </p>
      </div>

      {/* ======== 3. 大盘信息栏 ======= */}
      <MarketInfoBar indexes={[]} loading={false} />

      {/* ======== 4. 搜索框 ======= */}
      <SearchBox
        keyword={keyword}
        fundType={fundType}
        loading={loading}
        onKeywordChange={setKeyword}
        onTypeChange={setFundType}
        onSearch={() => handleSearch(1)}
      />

      {/* ======== 搜索错误提示 ======= */}
      {searchError && (
        <div className="card p-4 flex items-center justify-between">
          <p className="text-red-500 text-sm">{searchError}</p>
          <button
            onClick={() => setSearchError(null)}
            className="text-gray-400 hover:text-gray-600"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ======== 5. 搜索结果列表 ======= */}
      {keyword && (
        <FundResultList
          results={results}
          total={total}
          selectedCode={selectedFund?.fund_code || null}
          loading={loading}
          sentimentMap={sentimentMap}
          onSelect={handleSelect}
          onAddWatchlist={handleAddWatchlist}
          onAddPortfolio={handleAddPortfolio}
        />
      )}

      {/* ======== 6. 未搜索时的推荐内容 ======= */}
      {!keyword && (
        <div className="space-y-4">
          <SectorCards />
          <OpportunityRadarPanel />
        </div>
      )}

      {/* ======== 7. 右侧详情面板（遮罩 + 滑入）======= */}
      {panelOpen && selectedFund && (
        <>
          {/* 半透明遮罩 */}
          <div
            className="fixed inset-0 bg-black/20 z-40 transition-opacity duration-300"
            onClick={handleClosePanel}
          />

          {/* 面板：420px 宽，移动端全屏 */}
          <div
            className="fixed top-0 right-0 h-full w-full md:w-[420px] z-50 bg-white shadow-2xl
                       overflow-hidden animate-slideInRight"
            style={{ animation: 'slideInRight 300ms ease-out' }}
          >
            <FundDetailPanel
              fund={selectedFund}
              detail={detailData}
              sentiment={sentimentCache[selectedFund.fund_code] ?? null}
              loading={detailLoading}
              onClose={handleClosePanel}
            />
            {detailError && (
              <div className="px-6 py-2 text-center">
                <p className="text-red-500 text-xs">{detailError}</p>
              </div>
            )}
          </div>
        </>
      )}

      {/* 内联动画 */}
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to   { transform: translateX(0); }
        }
        .animate-slideInRight { animation: slideInRight 300ms ease-out; }
      `}</style>
    </div>
  );
}
