import { useEffect, useRef, useCallback } from "react";
import { fetchCacheVersion } from "../api/cache";

/**
 * 自动刷新Hook — 轮询后端数据版本号，发现变化才触发fetchFn
 *
 * @param modules 关注的模块列表，如 ["signal_board", "holdings"]
 * @param fetchFn 版本变化时调用的刷新函数
 * @param interval 轮询间隔，默认60秒
 */
export function useAutoRefresh(
  modules: string[],
  fetchFn: () => void | Promise<void>,
  interval: number = 60000
) {
  const lastVersionsRef = useRef<Record<string, string>>({});
  const fetchFnRef = useRef(fetchFn);

  // 保持fetchFn最新引用，不触发重新轮询
  useEffect(() => {
    fetchFnRef.current = fetchFn;
  }, [fetchFn]);

  const checkVersions = useCallback(async () => {
    try {
      const versions = await fetchCacheVersion(modules);

      // 首次获取 — 记录但不触发刷新（避免页面加载时重复请求）
      if (Object.keys(lastVersionsRef.current).length === 0) {
        lastVersionsRef.current = versions as Record<string, string>;
        return;
      }

      // 比较版本号
      let changed = false;
      for (const m of modules) {
        const oldVal = lastVersionsRef.current[m];
        const newVal = versions[m];
        if (newVal && oldVal !== newVal) {
          changed = true;
          break;
        }
      }

      if (changed) {
        lastVersionsRef.current = versions as Record<string, string>;
        // 随机延迟0-2秒错峰
        const delay = Math.random() * 2000;
        setTimeout(() => fetchFnRef.current(), delay);
      }
    } catch (e) {
      // 静默失败，不影响用户体验
      console.debug("[useAutoRefresh] check failed:", e);
    }
  }, [modules]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval>;

    // 立即检查一次
    checkVersions();

    // 定时轮询
    timer = setInterval(checkVersions, interval);

    // 页面不可见时暂停，可见时恢复
    const handleVisibilityChange = () => {
      if (document.hidden) {
        clearInterval(timer);
      } else {
        // 回到前台立即检查一次
        checkVersions();
        timer = setInterval(checkVersions, interval);
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [checkVersions, interval]);
}
