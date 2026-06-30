// Vitest configuration (P4-7)
// 注意：用 .mjs 而非 .ts，避免 vite 写临时 .timestamp 文件触发沙箱权限
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    // 优先用 jsdom（提供 DOM API），fallback 可改为 "node"
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      reporter: ["text", "html"],
      exclude: [
        "node_modules/",
        "src/__tests__/",
        "src/main.tsx",
      ],
    },
  },
});
