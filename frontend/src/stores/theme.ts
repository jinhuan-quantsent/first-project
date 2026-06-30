/**
 * P4-4: 主题切换 Store
 *
 * 功能：
 * - light / dark / system 三种模式
 * - localStorage 持久化
 * - 监听系统主题变化（system 模式）
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  resolved: ResolvedTheme;
  setTheme: (theme: Theme) => void;
  _setResolved: (resolved: ResolvedTheme) => void;
}

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(theme: Theme, resolved: ResolvedTheme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.setAttribute("data-theme", resolved);
  // 同步 meta 颜色
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute("content", resolved === "dark" ? "#0F172A" : "#F8FAFC");
  }
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "system",
      resolved: "light",

      setTheme: (theme: Theme) => {
        const resolved: ResolvedTheme =
          theme === "system" ? getSystemTheme() : theme;
        applyTheme(theme, resolved);
        set({ theme, resolved });
      },

      _setResolved: (resolved: ResolvedTheme) => {
        applyTheme(get().theme, resolved);
        set({ resolved });
      },
    }),
    {
      name: "fund-sentiment-theme",
      // 只持久化 theme，不持久化 resolved（resolved 每次都重新计算）
      partialize: (state) => ({ theme: state.theme }),
    }
  )
);

// 监听系统主题变化（system 模式下）
if (typeof window !== "undefined") {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", (e) => {
    const state = useThemeStore.getState();
    if (state.theme === "system") {
      const newResolved: ResolvedTheme = e.matches ? "dark" : "light";
      state._setResolved(newResolved);
    }
  });
}
