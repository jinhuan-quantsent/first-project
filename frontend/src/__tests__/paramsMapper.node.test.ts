/**
 * P4-7: 工具函数单元测试（Node.js 内置 test runner 验证）
 *
 * 这个文件用 Node 22 的内置 test runner（无需 vite/vitest 启动）
 * 用于在受限沙箱中验证测试基础设施的工作流思路
 *
 * 实际项目推荐用 Vitest（已配置在 package.json + vitest.config.mjs）
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  FACTOR_LABELS,
  FACTOR_NAMES,
  SIGNAL_LEVELS,
  DEFAULT_ACTION_MAPPING,
  DEFAULT_MODEL_PARAMS,
  modelParamsToApiRequest,
  apiStrategyToLocal,
} from "../utils/paramsMapper.ts";

test("FACTOR_LABELS 包含 14 个核心因子", () => {
  assert.equal(Object.keys(FACTOR_LABELS).length, 14);
});

test("FACTOR_NAMES 与 FACTOR_LABELS 一致", () => {
  assert.deepEqual(FACTOR_NAMES, Object.keys(FACTOR_LABELS));
});

test("SIGNAL_LEVELS 7 级顺序", () => {
  assert.deepEqual(SIGNAL_LEVELS, ["S+", "S", "A", "B", "C", "D", "E"]);
});

test("DEFAULT_ACTION_MAPPING S+ 是 buy/2.0", () => {
  assert.equal(DEFAULT_ACTION_MAPPING["S+"].type, "buy");
  assert.equal(DEFAULT_ACTION_MAPPING["S+"].mult, 2.0);
});

test("factor_weights 总和约等于 1.0", () => {
  const total = Object.values(
    DEFAULT_MODEL_PARAMS.factor_weights
  ).reduce((sum, w) => sum + w, 0);
  assert.ok(Math.abs(total - 1.0) < 0.01, `total=${total}`);
});

test("modelParamsToApiRequest 指数模式", () => {
  const result = modelParamsToApiRequest({
    strategy: { params: DEFAULT_MODEL_PARAMS },
    selectedFund: null,
    backtestParams: {
      startDate: "2024-01-01",
      endDate: "2024-12-31",
      initialCapital: 100000,
      strategyId: 1,
    },
  });
  assert.equal(result.fund_code, undefined);
  assert.equal(result.daily_tracking, false);
  assert.equal(result.index_code, "SH000300");
});

test("modelParamsToApiRequest 基金模式", () => {
  const result = modelParamsToApiRequest({
    strategy: { params: DEFAULT_MODEL_PARAMS },
    selectedFund: { code: "000001" },
    backtestParams: {
      startDate: "2024-01-01",
      endDate: "2024-12-31",
      initialCapital: 100000,
      strategyId: 1,
    },
  });
  assert.equal(result.fund_code, "000001");
  assert.equal(result.daily_tracking, true);
});

test("apiStrategyToLocal 解析 JSON 字符串", () => {
  const result = apiStrategyToLocal({
    id: 1,
    name: "测试",
    is_active: true,
    params_json: '{"factor_weights":{"VOL":0.5}}',
  });
  assert.equal(result.id, 1);
  assert.equal(result.params.factor_weights.VOL, 0.5);
});
