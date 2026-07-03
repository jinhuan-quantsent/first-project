/**
 * portfolioV5 Store - 持仓页 Zustand store
 */
import { create } from 'zustand';
import type { PortfolioItem, PortfolioSummary } from '../types';
import { fetchPortfolioV5 } from '../api/portfolioV5';

interface PortfolioV5State {
  items: PortfolioItem[];
  summary: PortfolioSummary | null;
  loading: boolean;
  activeTab: 'positions' | 'advice' | 'trades';
  expandedId: number | null;

  setActiveTab: (tab: 'positions' | 'advice' | 'trades') => void;
  toggleExpand: (id: number) => void;
  loadPortfolio: () => Promise<void>;
  reset: () => void;
}

const INITIAL: Pick<PortfolioV5State, | 'items' | 'summary' | 'loading' | 'activeTab' | 'expandedId'> = {
  items: [],
  summary: null,
  loading: false,
  activeTab: 'positions',
  expandedId: null,
};

export const usePortfolioV5Store = create<PortfolioV5State>((set, get) => ({
  ...INITIAL,

  setActiveTab: (tab) => set({ activeTab: tab }),

  toggleExpand: (id) => set((prev) => ({
    expandedId: prev.expandedId === id ? null : id,
  })),

  loadPortfolio: async () => {
    set({ loading: true });
    try {
      const data = await fetchPortfolioV5();
      set({ items: data.items, summary: data.summary, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  reset: () => set({ ...INITIAL }),
}));
