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
  guestLogin: () => Promise<void>;
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

    guestLogin: async () => {
      set({ auth: { ...get().auth, authLoading: true, authError: null } });
      try {
        // 调用后端 login 端点获取真实 JWT（AUTH_DISABLED 模式下后端签发 demo_user token）
        const data: AuthResponse = await authLogin('guest@fundsent.top', 'guest-pass');
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
        // 如果 login 端点不可用，降级为旧的 guest-token 模式
        const guestUser = { user_id: 'guest', email: 'guest@fundsent.top', role: 'guest' } as User;
        const guestToken = 'guest-token';
        set({
          auth: {
            user: guestUser,
            token: guestToken,
            isAuthenticated: true,
            authLoading: false,
            authError: null,
          },
        });
        localStorage.setItem(TOKEN_KEY, guestToken);
        localStorage.setItem(USER_KEY, JSON.stringify(guestUser));
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
        // 检测旧的 guest-token（无 JWT），清除以触发重新获取真实 JWT
        if (token === 'guest-token') {
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem(USER_KEY);
          return;
        }
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
