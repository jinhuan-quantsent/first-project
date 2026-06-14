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

  toggleExpand: (id: number) => void;
  loadWatchlist: () => Promise<void>;
  removeItem: (id: number) => Promise<void>;
  reset: () => void;
}

const INITIAL: Pick<WatchlistV5State, 'items' | 'loading' | 'expandedId'> = {
  items: [],
  loading: false,
  expandedId: null,
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
      set({ items: data, loading: false });
    } catch {
      set({ loading: false });
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
