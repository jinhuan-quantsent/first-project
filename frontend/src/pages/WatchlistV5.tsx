/**
 * WatchlistV5 - 自选页 (3-Tab 网格卡片架构)
 *
 * 3 Tab：🟢可建仓 | 🔴风险组 | ⚪观望关注（互斥分区，每个板块仅出现在一个Tab）
 * 裁决规则：strong/cautious→可建仓, forbidden→风险组, watch→观望关注
 * 方形卡片网格 → 点击展开基金列表 → 基金行：建仓按钮+删除按钮 → 点击基金展示详情面板
 */
import { useEffect, useState, useCallback } from 'react';
import { clsx } from 'clsx';
import { Trash2, ChevronDown, ExternalLink, Star, ChevronRight, X, PlusCircle, Calendar, Loader2 } from 'lucide-react';
import { useWatchlistV5Store, type WatchlistTab, type SectorCardData } from '../stores/watchlistV5';
import { POSITION_RATING_CONFIG, type PositionRating } from '../types/positionRating';
import { SIGNAL_LABELS, SIGNAL_COLORS_HEX, type SignalLevel } from '../types';
import type { WatchlistItem } from '../types';
import SignalRibbon from '../components/fundsearch/SignalRibbon';
import { PositionRatingDot } from '../components/sector/PositionRatingBadge';
import { addPortfolioV5 } from '../api/portfolioV5';
import { toast } from '../components/common/Toast';

/* ---- 情绪分色阶（低分=恐惧=绿 → 高分=贪婪=红） ---- */
function greedColor(v: number): string {
  if (v < 30) return '#22C55E';
  if (v < 50) return '#FBBF24';
  if (v < 70) return '#F59E0B';
  return '#EF4444';
}

/* ---- Tab 配置 ---- */
const TAB_CONFIG: Record<WatchlistTab, { label: string; icon: string; color: string }> = {
  buildable: { label: '可建仓', icon: '🟢', color: '#16a34a' },
  risk:      { label: '风险组', icon: '🔴', color: '#dc2626' },
  all:       { label: '全部关注', icon: '⚪', color: '#6b7280' },
};

/* ---- 操作建议文案 ---- */
function actionLabel(rating: PositionRating): { text: string; bg: string; textColor: string } {
  if (rating === 'strong')   return { text: '积极建仓', bg: '#dcfce7', textColor: '#15803d' };
  if (rating === 'cautious') return { text: '谨慎建仓', bg: '#fef9c3', textColor: '#a16207' };
  if (rating === 'forbidden') return { text: '禁止建仓', bg: '#fee2e2', textColor: '#b91c1c' };
  return { text: '持有观望', bg: '#f3f4f6', textColor: '#6b7280' };
}

/* ---- 基金详情面板（选中基金后在卡片下方展示） ---- */
function FundDetailPanel({
  fund,
  card,
}: {
  fund: WatchlistItem;
  card: SectorCardData;
}) {
  const rc = POSITION_RATING_CONFIG[card.rating];
  const action = actionLabel(card.rating);
  const stars = '⭐'.repeat(card.confidence_stars) + '☆'.repeat(Math.max(0, 5 - card.confidence_stars));

  return (
    <div className="mt-2 rounded-xl border border-gray-100 bg-gray-50 p-3 space-y-3 text-sm">
      {/* 基金标题行 */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-bold text-gray-800 leading-tight">{fund.fund_name}</p>
          <p className="text-[10px] text-gray-400 font-mono mt-0.5">{fund.fund_code}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {card.signal_level && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium"
              style={{ backgroundColor: SIGNAL_COLORS_HEX[card.signal_level as SignalLevel] || '#94a3b8' }}
            >
              {card.signal_level}
            </span>
          )}
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold"
            style={{ background: greedColor(card.composite_score) }}
          >
            {Math.round(card.composite_score)}
          </div>
        </div>
      </div>

      {/* 建仓评级 */}
      <div className={clsx('flex items-center gap-2 rounded-lg p-2', rc.bg, rc.border, 'border')}>
        <PositionRatingDot rating={card.rating} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className={clsx('text-xs font-bold', rc.text)}>{rc.label}</span>
            <span className="text-[10px] text-gray-400">{stars}</span>
          </div>
          <p className="text-[10px] text-gray-500 leading-relaxed mt-0.5 line-clamp-2">{card.reason}</p>
        </div>
        {card.position_suggestion > 0 && (
          <div className="flex-shrink-0 text-center">
            <p className="text-sm font-bold" style={{ color: rc.color }}>
              {Math.round(card.position_suggestion * 100)}%
            </p>
            <p className="text-[9px] text-gray-400">建议仓位</p>
          </div>
        )}
      </div>

      {/* 操作建议卡片 */}
      <div
        className="flex items-center justify-center py-2 rounded-lg text-xs font-bold"
        style={{ backgroundColor: action.bg, color: action.textColor }}
      >
        {action.text}
      </div>

      {/* 净值信息 2×2 */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: '当前净值', value: fund.current_nav ? fund.current_nav.toFixed(4) : '—' },
          {
            label: '今日涨跌',
            value: fund.daily_return
              ? `${fund.daily_return >= 0 ? '+' : ''}${Number(fund.daily_return).toFixed(2)}%`
              : '—',
            color: fund.daily_return > 0 ? '#ef4444' : fund.daily_return < 0 ? '#22c55e' : undefined,
          },
          {
            label: '近1周',
            value: fund.week_return
              ? `${fund.week_return >= 0 ? '+' : ''}${Number(fund.week_return).toFixed(2)}%`
              : '—',
            color: fund.week_return > 0 ? '#ef4444' : fund.week_return < 0 ? '#22c55e' : undefined,
          },
          {
            label: '近1月',
            value: fund.month_return
              ? `${fund.month_return >= 0 ? '+' : ''}${Number(fund.month_return).toFixed(2)}%`
              : '—',
            color: fund.month_return > 0 ? '#ef4444' : fund.month_return < 0 ? '#22c55e' : undefined,
          },
        ].map(item => (
          <div key={item.label} className="bg-white rounded-lg px-2.5 py-2 text-center border border-gray-100">
            <p className="text-[9px] text-gray-400">{item.label}</p>
            <p
              className="text-xs font-semibold mt-0.5"
              style={{ color: item.color || '#1f2937' }}
            >
              {item.value}
            </p>
          </div>
        ))}
      </div>

      {/* 添加时间 */}
      <p className="text-[10px] text-gray-300 text-right">
        添加于 {fund.added_at ? fund.added_at.slice(0, 10) : '—'}
      </p>
    </div>
  );
}

/* ---- 板块卡片 ---- */
function SectorCard({
  card,
  expanded,
  selectedFundCode,
  onExpand,
  onSelectFund,
  onDeleteFund,
  onAddPortfolio,
}: {
  card: SectorCardData;
  expanded: boolean;
  selectedFundCode: string | null;
  onExpand: () => void;
  onSelectFund: (code: string) => void;
  onDeleteFund: (id: number, code: string) => void;
  onAddPortfolio: (fund: WatchlistItem) => void;
}) {
  const rc = POSITION_RATING_CONFIG[card.rating];
  const scoreColor = greedColor(card.composite_score);
  const signalHex = SIGNAL_COLORS_HEX[card.signal_level as SignalLevel] || '#94A3B8';
  const signalLabel = SIGNAL_LABELS[card.signal_level as SignalLevel] || '';

  const tab = classifyTab(card.rating);
  const accentBar =
    tab === 'buildable' ? 'bg-green-400' : tab === 'risk' ? 'bg-red-400' : 'bg-gray-300';

  // 当前展开卡片内选中的基金对象
  const selectedFund = expanded
    ? card.funds.find(f => f.fund_code === selectedFundCode) || null
    : null;

  return (
    <div
      className={clsx(
        'rounded-xl border overflow-hidden transition-all cursor-pointer hover:shadow-md',
        expanded
          ? tab === 'buildable'
            ? 'border-green-200 shadow-md'
            : tab === 'risk'
            ? 'border-red-200 shadow-md'
            : 'border-gray-300 shadow-md'
          : 'border-gray-100',
      )}
      style={{ background: '#fff' }}
      onClick={onExpand}
    >
      {/* 顶部色带 */}
      <div className={clsx('h-1', accentBar)} />

      <div className="p-3">
        {/* 头部: 板块名 + 评级徽章 + 评分圆 */}
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <PositionRatingDot rating={card.rating} />
              <span className="text-sm font-bold text-gray-800 truncate">{card.sector_name}</span>
            </div>
            <div className="flex items-center gap-1.5 mt-1">
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium"
                style={{ backgroundColor: rc.color }}
              >
                {rc.shortLabel}
              </span>
              {card.signal_level && (
                <span
                  className="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium"
                  style={{ backgroundColor: signalHex }}
                >
                  {card.signal_level}
                </span>
              )}
              <span className="text-[10px] text-gray-400">{signalLabel}</span>
            </div>
          </div>
          {/* 评分圆 */}
          <div className="flex-shrink-0 flex flex-col items-center">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center text-white text-sm font-bold"
              style={{ background: scoreColor }}
            >
              {Math.round(card.composite_score)}
            </div>
            <span className="text-[10px] text-gray-400 mt-0.5">情绪分</span>
          </div>
        </div>

        {/* 置信度 + 建议仓位 */}
        <div className="flex items-center justify-between text-[10px] mb-2">
          <span className="text-gray-400">置信度 {card.confidence_stars}⭐</span>
          {card.position_suggestion > 0 && (
            <span className="text-gray-400">
              建议仓位 {Math.round(card.position_suggestion * 100)}%
            </span>
          )}
        </div>

        {/* 裁决原因 */}
        <p className="text-[11px] text-gray-500 leading-relaxed">{card.reason}</p>

        {/* ====== 展开区域 ====== */}
        <div
          style={{
            maxHeight: expanded ? '800px' : '0px',
            opacity: expanded ? 1 : 0,
            overflow: 'hidden',
            transition: 'max-height 300ms ease, opacity 200ms ease',
          }}
        >
          <div className="border-t border-gray-100 pt-2 mt-2 space-y-1.5">
            <p className="text-[10px] text-gray-400 font-medium">
              自选基金 ({card.funds.length})
            </p>

            {/* 基金列表 */}
            {card.funds.map(fund => {
              const isSelected = fund.fund_code === selectedFundCode;
              return (
                <div key={fund.fund_code}>
                  {/* 基金行 */}
                  <div
                    className={clsx(
                      'flex items-center justify-between rounded-lg px-2.5 py-2 group cursor-pointer transition-colors',
                      isSelected
                        ? tab === 'buildable'
                          ? 'bg-green-50 border border-green-200'
                          : tab === 'risk'
                          ? 'bg-red-50 border border-red-200'
                          : 'bg-blue-50 border border-blue-200'
                        : 'bg-gray-50 hover:bg-gray-100',
                    )}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectFund(fund.fund_code);
                    }}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <ChevronRight
                        className={clsx(
                          'w-3 h-3 flex-shrink-0 transition-transform',
                          isSelected ? 'rotate-90 text-gray-500' : 'text-gray-300',
                        )}
                      />
                      <div className="min-w-0">
                        <p className="text-xs font-medium text-gray-700 truncate">{fund.fund_name}</p>
                        <p className="text-[10px] text-gray-400 font-mono">{fund.fund_code}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {fund.daily_return !== 0 && (
                        <span
                          className={clsx(
                            'text-[11px] font-medium tabular-nums',
                            Number(fund.daily_return) >= 0 ? 'text-red-500' : 'text-green-500',
                          )}
                        >
                          {Number(fund.daily_return) >= 0 ? '+' : ''}
                          {Number(fund.daily_return).toFixed(2)}%
                        </span>
                      )}
                      {/* 建仓按钮 */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onAddPortfolio(fund);
                        }}
                        className={clsx(
                          'w-6 h-6 rounded-full flex items-center justify-center transition-colors',
                          'text-cyan-500 hover:bg-cyan-50 hover:text-cyan-600',
                          'opacity-0 group-hover:opacity-100',
                        )}
                        title="建仓（添加到持仓）"
                      >
                        <PlusCircle className="w-3.5 h-3.5" />
                      </button>
                      {/* 删除按钮 */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteFund(fund.id, fund.fund_code);
                        }}
                        className="w-6 h-6 rounded-full flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                        title="删除自选"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* 详情面板：选中基金时在行下方展开 */}
                  {isSelected && (
                    <FundDetailPanel fund={fund} card={card} />
                  )}
                </div>
              );
            })}

            {/* 查看板块详情 */}
            <a
              href={`/sectors/${card.sector_code}`}
              onClick={(e) => e.stopPropagation()}
              className="flex items-center justify-center gap-1 text-[10px] text-blue-500 hover:text-blue-600 pt-1"
            >
              查看板块详情 <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>

        {/* 展开提示箭头 */}
        <div className="flex items-center justify-center pt-1">
          <ChevronDown
            className={clsx(
              'w-3.5 h-3.5 text-gray-300 transition-transform',
              expanded && 'rotate-180',
            )}
          />
        </div>
      </div>
    </div>
  );
}

/** 裁决辅助 */
function classifyTab(rating: PositionRating): WatchlistTab {
  if (rating === 'strong' || rating === 'cautious') return 'buildable';
  if (rating === 'forbidden') return 'risk';
  return 'all';
}

/* ---- 主页面 ---- */
export default function WatchlistV5() {
  const {
    items, tabGroups, unmappedFunds,
    activeTab, expandedSectorCode, selectedFundCode,
    loading, error,
    loadAll, setActiveTab, toggleSectorExpand, selectFund, removeFund,
  } = useWatchlistV5Store();

  /* ---- 建仓弹窗状态 ---- */
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [addFundTarget, setAddFundTarget] = useState<WatchlistItem | null>(null);
  const [addAmount, setAddAmount] = useState('');
  const [addDate, setAddDate] = useState(new Date().toISOString().slice(0, 10));
  const [adding, setAdding] = useState(false);

  // mount时：仅在store为空时加载（防覆盖刚加自选后的最新状态）
  const storeItems = useWatchlistV5Store((s) => s.items);
  useEffect(() => {
    if (storeItems.length === 0) {
      loadAll();
    }
  }, [loadAll, storeItems.length]);

  /** 打开建仓弹窗 */
  const handleAddPortfolio = useCallback((fund: WatchlistItem) => {
    setAddFundTarget(fund);
    setAddAmount('');
    setAddDate(new Date().toISOString().slice(0, 10));
    setShowAddDialog(true);
  }, []);

  /** 确认建仓 */
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
        fund_name: addFundTarget.fund_name,
        current_nav: addFundTarget.current_nav || undefined,
        market_value: num,
        buy_date: addDate,
      });
      toast.success(`已将 ${addFundTarget.fund_name} 添加到持仓（投资 ¥${num.toLocaleString()}，买入日期 ${addDate}）`);
      setShowAddDialog(false);
      setAddFundTarget(null);
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '添加持仓失败';
      toast.error(msg);
    } finally {
      setAdding(false);
    }
  }, [addFundTarget, addAmount, addDate, adding]);

  const currentCards = tabGroups[activeTab];
  const firstCard = currentCards[0];
  const activeLevel = firstCard?.signal_level as SignalLevel || null;

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <h1 className="text-xl font-bold text-gray-800">我的自选</h1>
        <div className="card p-8 text-center">
          <div className="inline-block w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm mt-2">加载自选数据...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <h1 className="text-xl font-bold text-gray-800">我的自选</h1>
        <div className="card p-8 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button
            onClick={() => loadAll()}
            className="mt-3 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <h1 className="text-xl font-bold text-gray-800">我的自选</h1>
        <div className="card p-8 text-center">
          <Star className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-gray-500 text-sm font-medium">暂无自选基金</p>
          <p className="text-xs text-gray-300 mt-1">在基金查询页点击 ★ 添加自选基金</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <SignalRibbon activeLevel={activeLevel} height={8} />

      <div>
        <h1 className="text-xl font-bold text-gray-800">我的自选</h1>
        <p className="text-xs text-gray-400 mt-0.5">
          自选 {items.length} 只基金 · {tabGroups.buildable.length} 可建仓 · {tabGroups.all.length} 观望
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2">
        {(Object.keys(TAB_CONFIG) as WatchlistTab[]).map(tab => {
          const cfg = TAB_CONFIG[tab];
          const count = tabGroups[tab].length;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                'flex items-center gap-1 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg text-xs md:text-sm font-medium transition-all',
                activeTab === tab
                  ? 'bg-white shadow-sm border-2'
                  : 'bg-gray-50 border border-gray-100 text-gray-500 hover:bg-gray-100',
              )}
              style={activeTab === tab ? { borderColor: cfg.color, color: cfg.color } : undefined}
            >
              <span>{cfg.icon}</span>
              <span>{cfg.label}</span>
              <span className="text-xs opacity-70">{count}</span>
            </button>
          );
        })}
      </div>

      {/* 板块卡片网格 */}
      {currentCards.length > 0 ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-2 md:gap-3">
          {currentCards.map(card => (
            <SectorCard
              key={card.sector_code}
              card={card}
              expanded={expandedSectorCode === card.sector_code}
              selectedFundCode={selectedFundCode}
              onExpand={() => toggleSectorExpand(card.sector_code)}
              onSelectFund={selectFund}
              onDeleteFund={removeFund}
              onAddPortfolio={handleAddPortfolio}
            />
          ))}
        </div>
      ) : (
        <div className="card p-6 text-center">
          <p className="text-gray-400 text-sm">当前分类下暂无板块</p>
        </div>
      )}

      {/* 未映射基金（仅在全部关注Tab显示） */}
      {unmappedFunds.length > 0 && activeTab === 'all' && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
          <p className="text-xs text-gray-400 font-medium">未映射板块的基金</p>
          {unmappedFunds.map(fund => (
            <div
              key={fund.fund_code}
              className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 group"
            >
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-700 truncate">{fund.fund_name}</p>
                <p className="text-[10px] text-gray-400 font-mono">{fund.fund_code}</p>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {fund.daily_return !== 0 && (
                  <span
                    className={clsx(
                      'text-[11px] font-medium tabular-nums',
                      Number(fund.daily_return) >= 0 ? 'text-red-500' : 'text-green-500',
                    )}
                  >
                    {Number(fund.daily_return) >= 0 ? '+' : ''}
                    {Number(fund.daily_return).toFixed(2)}%
                  </span>
                )}
                {/* 建仓按钮 */}
                <button
                  onClick={() => handleAddPortfolio(fund)}
                  className="w-6 h-6 rounded-full flex items-center justify-center text-cyan-500 hover:bg-cyan-50 hover:text-cyan-600 transition-colors opacity-0 group-hover:opacity-100"
                  title="建仓（添加到持仓）"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                </button>
                {/* 删除按钮 */}
                <button
                  onClick={() => removeFund(fund.id, fund.fund_code)}
                  className="w-6 h-6 rounded-full flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors opacity-0 group-hover:opacity-100"
                  title="删除自选"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ======== 建仓弹窗 ======== */}
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
                {addFundTarget.fund_name}
              </p>
              <p className="text-xs text-gray-400 font-mono">
                {addFundTarget.fund_code} · 当前净值 {addFundTarget.current_nav?.toFixed(4) || '未知'}
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
                {adding ? '添加中...' : '确认建仓'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
