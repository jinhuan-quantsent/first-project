/**
 * watchlistV5 Store - 自选页 Zustand store
 */
import { create } from 'zustand';
import type { WatchlistItem } from '../types';
import { fetchWatchlistV5 } from '../api/watchlistV5';

interface WatchlistV5State {
  items: WatchlistItem[];
  loading: boolean;
  expandedId: number | null;
  /** 自选变更的时间戳，其他页面可订阅此值来触发刷新 */
  lastUpdated: number;

  toggleExpand: (id: number) => void;
  loadWatchlist: () => Promise<void>;
  /** 加自选成功后调用：刷新列表并更新时间戳 */
  refreshAfterAdd: () => Promise<void>;
  removeItem: (id: number) => Promise<void>;
  reset: () => void;
}

const INITIAL: Pick<WatchlistV5State, 'items' | 'loading' | 'expandedId' | 'lastUpdated'> = {
  items: [],
  loading: false,
  expandedId: null,
  lastUpdated: 0,
};

export const useWatchlistV5Store = create<WatchlistV5State>((set, get) => ({
  ...INITIAL,

  toggleExpand: (id) => set((prev) => ({
    expandedId: prev.expandedId === id ? null : id,
  })),

  loadWatchlist: async () => {
    set({ loading: true });
    try {
      const data = await fetchWatchlistV5();
      set({ items: data, loading: false, lastUpdated: Date.now() });
    } catch {
      set({ loading: false });
    }
  },

  /** 加自选成功后，预刷新 store 数据（不阻塞调用方） */
  refreshAfterAdd: async () => {
    try {
      const data = await fetchWatchlistV5();
      set({ items: data, lastUpdated: Date.now() });
    } catch {
      // 静默失败，不阻塞加自选的 toast
    }
  },

  removeItem: async (id) => {
    set((prev) => ({
      items: prev.items.filter((it) => it.id !== id),
      expandedId: prev.expandedId === id ? null : prev.expandedId,
    }));
  },

  reset: () => set({ ...INITIAL }),
}));
