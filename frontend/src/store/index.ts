import { create } from 'zustand';
import type {
  SentimentLabel,
  IndexSnapshot,
  MarketSnapshot,
  MultiIndexData,
  CompositeSentiment,
} from '../types';
import { fetchMarketSnapshot, fetchMultiIndex } from '../api/market';

interface AppState {
  // --- 市场快照 ---
  snapshot: MarketSnapshot | null;
  snapshotLoading: boolean;
  snapshotError: string | null;

  // --- 选中指数 ---
  selectedIndex: string; // 默认沪深300
  multiIndexData: MultiIndexData[];
  composite: CompositeSentiment | null;
  marketLoading: boolean;
  marketError: string | null;

  // --- 免责声明 ---
  disclaimerAccepted: boolean;

  // --- Actions ---
  loadSnapshot: () => Promise<void>;
  loadMultiIndex: (codes?: string) => Promise<void>;
  setSelectedIndex: (code: string) => void;
  acceptDisclaimer: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // 初始状态
  snapshot: null,
  snapshotLoading: false,
  snapshotError: null,

  selectedIndex: 'SH000300',
  multiIndexData: [],
  composite: null,
  marketLoading: false,
  marketError: null,

  disclaimerAccepted: false,

  // 加载快照
  loadSnapshot: async () => {
    set({ snapshotLoading: true, snapshotError: null });
    try {
      const data = await fetchMarketSnapshot();
      set({ snapshot: data, snapshotLoading: false });
    } catch (err) {
      set({ snapshotError: '加载市场快照失败', snapshotLoading: false });
    }
  },

  // 加载多指数数据
  loadMultiIndex: async (codes?: string) => {
    set({ marketLoading: true, marketError: null });
    try {
      const data = await fetchMultiIndex(codes);
      set({
        multiIndexData: data.indexes,
        composite: data.composite,
        marketLoading: false,
      });
    } catch (err) {
      set({ marketError: '加载市场数据失败', marketLoading: false });
    }
  },

  // 切换选中指数
  setSelectedIndex: (code: string) => {
    set({ selectedIndex: code });
  },

  // 接受免责声明
  acceptDisclaimer: () => {
    set({ disclaimerAccepted: true });
    localStorage.setItem('disclaimer_accepted', 'true');
  },
}));
