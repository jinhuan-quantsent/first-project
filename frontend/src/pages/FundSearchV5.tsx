/**
 * FundSearchV5 - V5.0 基金查询页（默认首页）
 * 集成：SignalRibbon · MarketInfoBar · SearchBox · ResultList(卡片式)
 *          FundDetailPanel(右侧面板)
 *
 * V5.1 精简：移除 SectorCards/SectorWarnings/OpportunityRadarPanel 重复组件
 * 板块情绪和机会雷达已在 /sectors 页面提供完整版本
 */
import { useState, useCallback, useMemo, useEffect } from 'react';
import { Search, X, Calendar, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';

import SignalRibbon  from '../components/fundsearch/SignalRibbon';
import MarketInfoBar from '../components/fundsearch/MarketInfoBar';
import SearchBox     from '../components/fundsearch/SearchBox';
import FundResultList from '../components/fundsearch/FundResultList';
import FundDetailPanel from '../components/fundsearch/FundDetailPanel';
import SnapshotDownloadButton from '../components/fundsearch/SnapshotDownloadButton';

import { searchFunds, fetchFundDetail } from '../api/fund';
import { fetchV5Sentiment, fetchV5MultiIndex } from '../api/marketV5';
import type { V5MultiIndexItem, V5FactorDetail } from '../api/marketV5';
import { addWatchlistV5 } from '../api/watchlistV5';
import { useWatchlistV5Store } from '../stores/watchlistV5';
import { addPortfolioV5 } from '../api/portfolioV5';
import { toast } from '../components/common/Toast';
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
  reason?: string;
}

/**
 * 从 V5 因子明细构建推荐理由文案
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

  // —— 添加持仓对话框 ——
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addFundTarget, setAddFundTarget] = useState<FundSearchItem | null>(null);
  const [addAmount, setAddAmount] = useState('');
  const [addDate, setAddDate] = useState(new Date().toISOString().slice(0, 10));
  const [adding, setAdding] = useState(false);

  // —— 大盘数据（MarketInfoBar用） ——
  const [marketIndexes, setMarketIndexes] = useState<V5MultiIndexItem[]>([]);
  const [marketReason, setMarketReason] = useState<string | null>(null);
  const [marketScore, setMarketScore] = useState<number | null>(null);
  const [marketSignal, setMarketSignal] = useState<SignalLevel | null>(null);

  /** 加载大盘数据 */
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchV5MultiIndex();
        if (cancelled) return;
        setMarketIndexes(data.indexes);
        if (data.composite) {
          setMarketScore(data.composite.composite_score);
          setMarketSignal(toSignalLevel(data.composite.signal_level));
          try {
            const sh300 = data.indexes.find(i => i.index_code === 'SH000300');
            if (sh300) {
              const detail = await fetchV5Sentiment('SH000300');
              if (!cancelled && detail.factor_details) {
                setMarketReason(buildReasonFromFactors(detail.factor_details, toSignalLevel(detail.signal_level)));
              }
            }
          } catch { /* 推荐理由非关键 */ }
        }
      } catch { /* 静默降级 */ }
    })();
    return () => { cancelled = true; };
  }, []);

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
        }).catch(() => {}),
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
      const result = await addWatchlistV5({ fund_code: fund.fund_code });
      toast.success(`已将 ${fund.fund_short_name || fund.fund_name} 添加到自选`);
      // 乐观更新：立即往store追加（确保切到自选页能看到）
      useWatchlistV5Store.getState().addFundOptimistic({
        fund_code: fund.fund_code,
        fund_name: fund.fund_short_name || fund.fund_name,
        id: result?.id,
      });
      useWatchlistV5Store.getState().loadAll().catch(() => {});
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '添加自选失败';
      toast.error(msg);
    }
  }, []);

  /** 添加到持仓 — 打开对话框 */
  const handleAddPortfolio = useCallback((fund: FundSearchItem) => {
    setAddFundTarget(fund);
    setAddAmount('');
    setAddDate(new Date().toISOString().slice(0, 10));
    setShowAddDialog(true);
  }, []);

  /** 确认添加持仓 */
  const handleConfirmAddPortfolio = useCallback(async () => {
    if (!addFundTarget || adding) return;
    const num = parseFloat(addAmount);
    if (isNaN(num) || num <= 0) {
      toast.error('请输入有效的投资金额');
      return;
    }
    setAdding(true);
    try {
      await addPortfolioV5({
        fund_code: addFundTarget.fund_code,
        fund_name: addFundTarget.fund_short_name || addFundTarget.fund_name,
        fund_type: addFundTarget.fund_type,
        current_nav: addFundTarget.nav,
        market_value: num,
        buy_date: addDate,
      });
      toast.success(`已将 ${addFundTarget.fund_short_name || addFundTarget.fund_name} 添加到持仓（投资 ¥${num.toLocaleString()}，买入日期 ${addDate}）`);
      setShowAddDialog(false);
      setAddFundTarget(null);
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '添加持仓失败';
      toast.error(msg);
    } finally {
      setAdding(false);
    }
  }, [addFundTarget, addAmount, addDate, adding]);

  const activeSignal = selectedFund ? (sentimentCache[selectedFund.fund_code]?.signalLevel ?? null) : null;

  return (
    <div className="relative max-w-5xl mx-auto space-y-3 md:space-y-4 pb-20 md:pb-8">
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
      <MarketInfoBar
        indexes={marketIndexes.map(idx => ({
          index_code: idx.index_code,
          index_name: idx.index_name,
          close: 0,
          change_pct: 0,
          composite_score: idx.composite_score,
          sentiment_label: idx.signal_level as any,
        }))}
        globalScore={marketScore}
        globalLabel={marketSignal ? (marketSignal === 'S+' ? 'extreme_fear' : marketSignal === 'S' ? 'fear' : marketSignal === 'A' ? 'fear' : marketSignal === 'B' ? 'neutral' : marketSignal === 'C' ? 'greed' : marketSignal === 'D' ? 'greed' : 'extreme_greed') as any : null}
        reason={marketReason}
        loading={false}
      />

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

      {/* ======== 6. 未搜索时：引导到板块页 ======= */}
      {!keyword && (
        <div className="card p-6 text-center">
          <div className="w-14 h-14 rounded-full bg-brand-50 flex items-center justify-center mx-auto mb-3">
            <Search className="w-6 h-6 text-brand-400" />
          </div>
          <p className="text-sm text-gray-500 mb-1">输入基金名称或代码开始搜索</p>
          <p className="text-[10px] text-gray-400">
            板块情绪和机会雷达请访问 <a href="/sectors" className="text-brand-500 hover:text-brand-600">板块分析页</a>
          </p>
        </div>
      )}

      {/* ======== 7. 决策快照下载按钮 ======= */}
      <SnapshotDownloadButton />

      {/* ======== 8. 右侧详情面板（遮罩 + 滑入）======= */}
      {panelOpen && selectedFund && (
        <>
          <div
            className="fixed inset-0 bg-black/20 z-40 transition-opacity duration-300"
            onClick={handleClosePanel}
          />
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

      {/* ======== 添加持仓对话框 ======== */}
      {showAddDialog && addFundTarget && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"
          onClick={() => { if (!adding) setShowAddDialog(false); }}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-[360px] max-w-[90vw] p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-800">添加到持仓</h3>
              <button
                onClick={() => { if (!adding) setShowAddDialog(false); }}
                className="text-gray-300 hover:text-gray-500 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="bg-gray-50 rounded-lg p-3 space-y-1">
              <p className="text-sm font-medium text-gray-700">
                {addFundTarget.fund_short_name || addFundTarget.fund_name}
              </p>
              <p className="text-xs text-gray-400 font-mono">
                {addFundTarget.fund_code} · 当前净值 {addFundTarget.nav?.toFixed(4) || '未知'}
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-600">投资金额</label>
              <div className="flex items-center gap-1">
                <span className="text-sm text-gray-400">¥</span>
                <input
                  type="text"
                  value={addAmount}
                  onChange={(e) => setAddAmount(e.target.value.replace(/[^\d.]/g, ''))}
                  placeholder="输入投资金额"
                  autoFocus
                  className="flex-1 text-sm font-mono border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-400"
                />
              </div>
              <p className="text-[10px] text-gray-400">将自动从可用现金中扣除</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-600">买入日期</label>
              <input
                type="date"
                value={addDate}
                onChange={(e) => setAddDate(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-cyan-400"
              />
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setShowAddDialog(false)}
                disabled={adding}
                className="flex-1 py-2 rounded-lg text-sm font-medium text-gray-500 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={handleConfirmAddPortfolio}
                disabled={adding || !addAmount || parseFloat(addAmount) <= 0}
                className="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-cyan-500 hover:bg-cyan-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                {adding ? '添加中...' : '确认添加'}
              </button>
            </div>
          </div>
        </div>
      )}

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
