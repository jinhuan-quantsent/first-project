/**
 * P4-7: Vitest 单元测试基础设施 - 全局 setup
 *
 * 加载 jest-dom 扩展（toBeInTheDocument 等）
 * 设置 localStorage / matchMedia 等浏览器 API mock
 */
import "@testing-library/jest-dom/vitest";

// localStorage mock（jsdom 应有，但保险起见）
if (typeof window !== "undefined" && !window.localStorage) {
  const store: Record<string, string> = {};
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
      clear: () => { for (const k in store) delete store[k]; },
      key: (i: number) => Object.keys(store)[i] ?? null,
      get length() { return Object.keys(store).length; },
    },
    writable: true,
  });
}

// matchMedia mock（jsdom 默认无实现）
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},     // deprecated
      removeListener: () => {},  // deprecated
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
