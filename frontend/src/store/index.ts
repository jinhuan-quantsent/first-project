import { create } from 'zustand';
import type {
  SentimentLabel,
  IndexSnapshot,
  MarketSnapshot,
  MultiIndexData,
  CompositeSentiment,
  User,
  AuthResponse,
} from '../types';
import { fetchMarketSnapshot, fetchMultiIndex } from '../api/market';
import { login as authLogin, register as authRegister } from '../api/auth';

const TOKEN_KEY = 'fsa_jwt_token';
const USER_KEY = 'fsa_user_info';

// --- Auth State ---
interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  authLoading: boolean;
  authError: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  restoreSession: () => void;
  clearError: () => void;
}

interface AuthSlice {
  auth: AuthState;
}

// --- Market State ---
interface MarketState {
  snapshot: MarketSnapshot | null;
  snapshotLoading: boolean;
  snapshotError: string | null;
  selectedIndex: string;
  multiIndexData: MultiIndexData[];
  composite: CompositeSentiment | null;
  marketLoading: boolean;
  marketError: string | null;
  disclaimerAccepted: boolean;

  loadSnapshot: () => Promise<void>;
  loadMultiIndex: (codes?: string) => Promise<void>;
  setSelectedIndex: (code: string) => void;
  acceptDisclaimer: () => void;
}

type AppState = AuthSlice & MarketState;

export const useAppStore = create<AppState>((set, get) => ({
  // --- Auth 初始状态 ---
  auth: {
    user: null,
    token: null,
    isAuthenticated: false,
    authLoading: false,
    authError: null,

    login: async (email: string, password: string) => {
      set({ auth: { ...get().auth, authLoading: true, authError: null } });
      try {
        const data: AuthResponse = await authLogin(email, password);
        set({
          auth: {
            user: data.user,
            token: data.access_token,
            isAuthenticated: true,
            authLoading: false,
            authError: null,
          },
        });
        localStorage.setItem(TOKEN_KEY, data.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      } catch (err: any) {
        const msg = err?.response?.data?.message || '登录失败';
        set({ auth: { ...get().auth, authLoading: false, authError: msg } });
        throw new Error(msg);
      }
    },

    register: async (email: string, password: string) => {
      set({ auth: { ...get().auth, authLoading: true, authError: null } });
      try {
        await authRegister(email, password);
        set({ auth: { ...get().auth, authLoading: false } });
      } catch (err: any) {
        const msg = err?.response?.data?.message || '注册失败';
        set({ auth: { ...get().auth, authLoading: false, authError: msg } });
        throw new Error(msg);
      }
    },

    logout: () => {
      set({
        auth: {
          user: null,
          token: null,
          isAuthenticated: false,
          authLoading: false,
          authError: null,
        },
      });
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },

    restoreSession: () => {
      const token = localStorage.getItem(TOKEN_KEY);
      const userStr = localStorage.getItem(USER_KEY);
      if (token && userStr) {
        try {
          const user = JSON.parse(userStr) as User;
          set({
            auth: {
              user,
              token,
              isAuthenticated: true,
              authLoading: false,
              authError: null,
            },
          });
        } catch {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(USER_KEY);
        }
      }
    },

    clearError: () => {
      set({ auth: { ...get().auth, authError: null } });
    },
  },

  // --- Market 初始状态 ---
  snapshot: null,
  snapshotLoading: false,
  snapshotError: null,
  selectedIndex: 'SH000300',
  multiIndexData: [],
  composite: null,
  marketLoading: false,
  marketError: null,
  disclaimerAccepted: false,

  loadSnapshot: async () => {
    set({ snapshotLoading: true, snapshotError: null });
    try {
      const data = await fetchMarketSnapshot();
      set({ snapshot: data, snapshotLoading: false });
    } catch {
      set({ snapshotError: '加载市场快照失败', snapshotLoading: false });
    }
  },

  loadMultiIndex: async (codes?: string) => {
    set({ marketLoading: true, marketError: null });
    try {
      const data = await fetchMultiIndex(codes);
      set({
        multiIndexData: data.indexes,
        composite: data.composite,
        marketLoading: false,
      });
    } catch {
      set({ marketError: '加载市场数据失败', marketLoading: false });
    }
  },

  setSelectedIndex: (code: string) => {
    set({ selectedIndex: code });
  },

  acceptDisclaimer: () => {
    set({ disclaimerAccepted: true });
    localStorage.setItem('disclaimer_accepted', 'true');
  },
}));
