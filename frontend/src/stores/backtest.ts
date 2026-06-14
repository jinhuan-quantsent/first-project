/**
 * backtest Store - 回溯页 Zustand store
 */
import { create } from 'zustand';

interface BacktestStrategy {
  id: number;
  name: string;
  is_active: boolean;
  params: Record<string, unknown>;
}

interface BacktestState {
  strategies: BacktestStrategy[];
  activeId: number | null;
  panels: Record<string, boolean>;
  running: boolean;
  result: Record<string, unknown> | null;

  setActiveId: (id: number | null) => void;
  togglePanel: (key: string) => void;
  setRunning: (v: boolean) => void;
  setResult: (r: Record<string, unknown> | null) => void;
  addStrategy: () => void;
  removeStrategy: (id: number) => void;
  reset: () => void;
}

const INITIAL: Pick<BacktestState, 'strategies' | 'activeId' | 'panels' | 'running' | 'result'> = {
  strategies: [],
  activeId: null,
  panels: { signal: true, factors: false, sigmoid: false, position: false, risk: false },
  running: false,
  result: null,
};

export const useBacktestStore = create<BacktestState>((set, get) => ({
  ...INITIAL,

  setActiveId: (id) => set({ activeId: id }),
  togglePanel: (key) => set((prev) => ({
    panels: { ...prev.panels, [key]: !prev.panels[key] },
  })),
  setRunning: (v) => set({ running: v }),
  setResult: (r) => set({ result: r }),

  addStrategy: () => set((prev) => {
    const newId = Math.max(0, ...prev.strategies.map((s) => s.id)) + 1;
    return {
      strategies: [...prev.strategies, { id: newId, name: `新方案${newId}`, is_active: false, params: {} }],
      activeId: newId,
    };
  }),

  removeStrategy: (id) => set((prev) => ({
    strategies: prev.strategies.filter((s) => s.id !== id),
    activeId: prev.activeId === id ? null : prev.activeId,
  })),

  reset: () => set({ ...INITIAL }),
}));
