/**
 * backtest Store - 回溯页统一状态管理
 * 合并了原 Backtest.tsx 中的所有 useState 和 action handlers
 */
import { create } from 'zustand';
import { runBacktestV5, saveBacktestStrategyV5, deleteBacktestStrategyV5, activateBacktestStrategyV5 } from '../api/backtest';
import type { ModelParams, BacktestResultV5 } from '../api/backtest';
import { modelParamsToApiRequest, apiStrategyToLocal, DEFAULT_MODEL_PARAMS } from '../utils/paramsMapper';
import client from '../api/client';

/* ============================================================
   类型
   ============================================================ */
export interface BacktestStrategy {
  id: number;
  name: string;
  is_active: boolean;
  params: ModelParams;
}

interface FundSuggestion {
  code: string;
  name: string;
  type?: string;
  nav?: number;
}

interface BacktestParams {
  startDate: string;
  endDate: string;
  initialCapital: number;
  strategyId: number | null;
}

interface BacktestState {
  // 策略管理
  strategies: BacktestStrategy[];
  activeId: number | null;
  systemActiveSchemeName: string | null;

  // 参数面板
  panels: Record<string, boolean>;

  // 回测执行
  running: boolean;
  result: BacktestResultV5 | null;
  error: string | null;

  // 基金选择
  selectedFund: FundSuggestion | null;
  backtestParams: BacktestParams;

  loadError: string | null;

  // Actions — 策略管理
  setActiveId: (id: number | null) => void;
  updateParams: (newParams: ModelParams) => void;
  addStrategy: () => void;
  removeStrategy: (id: number) => void;
  renameStrategy: (newName: string) => void;
  loadSavedStrategies: () => Promise<void>;
  handleSave: () => Promise<void>;
  handleDelete: (id: number) => Promise<void>;
  handleApply: () => Promise<void>;

  // Actions — 回测执行
  handleRunBacktest: () => Promise<void>;

  // Actions — 面板
  togglePanel: (key: string) => void;

  // Actions — 基金选择
  setSelectedFund: (fund: FundSuggestion | null) => void;
  setBacktestParams: (params: BacktestParams) => void;
}

/* ============================================================
   初始值
   ============================================================ */
const defaultDateRange = () => {
  const d = new Date();
  d.setDate(d.getDate() - 90);
  return d.toISOString().slice(0, 10);
};

const INITIAL_STRATEGIES: BacktestStrategy[] = [
  { id: 1, name: '稳健方案', is_active: true, params: { ...DEFAULT_MODEL_PARAMS } },
  {
    id: 2, name: '激进方案', is_active: false,
    params: {
      ...DEFAULT_MODEL_PARAMS,
      action_mapping: { ...DEFAULT_MODEL_PARAMS.action_mapping, 'B': { type: 'buy', mult: 0.5, label: '小幅加仓' } },
      overheat_days: 15, pullback_add: -0.20,
    },
  },
];

/* ============================================================
   Store
   ============================================================ */
export const useBacktestStore = create<BacktestState>((set, get) => ({
  strategies: [...INITIAL_STRATEGIES],
  activeId: 1,
  systemActiveSchemeName: null,
  panels: { signal: true, factors: false, action: false, engine: false, risk: false },
  running: false,
  result: null,
  error: null,
  loadError: null,
  selectedFund: null,
  backtestParams: {
    startDate: defaultDateRange(),
    endDate: new Date().toISOString().slice(0, 10),
    initialCapital: 100000,
    strategyId: null,
  },

  // ---- 策略管理 ----
  setActiveId: (id) => set({ activeId: id }),

  updateParams: (newParams) => {
    const { activeId } = get();
    if (!activeId) return;
    set((prev) => ({
      strategies: prev.strategies.map((s: BacktestStrategy) => s.id !== activeId ? s : { ...s, params: newParams }),
    }));
  },

  addStrategy: () => {
    const { strategies } = get();
    const newId = Math.max(0, ...strategies.map((s: BacktestStrategy) => s.id)) + 1;
    set((prev) => ({
      strategies: [...prev.strategies, { id: newId, name: `新方案${newId}`, is_active: false, params: { ...DEFAULT_MODEL_PARAMS } }],
      activeId: newId,
    }));
  },

  removeStrategy: (id) => {
    const { activeId, strategies } = get();
    const remaining = strategies.filter((s: BacktestStrategy) => s.id !== id);
    set({
      strategies: remaining,
      activeId: activeId === id ? (remaining.length > 0 ? remaining[0].id : null) : activeId,
    });
  },

  renameStrategy: (newName) => {
    const { activeId } = get();
    if (!activeId) return;
    set((prev) => ({
      strategies: prev.strategies.map((s: BacktestStrategy) => s.id === activeId ? { ...s, name: newName } : s),
    }));
  },

  loadSavedStrategies: async () => {
    try {
      const res = await client.get('/api/v5/backtest/strategy');
      const saved = res.data.data?.strategies || [];
      if (saved.length > 0) {
        const mapped = saved.map(apiStrategyToLocal);
        set((prev) => {
          const prevIds = new Set(prev.strategies.map((s: BacktestStrategy) => s.id));
          const newOnes = mapped.filter((s: BacktestStrategy) => !prevIds.has(s.id));
          const updated = prev.strategies.map((p: BacktestStrategy) => {
            const found = mapped.find((s: BacktestStrategy) => s.id === p.id);
            return found ? { ...p, params: found.params, is_active: found.is_active } : p;
          });
          return { strategies: [...updated, ...newOnes] };
        });
        const active = mapped.find((s: BacktestStrategy) => s.is_active);
        if (active) {
          set({ activeId: active.id, systemActiveSchemeName: active.name });
        }
      }
    } catch (err) {
      console.error('[Backtest] 加载方案失败:', err);
      set({ loadError: String(err) } as any);
    }
  },

  handleSave: async () => {
    const { activeId, strategies } = get();
    const activeStrategy = strategies.find((s: BacktestStrategy) => s.id === activeId);
    if (!activeStrategy) return;

    const duplicate = strategies.find((s: BacktestStrategy) => s.name === activeStrategy.name && s.id !== activeId);
    if (duplicate) {
      const confirmed = window.confirm(`方案「${activeStrategy.name}」已存在，确定要覆盖吗？`);
      if (!confirmed) return;
    }

    try {
      const saved = await saveBacktestStrategyV5({ name: activeStrategy.name, params_json: activeStrategy.params as any });
      // 用后端返回的真实 id 替换本地假 id
      if (saved?.id) {
        set(state => ({
          strategies: state.strategies.map((s: BacktestStrategy) =>
            s.id === activeStrategy.id ? { ...s, id: saved.id } : s
          ),
        }));
      }
      await get().loadSavedStrategies();  // 重新从后端拉取确保一致
      alert(`方案「${activeStrategy.name}」保存成功！`);
    } catch (err: any) {
      alert(err?.message || '保存方案失败');
    }
  },

  handleDelete: async (id: number) => {
    try {
      await deleteBacktestStrategyV5(id);
      get().removeStrategy(id);
    } catch (err: any) {
      alert(err?.message || '删除方案失败');
    }
  },

  handleApply: async () => {
    const { activeId, strategies } = get();
    if (!activeId) return;
    const activeStrategy = strategies.find((s: BacktestStrategy) => s.id === activeId);
    try {
      await activateBacktestStrategyV5(activeId);
      set((prev) => ({
        strategies: prev.strategies.map((s: BacktestStrategy) => ({ ...s, is_active: s.id === activeId })),
        systemActiveSchemeName: activeStrategy?.name || null,
      }));
    } catch (err: any) {
      alert(err?.response?.data?.message || err?.message || '应用方案失败');
    }
  },

  // ---- 回测执行 ----
  handleRunBacktest: async () => {
    const { activeId, strategies, selectedFund, backtestParams } = get();
    const strategyId = backtestParams.strategyId || activeId;
    const strategy = strategies.find((s: BacktestStrategy) => s.id === strategyId) ?? strategies.find((s: BacktestStrategy) => s.id === activeId);
    if (!strategy) return;

    set({ running: true, error: null });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    try {
      const data = await runBacktestV5(
        modelParamsToApiRequest({ strategy, selectedFund, backtestParams })
      );
      set({ result: data });
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '回测运行失败，请重试';
      set({ error: msg });
    } finally {
      clearTimeout(timeoutId);
      set({ running: false });
    }
  },

  // ---- 面板 ----
  togglePanel: (key) => set((prev) => ({
    panels: { ...prev.panels, [key]: !prev.panels[key] },
  })),

  // ---- 基金选择 ----
  setSelectedFund: (fund) => set({ selectedFund: fund }),
  setBacktestParams: (params) => set({ backtestParams: params }),
}));
