import client from "./client";

/** 获取模块数据版本号 */
export async function fetchCacheVersion(
  modules?: string[]
): Promise<Record<string, string | null>> {
  const params = modules?.length ? `?modules=${modules.join(",")}` : "";
  const res = await client.get(`/api/v5/cache/version${params}`);
  return res.data?.data ?? res.data ?? {};
}
