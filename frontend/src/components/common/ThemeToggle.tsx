/**
 * P4-4: 主题切换组件
 *
 * 三种模式：light / dark / system（跟随系统）
 */
import { useEffect } from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useThemeStore, type Theme } from "../../stores/theme";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "浅色", icon: Sun },
  { value: "dark", label: "深色", icon: Moon },
  { value: "system", label: "系统", icon: Monitor },
];

export function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  // 初始化：应用持久化的 theme
  useEffect(() => {
    setTheme(theme);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="inline-flex rounded-lg border p-1"
      style={{ borderColor: "var(--border-color)" }}
      role="radiogroup"
      aria-label="主题切换"
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            onClick={() => setTheme(value)}
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            className="flex items-center justify-center w-8 h-8 rounded transition-colors"
            style={{
              backgroundColor: active ? "var(--brand-cyan)" : "transparent",
              color: active ? "white" : "var(--text-secondary)",
            }}
          >
            <Icon size={16} />
          </button>
        );
      })}
    </div>
  );
}
