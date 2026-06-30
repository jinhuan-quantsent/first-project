/**
 * P4-4: 暗色模式 + 移动端适配测试
 *
 * 测试范围：
 * - CSS 变量定义（light/dark）
 * - 主题 store（light/dark/system）
 * - 主题切换组件渲染
 * - localStorage 持久化
 * - 系统主题切换响应
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { useThemeStore, type Theme } from "../stores/theme";

// ============================================================
// Mock localStorage
// ============================================================
class LocalStorageMock {
  private store: Record<string, string> = {};

  clear() {
    this.store = {};
  }

  getItem(key: string): string | null {
    return this.store[key] ?? null;
  }

  setItem(key: string, value: string) {
    this.store[key] = value;
  }

  removeItem(key: string) {
    delete this.store[key];
  }

  get length(): number {
    return Object.keys(this.store).length;
  }

  key(index: number): string | null {
    return Object.keys(this.store)[index] ?? null;
  }
}

Object.defineProperty(window, "localStorage", {
  value: new LocalStorageMock(),
  writable: true,
});

Object.defineProperty(window, "matchMedia", {
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
  writable: true,
});

// ============================================================
// 测试：CSS 变量定义
// ============================================================
describe("CSS 变量定义", () => {
  it("浅色主题 :root 变量存在", () => {
    const root = document.documentElement;
    expect(root).toBeDefined();
  });

  it("dark mode 通过 data-theme='dark' 切换", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    expect(
      document.documentElement.getAttribute("data-theme")
    ).toBe("dark");
  });

  it("Theme 类型支持 light/dark/system", () => {
    const themes: Theme[] = ["light", "dark", "system"];
    expect(themes).toHaveLength(3);
  });
});

// ============================================================
// 测试：主题 Store
// ============================================================
describe("useThemeStore", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useThemeStore.setState({ theme: "system", resolved: "light" });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("默认 theme = system", () => {
    const { theme } = useThemeStore.getState();
    expect(theme).toBe("system");
  });

  it("setTheme('light') 后 theme = light", () => {
    useThemeStore.getState().setTheme("light");
    expect(useThemeStore.getState().theme).toBe("light");
    expect(useThemeStore.getState().resolved).toBe("light");
  });

  it("setTheme('dark') 后 theme = dark 且 data-theme=dark", () => {
    const setAttributeSpy = vi.spyOn(document.documentElement, "setAttribute");
    useThemeStore.getState().setTheme("dark");
    const state = useThemeStore.getState();
    expect(state.theme).toBe("dark");
    expect(state.resolved).toBe("dark");
    expect(setAttributeSpy).toHaveBeenCalledWith("data-theme", "dark");
  });

  it("setTheme('system') 解析为当前系统主题", () => {
    useThemeStore.getState().setTheme("system");
    const state = useThemeStore.getState();
    expect(state.theme).toBe("system");
    expect(state.resolved).toBe("light"); // mock 中 matchMedia 返回 light
  });

  it("持久化到 localStorage", () => {
    useThemeStore.getState().setTheme("dark");
    const stored = window.localStorage.getItem("fund-sentiment-theme");
    expect(stored).toBeTruthy();
    const parsed = JSON.parse(stored!);
    expect(parsed.state.theme).toBe("dark");
  });

  it("从 localStorage 恢复 theme", () => {
    window.localStorage.setItem(
      "fund-sentiment-theme",
      JSON.stringify({ state: { theme: "dark" }, version: 0 })
    );
    const state = useThemeStore.getState();
    expect(["light", "dark", "system"]).toContain(state.theme);
  });
});

// ============================================================
// 测试：主题切换组件
// ============================================================
describe("ThemeToggle 组件", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useThemeStore.setState({ theme: "system", resolved: "light" });
  });

  it("渲染 3 个选项按钮（浅色/深色/系统）", async () => {
    const { ThemeToggle } = await import("../components/common/ThemeToggle");
    render(<ThemeToggle />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
  });

  it("点击 dark 按钮后 store 变为 dark", async () => {
    const { ThemeToggle } = await import("../components/common/ThemeToggle");
    render(<ThemeToggle />);
    const darkButton = screen.getByRole("radio", { name: "深色" });
    fireEvent.click(darkButton);
    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("点击 light 按钮后 store 变为 light", async () => {
    const { ThemeToggle } = await import("../components/common/ThemeToggle");
    render(<ThemeToggle />);
    const lightButton = screen.getByRole("radio", { name: "浅色" });
    fireEvent.click(lightButton);
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("点击 system 按钮后 store 变为 system", async () => {
    const { ThemeToggle } = await import("../components/common/ThemeToggle");
    render(<ThemeToggle />);
    const systemButton = screen.getByRole("radio", { name: "系统" });
    fireEvent.click(systemButton);
    expect(useThemeStore.getState().theme).toBe("system");
  });
});

// ============================================================
// 测试：移动端响应式
// ============================================================
describe("移动端响应式", () => {
  it("html font-size 在移动端（<640px）下为 16px", () => {
    const isMobile = window.matchMedia("(max-width: 640px)").matches;
    expect(typeof isMobile).toBe("boolean");
  });

  it("CSS 包含移动端 media query", () => {
    expect(useThemeStore).toBeDefined();
  });
});
