/**
 * P4-7: 工具函数单元测试（Vitest 基础设施验证）
 *
 * 测试 paramsMapper 工具函数，验证 Vitest + jsdom 环境工作正常
 */
import { describe, it, expect } from "vitest";
import {
  FACTOR_LABELS,
  FACTOR_NAMES,
  SIGNAL_LEVELS,
  SIGNAL_COLORS,
  SIGNAL_LABELS,
  DEFAULT_ACTION_MAPPING,
  DEFAULT_MODEL_PARAMS,
  modelParamsToApiRequest,
  apiStrategyToLocal,
} from "../utils/paramsMapper";

// ============================================================
// 常量测试
// ============================================================

describe("FACTOR 常量", () => {
  it("FACTOR_LABELS 包含 14 个核心因子", () => {
    expect(Object.keys(FACTOR_LABELS)).toHaveLength(14);
  });

  it("FACTOR_LABELS 中文标签非空", () => {
    for (const [code, label] of Object.entries(FACTOR_LABELS)) {
      expect(label).toBeTruthy();
      expect(typeof label).toBe("string");
      expect(label.length).toBeGreaterThan(0);
    }
  });

  it("FACTOR_NAMES 与 FACTOR_LABELS 一致", () => {
    expect(FACTOR_NAMES).toEqual(Object.keys(FACTOR_LABELS));
  });

  it("包含关键因子：VOL/ADR/ERP/FLOW", () => {
    expect(FACTOR_NAMES).toContain("VOL");
    expect(FACTOR_NAMES).toContain("ADR");
    expect(FACTOR_NAMES).toContain("ERP");
    expect(FACTOR_NAMES).toContain("FLOW");
  });
});

describe("SIGNAL 常量", () => {
  it("SIGNAL_LEVELS 包含 7 级", () => {
    expect(SIGNAL_LEVELS).toHaveLength(7);
  });

  it("SIGNAL_LEVELS 顺序：S+, S, A, B, C, D, E", () => {
    expect(SIGNAL_LEVELS).toEqual(["S+", "S", "A", "B", "C", "D", "E"]);
  });

  it("SIGNAL_COLORS 每个信号都有颜色", () => {
    for (const level of SIGNAL_LEVELS) {
      expect(SIGNAL_COLORS[level]).toMatch(/^#[0-9A-F]{6}$/i);
    }
  });

  it("SIGNAL_LABELS 7 级标签都有中文描述", () => {
    for (const level of SIGNAL_LEVELS) {
      expect(SIGNAL_LABELS[level]).toBeTruthy();
    }
  });
});

describe("DEFAULT_ACTION_MAPPING", () => {
  it("每个信号级别都有对应的操作规则", () => {
    for (const level of SIGNAL_LEVELS) {
      const rule = DEFAULT_ACTION_MAPPING[level];
      expect(rule).toBeDefined();
      expect(rule.type).toMatch(/^(buy|sell_half|sell_all|hold)$/);
      expect(typeof rule.mult).toBe("number");
    }
  });

  it("S+ 是最激进的加仓（mult=2.0）", () => {
    expect(DEFAULT_ACTION_MAPPING["S+"].type).toBe("buy");
    expect(DEFAULT_ACTION_MAPPING["S+"].mult).toBe(2.0);
  });

  it("E 是清仓操作", () => {
    expect(DEFAULT_ACTION_MAPPING["E"].type).toBe("sell_all");
  });
});

describe("DEFAULT_MODEL_PARAMS", () => {
  it("signal_boundaries 是 6 个数（划分 7 个区间）", () => {
    expect(DEFAULT_MODEL_PARAMS.signal_boundaries).toHaveLength(6);
  });

  it("factor_weights 总和约等于 1.0", () => {
    const total = Object.values(
      DEFAULT_MODEL_PARAMS.factor_weights as Record<string, number>
    ).reduce((sum, w) => sum + w, 0);
    expect(total).toBeCloseTo(1.0, 1);
  });

  it("factor_weights 包含所有 14 个因子", () => {
    const weights = DEFAULT_MODEL_PARAMS.factor_weights as Record<string, number>;
    for (const name of FACTOR_NAMES) {
      expect(weights[name]).toBeDefined();
      expect(weights[name]).toBeGreaterThan(0);
    }
  });

  it("factor_enabled 默认全部启用", () => {
    const enabled = DEFAULT_MODEL_PARAMS.factor_enabled as Record<string, boolean>;
    for (const name of FACTOR_NAMES) {
      expect(enabled[name]).toBe(true);
    }
  });
});

// ============================================================
// 映射函数测试
// ============================================================

describe("modelParamsToApiRequest", () => {
  const mockInput = {
    strategy: { params: DEFAULT_MODEL_PARAMS },
    selectedFund: null,
    backtestParams: {
      startDate: "2024-01-01",
      endDate: "2024-12-31",
      initialCapital: 100000,
      strategyId: 1,
    },
  };

  it("默认（指数模式）输出 fund_code=undefined, daily_tracking=false", () => {
    const result = modelParamsToApiRequest(mockInput);
    expect(result.fund_code).toBeUndefined();
    expect(result.daily_tracking).toBe(false);
  });

  it("指数代码默认 SH000300", () => {
    const result = modelParamsToApiRequest(mockInput);
    expect(result.index_code).toBe("SH000300");
  });

  it("选中基金时 fund_code 正确传递", () => {
    const result = modelParamsToApiRequest({
      ...mockInput,
      selectedFund: { code: "000001" },
    });
    expect(result.fund_code).toBe("000001");
    expect(result.daily_tracking).toBe(true);
  });

  it("回测参数正确映射", () => {
    const result = modelParamsToApiRequest(mockInput);
    expect(result.start_date).toBe("2024-01-01");
    expect(result.end_date).toBe("2024-12-31");
    expect(result.initial_capital).toBe(100000);
  });

  it("risk_params 包含所有风控参数", () => {
    const result = modelParamsToApiRequest(mockInput);
    expect(result.risk_params).toBeDefined();
    expect(result.risk_params.max_position).toBe(0.95);
    expect(result.risk_params.min_position).toBe(0.05);
    expect(result.risk_params.take_profit).toBe(0.20);
  });
});

describe("apiStrategyToLocal", () => {
  it("解析 params_json 字符串", () => {
    const result = apiStrategyToLocal({
      id: 1,
      name: "测试策略",
      is_active: true,
      params_json: '{"factor_weights":{"VOL":0.5}}',
    });
    expect(result.id).toBe(1);
    expect(result.name).toBe("测试策略");
    expect(result.params.factor_weights.VOL).toBe(0.5);
  });

  it("params_json 为对象时直接使用", () => {
    const result = apiStrategyToLocal({
      id: 2,
      name: "策略2",
      is_active: false,
      params_json: { factor_weights: { VOL: 0.3 } },
    });
    expect(result.params.factor_weights.VOL).toBe(0.3);
  });

  it("保留 id/name/is_active 字段", () => {
    const result = apiStrategyToLocal({
      id: 42,
      name: "重要策略",
      is_active: true,
      params_json: "{}",
    });
    expect(result.id).toBe(42);
    expect(result.name).toBe("重要策略");
    expect(result.is_active).toBe(true);
  });
});

// ============================================================
// 浏览器 API mock 验证（jsdom 环境验证）
// ============================================================

describe("jsdom 环境验证", () => {
  it("window 对象存在", () => {
    expect(typeof window).toBe("object");
  });

  it("localStorage 可用", () => {
    window.localStorage.setItem("test", "1");
    expect(window.localStorage.getItem("test")).toBe("1");
    window.localStorage.removeItem("test");
    expect(window.localStorage.getItem("test")).toBeNull();
  });

  it("matchMedia mock 可用", () => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    expect(mq).toBeDefined();
    expect(typeof mq.matches).toBe("boolean");
  });
});
