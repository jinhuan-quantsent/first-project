/**
 * WatchlistV5 - 自选页 (3-Tab 架构重设计版)
 *
 * 3 Tab：🟢可建仓 | 🔴风险组 | ⚪全部关注
 * 裁决规则：strong/cautious→可建仓, forbidden→风险组, watch→全部关注
 * 板块卡片 → 基金列表 → 选中基金详情
 */
import { useEffect } from 'react';
import { clsx } from 'clsx';
import { Star, ChevronRight, ChevronDown, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { useWatchlistV5Store, type WatchlistTab, type SectorCardData } from '../stores/watchlistV5';
import { POSITION_RATING_CONFIG, type PositionRating } from '../types/positionRating';
import { SIGNAL_LABELS, SIGNAL_COLORS_HEX, type SignalLevel } from '../types';
import SignalRibbon from '../components/fundsearch/SignalRibbon';
import { PositionRatingDot } from '../components/sector/PositionRatingBadge';

/* ---- Tab 配置 ---- */
const TAB_CONFIG: Record<WatchlistTab, { label: string; icon: string; color: string }> = {
  buildable: { label: '可建仓', icon: '🟢', color: '#16a34a' },
  risk:      { label: '风险组', icon: '🔴', color: '#dc2626' },
  all:       { label: '全部关注', icon: '⚪', color: '#6b7280' },
};

/* ---- 板块卡片 ---- */
function SectorCard({ card, expanded, onExpand, onSelectFund, selectedFundCode }: {
  card: SectorCardData;
  expanded: boolean;
  onExpand: () => void;
  onSelectFund: (code: string) => void;
  selectedFundCode: string | null;
}) {
  const rc = POSITION_RATING_CONFIG[card.rating];

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden transition-all duration-200">
      {/* 顶部：板块名 + 评级 + 信号 */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-gray-50"
        onClick={onExpand}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <PositionRatingDot rating={card.rating} />
          <span className="text-sm font-bold text-gray-800 truncate">{card.sector_name}</span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium whitespace-nowrap"
            style={{ backgroundColor: rc.color }}
          >
            {rc.shortLabel}
          </span>
          {card.signal_level && (
            <span
              className="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium whitespace-nowrap"
              style={{ backgroundColor: SIGNAL_COLORS_HEX[card.signal_level as SignalLevel] }}
            >
              {card.signal_level}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-lg font-bold tabular-nums" style={{ color: rc.color }}>
            {Math.round(card.composite_score)}
          </span>
          <span className="text-xs text-gray-400">分</span>
          <ChevronDown
            className={clsx('w-4 h-4 text-gray-400 transition-transform', expanded && 'rotate-180')}
          />
        </div>
      </div>

      {/* 展开区：基金列表 */}
      <div
        className={clsx(
          'transition-all duration-300 ease-in-out overflow-hidden',
          expanded ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0',
        )}
      >
        <div className="px-4 pb-3 space-y-2 border-t border-gray-100">
          <p className="text-xs text-gray-500 pt-2">{card.reason}</p>

          {/* 自选基金列表 */}
          <div className="space-y-1">
            <p className="text-[11px] text-gray-400 font-medium">自选基金</p>
            {card.funds.map(fund => (
              <div
                key={fund.fund_code}
                className={clsx(
                  'flex items-center justify-between px-3 py-1.5 rounded-lg cursor-pointer transition-colors',
                  selectedFundCode === fund.fund_code
                    ? 'bg-brand-50 border border-brand-200'
                    : 'hover:bg-gray-50',
                )}
                onClick={() => onSelectFund(fund.fund_code)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs font-medium text-gray-700 truncate">{fund.fund_name}</span>
                  <span className="text-[11px] text-gray-400 font-mono">{fund.fund_code}</span>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {fund.daily_return !== 0 && (
                    <span className={clsx(
                      'text-[11px] font-medium tabular-nums',
                      fund.daily_return >= 0 ? 'text-red-500' : 'text-green-500',
                    )}>
                      {fund.daily_return >= 0 ? '+' : ''}{Number(fund.daily_return).toFixed(2)}%
                    </span>
                  )}
                  <ChevronRight className="w-3.5 h-3.5 text-gray-300" />
                </div>
              </div>
            ))}
          </div>

          <a
            href={`/sectors/${card.sector_code}`}
            className="flex items-center justify-center gap-1 text-xs text-brand-500 hover:text-brand-600 pt-1"
          >
            查看板块详情 <ChevronRight className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  );
}

/* ---- 基金详情面板 ---- */
function FundDetailPanel({ fundCode, items, sectorRatings }: {
  fundCode: string | null;
  items: any[];
  sectorRatings: Record<string, any>;
}) {
  if (!fundCode) return null;

  const fund = items.find((it: any) => it.fund_code === fundCode);
  if (!fund) return null;

  const sectorCode = (fund as any).sector_code;
  const rating = sectorRatings[sectorCode];
  const rc = rating ? POSITION_RATING_CONFIG[rating.rating as PositionRating] : null;

  // 操作建议
  let actionLabel = '持有观望';
  let actionIcon = <Minus className="w-4 h-4 text-white" />;
  let actionBg = 'bg-blue-50 border border-blue-200';
  let actionIconBg = 'bg-blue-500';
  if (rating) {
    if (rating.rating === 'strong') {
      actionLabel = '积极建仓';
      actionIcon = <TrendingUp className="w-4 h-4 text-white" />;
      actionBg = 'bg-green-50 border border-green-200';
      actionIconBg = 'bg-green-500';
    } else if (rating.rating === 'cautious') {
      actionLabel = '谨慎建仓';
      actionIcon = <TrendingUp className="w-4 h-4 text-white" />;
      actionBg = 'bg-yellow-50 border border-yellow-200';
      actionIconBg = 'bg-yellow-500';
    } else if (rating.rating === 'forbidden') {
      actionLabel = '禁止建仓';
      actionIcon = <TrendingDown className="w-4 h-4 text-white" />;
      actionBg = 'bg-red-50 border border-red-200';
      actionIconBg = 'bg-red-500';
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-fadeIn">
      {/* 标题行 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="min-w-0 flex items-center gap-2">
          <h3 className="text-base font-bold text-gray-800 truncate">{fund.fund_name}</h3>
          <span className="text-xs text-gray-400 font-mono flex-shrink-0">{fund.fund_code}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {rating && (
            <>
              <span className="text-xs px-2 py-0.5 rounded-full text-white font-medium"
                style={{ backgroundColor: SIGNAL_COLORS_HEX[rating.signal_level as SignalLevel] }}>
                {rating.signal_level}·{SIGNAL_LABELS[rating.signal_level as SignalLevel]}
              </span>
              <span className="text-sm font-bold tabular-nums"
                style={{ color: rc?.color || '#6b7280' }}>
                {Math.round(rating.composite_score)}分
              </span>
            </>
          )}
        </div>
      </div>

      {/* 详情内容 */}
      <div className="p-4 space-y-4">
        {/* 建仓评级 */}
        {rating && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5">
              <PositionRatingDot rating={rating.rating} />
              <span className="text-sm font-bold" style={{ color: rc?.color }}>
                {rating.rating_label}
              </span>
              <span className="text-xs text-gray-400">
                置信度 {rating.confidence_stars}⭐
              </span>
            </div>
            <p className="text-xs text-gray-600">{rating.reason}</p>
            {rating.position_suggestion > 0 && (
              <p className="text-xs text-gray-400">
                建议仓位：{Math.round(rating.position_suggestion * 100)}%
              </p>
            )}
          </div>
        )}

        {/* 操作建议 */}
        <div className={clsx('rounded-lg p-3 flex items-start gap-2.5', actionBg)}>
          <div className={clsx('w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0', actionIconBg)}>
            {actionIcon}
          </div>
          <div>
            <p className="text-sm font-bold text-gray-800">{actionLabel}</p>
            <p className="text-xs text-gray-500 mt-0.5">{rating?.reason || '暂无板块信号数据'}</p>
          </div>
        </div>

        {/* 基金净值信息 */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <div>
            <span className="text-gray-400">估算净值</span>
            <p className="font-medium text-gray-700">{Number(fund.current_nav || 0).toFixed(4)}</p>
          </div>
          <div>
            <span className="text-gray-400">今日涨跌</span>
            <p className={clsx('font-medium', Number(fund.daily_return) >= 0 ? 'text-red-500' : 'text-green-500')}>
              {Number(fund.daily_return) >= 0 ? '+' : ''}{Number(fund.daily_return || 0).toFixed(2)}%
            </p>
          </div>
          <div>
            <span className="text-gray-400">近1周</span>
            <p className={clsx('font-medium', Number(fund.week_return) >= 0 ? 'text-red-500' : 'text-green-500')}>
              {Number(fund.week_return) >= 0 ? '+' : ''}{Number(fund.week_return || 0).toFixed(2)}%
            </p>
          </div>
          <div>
            <span className="text-gray-400">近1月</span>
            <p className={clsx('font-medium', Number(fund.month_return) >= 0 ? 'text-red-500' : 'text-green-500')}>
              {Number(fund.month_return) >= 0 ? '+' : ''}{Number(fund.month_return || 0).toFixed(2)}%
            </p>
          </div>
        </div>

        {/* 添加时间 */}
        <div className="border-t border-gray-100 pt-2 text-xs text-gray-400">
          添加自选：{fund.added_at || '未知'}
        </div>
      </div>
    </div>
  );
}

/* ---- 主页面 ---- */
export default function WatchlistV5() {
  const {
    items, tabGroups, unmappedFunds, sectorRatings,
    activeTab, selectedFundCode, expandedSectorCode,
    loading, error,
    loadAll, setActiveTab, selectFund, toggleSectorExpand,
  } = useWatchlistV5Store();

  useEffect(() => { loadAll(); }, [loadAll]);

  const currentCards = tabGroups[activeTab];
  const totalBuildable = tabGroups.buildable.length;
  const totalRisk = tabGroups.risk.length;
  const totalAll = tabGroups.all.length;

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
          <button onClick={() => loadAll()} className="mt-3 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg">重试</button>
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

  // 信号色带：用选中基金的板块信号
  const activeLevel = selectedFundCode && sectorRatings
    ? (() => {
        const fund = items.find(it => it.fund_code === selectedFundCode);
        const sc = (fund as any)?.sector_code;
        if (sc && sectorRatings[sc]) return sectorRatings[sc].signal_level as SignalLevel;
        return null;
      })()
    : null;

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <SignalRibbon activeLevel={activeLevel} height={8} />

      <div>
        <h1 className="text-xl font-bold text-gray-800">我的自选</h1>
        <p className="text-xs text-gray-400 mt-0.5">
          自选 {items.length} 只基金 · 覆盖 {tabGroups.all.length} 个板块
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2">
        {(Object.keys(TAB_CONFIG) as WatchlistTab[]).map(tab => {
          const cfg = TAB_CONFIG[tab];
          const count = tab === 'buildable' ? totalBuildable : tab === 'risk' ? totalRisk : totalAll;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={clsx(
                'flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all',
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

      {/* 板块卡片列表 */}
      <div className="space-y-3">
        {currentCards.length > 0 ? (
          currentCards.map(card => (
            <SectorCard
              key={card.sector_code}
              card={card}
              expanded={expandedSectorCode === card.sector_code}
              onExpand={() => toggleSectorExpand(card.sector_code)}
              onSelectFund={selectFund}
              selectedFundCode={selectedFundCode}
            />
          ))
        ) : (
          <div className="card p-6 text-center">
            <p className="text-gray-400 text-sm">当前 Tab 下暂无板块</p>
          </div>
        )}

        {/* 未映射基金 */}
        {unmappedFunds.length > 0 && activeTab === 'all' && (
          <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-2">
            <p className="text-xs text-gray-400 font-medium">未映射板块的基金</p>
            {unmappedFunds.map(fund => (
              <div
                key={fund.fund_code}
                className={clsx(
                  'flex items-center justify-between px-3 py-1.5 rounded-lg cursor-pointer',
                  selectedFundCode === fund.fund_code ? 'bg-brand-50' : 'hover:bg-gray-50',
                )}
                onClick={() => selectFund(fund.fund_code)}
              >
                <span className="text-xs text-gray-600">{fund.fund_name} ({fund.fund_code})</span>
                <span className="text-xs text-gray-400">无板块映射</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 选中基金详情 */}
      <FundDetailPanel
        fundCode={selectedFundCode}
        items={items as any}
        sectorRatings={sectorRatings as any}
      />
    </div>
  );
}
