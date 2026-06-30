/**
 * watchlistV5 Store - 自选页 Zustand store (4-Tab 架构)
 *
 * 状态管理：
 *   - items:          自选基金列表（含 sector_code/category）
 *   - sectorRatings:  全板块建仓评级
 *   - tabGroups:      按裁决规则分组 (buildable/risk/all)
 *   - activeTab:      当前选中Tab
 *   - selectedFundCode: 选中查看详情的基金代码
 *   - expandedSectorCode: 当前展开的板块代码
 */
import { create } from 'zustand';
import { fetchWatchlistV5, removeWatchlistV5 } from '../api/watchlistV5';
import { fetchSectorRatingsFull } from '../api/sectorDetailV5';
import type { WatchlistItem } from '../types';
import type { PositionRatingItem, PositionRating } from '../types/positionRating';

// ---- Tab类型 ----
export type WatchlistTab = 'buildable' | 'risk' | 'all';

// ---- 板块卡片数据 ----
export interface SectorCardData {
  sector_code: string;
  sector_name: string;
  rating: PositionRating;
  rating_label: string;
  rating_color: string;
  reason: string;
  signal_level: string;
  track: string;
  confidence_stars: number;
  composite_score: number;
  position_suggestion: number;
  funds: WatchlistItem[];  // 该板块下属于用户自选的基金
  total_fund_count: number;
}

// ---- Tab分组 ----
export interface TabGroups {
  buildable: SectorCardData[];
  risk: SectorCardData[];
  all: SectorCardData[];
}

/** 裁决规则：rating → Tab */
function classifyByRating(rating: PositionRating): WatchlistTab {
  if (rating === 'strong' || rating === 'cautious') return 'buildable';
  if (rating === 'forbidden') return 'risk';
  return 'all';
}

/** 构建分组 */
function buildTabGroups(
  items: WatchlistItem[],
  ratings: Record<string, PositionRatingItem>,
): TabGroups {
  const fundsBySector: Record<string, WatchlistItem[]> = {};
  const unmapped: WatchlistItem[] = [];

  for (const item of items) {
    const sc = (item as any).sector_code as string | undefined;
    if (sc) {
      if (!fundsBySector[sc]) fundsBySector[sc] = [];
      fundsBySector[sc].push(item);
    } else {
      unmapped.push(item);
    }
  }

  const allCards: SectorCardData[] = [];
  for (const code of Object.keys(fundsBySector)) {
    const ratingItem = ratings[code];
    if (!ratingItem) continue;

    allCards.push({
      sector_code: code,
      sector_name: ratingItem.sector_name,
      rating: ratingItem.rating,
      rating_label: ratingItem.rating_label,
      rating_color: ratingItem.rating_color,
      reason: ratingItem.reason,
      signal_level: ratingItem.signal_level,
      track: ratingItem.track,
      confidence_stars: ratingItem.confidence_stars,
      composite_score: ratingItem.composite_score,
      position_suggestion: ratingItem.position_suggestion,
      funds: fundsBySector[code],
      total_fund_count: ratingItem.funds.filter(f => f.status === 'active').length,
    });
  }

  const groups: TabGroups = { buildable: [], risk: [], all: [] };
  for (const card of allCards) {
    const tab = classifyByRating(card.rating);
    groups[tab].push(card);
    groups.all.push(card);
  }

  groups.buildable.sort((a, b) => a.composite_score - b.composite_score);
  groups.risk.sort((a, b) => b.composite_score - a.composite_score);
  groups.all.sort((a, b) => a.composite_score - b.composite_score);

  return groups;
}

// ---- Store接口 ----
interface WatchlistV5State {
  items: WatchlistItem[];
  sectorRatings: Record<string, PositionRatingItem>;
  tabGroups: TabGroups;
  unmappedFunds: WatchlistItem[];
  activeTab: WatchlistTab;
  selectedFundCode: string | null;
  expandedSectorCode: string | null;
  loading: boolean;
  error: string | null;

  loadAll: () => Promise<void>;
  setActiveTab: (tab: WatchlistTab) => void;
  selectFund: (code: string) => void;
  toggleSectorExpand: (code: string) => void;
  removeFund: (id: number, code: string) => Promise<void>;
  reset: () => void;
}

const INITIAL = {
  items: [] as WatchlistItem[],
  sectorRatings: {} as Record<string, PositionRatingItem>,
  tabGroups: { buildable: [], risk: [], all: [] } as TabGroups,
  unmappedFunds: [] as WatchlistItem[],
  activeTab: 'all' as WatchlistTab,
  selectedFundCode: null as string | null,
  expandedSectorCode: null as string | null,
  loading: false,
  error: null as string | null,
};

export const useWatchlistV5Store = create<WatchlistV5State>((set, get) => ({
  ...INITIAL,

  loadAll: async () => {
    set({ loading: true, error: null });
    try {
      const [watchlistData, ratingsData] = await Promise.all([
        fetchWatchlistV5(),
        fetchSectorRatingsFull(),
      ]);

      const items = Array.isArray(watchlistData) ? watchlistData : [];
      const sectorRatings = ratingsData;
      const tabGroups = buildTabGroups(items, sectorRatings);
      const unmappedFunds = items.filter(it => !(it as any).sector_code);

      const firstCard = tabGroups.all[0];
      const defaultFund = firstCard?.funds[0]?.fund_code || null;

      set({
        items,
        sectorRatings,
        tabGroups,
        unmappedFunds,
        selectedFundCode: defaultFund,
        loading: false,
      });
    } catch (err: any) {
      set({ error: err?.message || '加载失败', loading: false });
    }
  },

  setActiveTab: (tab) => set({ activeTab: tab }),
  selectFund: (code) => set({ selectedFundCode: code }),
  toggleSectorExpand: (code) => set((prev) => ({
    expandedSectorCode: prev.expandedSectorCode === code ? null : code,
  })),

  removeFund: async (id, code) => {
    const { items, sectorRatings, selectedFundCode } = get();
    const newItems = items.filter(it => it.id !== id);
    const tabGroups = buildTabGroups(newItems, sectorRatings);
    const unmappedFunds = newItems.filter(it => !(it as any).sector_code);
    const newSelected = selectedFundCode === code
      ? (tabGroups.all[0]?.funds[0]?.fund_code || null)
      : selectedFundCode;
    set({ items: newItems, tabGroups, unmappedFunds, selectedFundCode: newSelected });
    try { await removeWatchlistV5(id); } catch {}
  },

  reset: () => set({ ...INITIAL }),
}));
