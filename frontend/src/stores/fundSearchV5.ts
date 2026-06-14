/**
 * fundSearchV5 Store - 基金查询页 Zustand store
 * 管理搜索参数、结果、选中基金、详情、V5情绪数据
 */
import { create } from 'zustand';
import type {
  FundSearchItem,
  FundDetail,
  SignalLevel,
} from '../types';
import { searchFunds, fetchFundDetail } from '../api/fund';
import { fetchV5Sentiment } from '../api/marketV5';

/** 单只基金的 V5 情绪缓存结构 */
interface FundV5Sentiment {
  score: number;
  signalLevel: SignalLevel;
  confidenceStars: number;
  shortTerm: SignalLevel;
  midTerm: SignalLevel;
  longTerm: SignalLevel;
  hasDivergence: boolean;
  divergenceType: 'bullish' | 'bearish' | undefined;
  advice: {
    action: string;
    level: string;
    reason: string;
    targetPositionPct: number;
  };
}

interface FundSearchV5State {
  // 搜索参数
  keyword: string;
  fundType: string;
  page: number;

  // 搜索结果
  results: FundSearchItem[];
  total: number;
  loading: boolean;

  // 选中与详情
  selectedFund: FundSearchItem | null;
  detailData: FundDetail | null;
  detailLoading: boolean;
  detailError: string | null;

  // V5 情绪（按 fund_code 缓存）
  sentimentCache: Record<string, FundV5Sentiment>;

  // Actions
  setKeyword: (v: string) => void;
  setFundType: (v: string) => void;
  setPage: (p: number) => void;
  search: (p?: number) => Promise<void>;
  selectFund: (fund: FundSearchItem | null) => Promise<void>;
  clearSelection: () => void;
  reset: () => void;
}

const INITIAL: Pick<
  FundSearchV5State,
  | 'keyword'
  | 'fundType'
  | 'page'
  | 'results'
  | 'total'
  | 'loading'
  | 'selectedFund'
  | 'detailData'
  | 'detailLoading'
  | 'detailError'
  | 'sentimentCache'
> = {
  keyword: '',
  fundType: '',
  page: 1,
  results: [],
  total: 0,
  loading: false,
  selectedFund: null,
  detailData: null,
  detailLoading: false,
  detailError: null,
  sentimentCache: {},
};

export const useFundSearchV5Store = create<FundSearchV5State>((set, get) => ({
  ...INITIAL,

  setKeyword: (v) => set({ keyword: v }),
  setFundType: (v) => set({ fundType: v }),
  setPage: (p) => set({ page: p }),

  search: async (p = 1) => {
    const { keyword, fundType } = get();
    if (!keyword.trim()) return;
    set({ loading: true, page: p, selectedFund: null, detailData: null });
    try {
      const data = await searchFunds({
        keyword,
        fund_type: fundType || undefined,
        page: p,
      });
      set({ results: data.items, total: data.total, loading: false });
    } catch {
      set({ loading: false });
      // 搜索失败时不打断页面，由组件层决定如何提示
    }
  },

  selectFund: async (fund) => {
    if (!fund) {
      set({ selectedFund: null, detailData: null, detailError: null });
      return;
    }

    const state = get();
    if (state.selectedFund?.fund_code === fund.fund_code) {
      // 再次点击同一行 → 收起
      set({ selectedFund: null, detailData: null, detailError: null });
      return;
    }

    set({
      selectedFund: fund,
      detailLoading: true,
      detailError: null,
      detailData: null,
    });

    try {
      // 并行获取详情和 V5 情绪
      const [detail] = await Promise.all([
        fetchFundDetail(fund.fund_code).catch(() => null),
        // 尝试获取 V5 情绪，失败则静默处理
        fetchV5Sentiment(fund.fund_code).then((s) => {
          const cached: FundV5Sentiment = {
            score: s.composite_score,
            signalLevel: s.signal_level as SignalLevel,
            confidenceStars: s.confidence_stars,
            shortTerm: s.signal_level as SignalLevel,
            midTerm: s.signal_level as SignalLevel,
            longTerm: s.signal_level as SignalLevel,
            hasDivergence: false,
            divergenceType: undefined,
            advice: {
              action: '',
              level: '',
              reason: '',
              targetPositionPct: 0.5,
            },
          };
          set((prev) => ({
            sentimentCache: { ...prev.sentimentCache, [fund.fund_code]: cached },
          }));
        }).catch(() => {}),
      ]);

      set({ detailData: detail, detailLoading: false });
    } catch {
      set({ detailLoading: false });
    }
  },

  clearSelection: () =>
    set({ selectedFund: null, detailData: null, detailError: null }),

  reset: () => set({ ...INITIAL }),
}));
