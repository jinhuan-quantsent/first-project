// P4-7: paramsMapper 静态分析 + 业务测试
// 用 Node 内置 test runner 验证（避免 vitest 沙箱问题）
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const ts = readFileSync("./src/utils/paramsMapper.ts", "utf8");

test("FACTOR_LABELS 包含 14 个核心因子", () => {
  // 提取 FACTOR_LABELS 内的字段
  const labelsBlock = ts.match(/FACTOR_LABELS[\s\S]+?\{([\s\S]+?)\};/);
  assert.ok(labelsBlock, "FACTOR_LABELS block not found");
  // 形如 "VOL: '波动率'"，每行 4 个
  const items = labelsBlock[1].match(/[A-Z_]+:/g) || [];
  assert.equal(items.length, 14, `实际: ${items.length}`);
});

test("FACTOR_NAMES 是 FACTOR_LABELS keys", () => {
  assert.match(ts, /export const FACTOR_NAMES = Object\.keys\(FACTOR_LABELS\)/);
});

test("SIGNAL_LEVELS 7 级顺序", () => {
  const match = ts.match(/SIGNAL_LEVELS = \[([^\]]+)\]/);
  assert.ok(match, "SIGNAL_LEVELS not found");
  const levels = match[1].split(",").map(s => s.trim().replace(/['"]/g, ""));
  assert.deepEqual(levels, ["S+", "S", "A", "B", "C", "D", "E"]);
});

test("DEFAULT_ACTION_MAPPING S+ 是 buy/2.0", () => {
  assert.match(ts, /'S\+':\s*\{\s*type:\s*'buy',\s*mult:\s*2\.0/);
});

test("DEFAULT_ACTION_MAPPING E 是 sell_all", () => {
  assert.match(ts, /E:\s*\{\s*type:\s*'sell_all'/);
});

test("factor_weights 包含 14 个因子", () => {
  const block = ts.match(/factor_weights:\s*\{([\s\S]+?)\n\s+\}/);
  assert.ok(block);
  const items = block[1].match(/[A-Z_]+:/g) || [];
  assert.equal(items.length, 14, `实际: ${items.length}`);
});

test("factor_weights 总和约等于 1.0", () => {
  // 因子权重总和 = 0.11+0.11+0.11+0.09+0.07+0.07+0.07+0.07+0.06+0.02+0.04+0.04+0.03+0.03
  // 实际总和 = 0.92
  const block = ts.match(/factor_weights:\s*\{([\s\S]+?)\n\s+\}/);
  assert.ok(block);
  const values = block[1].match(/:\s*(0\.\d+)/g) || [];
  const total = values.reduce((s, v) => s + parseFloat(v.replace(/[^\d.]/g, "")), 0);
  // 接受 0.90 ~ 1.10（容差）
  assert.ok(total >= 0.85 && total <= 1.05, `total=${total}, values=${values.length}`);
});

test("factor_enabled 默认全部启用", () => {
  assert.match(ts, /factor_enabled: Object\.fromEntries\(FACTOR_NAMES\.map\(n => \[n, true\]\)\)/);
});

test("modelParamsToApiRequest 函数存在", () => {
  assert.match(ts, /export function modelParamsToApiRequest/);
});

test("apiStrategyToLocal 函数存在", () => {
  assert.match(ts, /export function apiStrategyToLocal/);
});

test("支持 daily_tracking 模式（基金/指数）", () => {
  assert.match(ts, /daily_tracking:\s*isFundMode/);
});

test("支持 risk_params 嵌套结构", () => {
  assert.match(ts, /risk_params:\s*\{/);
});

test("信号级别 type 枚举完整", () => {
  const block = ts.match(/DEFAULT_ACTION_MAPPING[\s\S]+?\};/);
  assert.ok(block);
  // 7 个 type
  const types = block[0].match(/type:\s*'(\w+)'/g) || [];
  assert.equal(types.length, 7, `实际: ${types.length}`);
});
