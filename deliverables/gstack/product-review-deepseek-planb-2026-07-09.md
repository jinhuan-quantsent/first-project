# 方案B（独立顾问模式）产品评审报告

**评审人**: gstack-product-reviewer
**日期**: 2026-07-09
**评审范围**: DeepSeek 方案B 产品设计一致性、可行性、风险评估
**评审模式**: 纯研究，不修改任何代码

---

## 一、关键事实修正（对 team-lead 已有发现的验证与纠正）

在正式评审前，必须先纠正 team-lead 分析中的 **2 处事实性错误**，否则后续评审会建立在错误前提上。

### 修正 1: "4个API全未实现" — 错误，4个API全部已实现

team-lead 认为 validation-today / validation-history / validation-stats / validation-download 四个 API 全未实现。经代码核查，**4 个 API 全部已在 `snapshot_router.py` 中实现**：

| API | 路由 | 代码位置 | 状态 |
|-----|------|---------|------|
| validation-today | `GET /api/v5/validation-today/{fund_code}` | snapshot_router.py L825 | ✅ 已实现 |
| validation-history | `GET /api/v5/validation-history` | snapshot_router.py L596 | ✅ 已实现 |
| validation-stats | `GET /api/v5/validation-stats` | snapshot_router.py L675 | ✅ 已实现 |
| validation-download | `GET /api/v5/validation-download` | snapshot_router.py L536 | ✅ 已实现 |

**影响**：方案B 不需要从零建 API，而是在现有 API 基础上扩展返回字段。工作量大幅降低。

### 修正 2: "前端组件已有但API缺失" — 部分错误

前端组件 `AIAnalysisPanel.tsx` 调用的 `/api/v5/validation-today/{fund_code}` **已实现且已联通**。前端能正常获取数据并渲染。问题不是"API 缺失"，而是"API 返回的数据结构简化了"——只返回 3 个 DeepSeek 字段而非项目书设计的 9 个，且一致性计算因 override 机制永远返回 "consistent"。

### team-lead 其他发现验证结果

| # | team-lead 发现 | 验证结果 |
|---|--------------|---------|
| 1 | 项目书 G6 设计 9 列 vs 实际 DB 3 列 | ✅ 确认。实际 DB 只有 deepseek_advice / deepseek_advice_action / deepseek_advice_correct 三列 |
| 2 | 项目书 G7 一致性分析 4 列完全缺失 | ✅ 确认。G7 被改成了"回验评分+系统建议"6 列，4 个一致性字段不存在 |
| 3 | T+1 回验 bug：用 override 后的 action 测 AI 准确率 | ✅ 确认。scheduler.py L3062-3070，`deepseek_advice_correct` 用的 `record.deepseek_advice_action` 是 override 后的值 |
| 4 | DeepSeek 被实现为"翻译器" | ✅ 确认。scheduler.py L2700 注释"金额由系统算，模型只翻译，零黑箱"；L2753 prompt 写"请勿修改任何数字，仅供翻译" |
| 5 | action 被强制 override | ✅ 确认。scheduler.py L2838-2856，模型解析的 action 如与系统不一致，强制 override 并插入 `[系统override]` 标注 |

---

## 二、方案B与项目书设计对齐度评估

### 2.1 总体对齐度：~54%

项目书设计了 13 个 DeepSeek/一致性相关字段（G6 的 9 列 + G7 的 4 列），方案B 提出 7 个独立字段。对齐分析如下：

### 2.2 逐字段对齐矩阵

| # | 项目书设计字段 | 方案B是否覆盖 | 当前DB是否存在 | 差距分析 |
|---|-------------|-------------|-------------|---------|
| 1 | deepseek_advice（完整文本） | ✅ 覆盖（隐含） | ✅ 已存在 | 无差距，方案B应保留此字段存储AI完整输出 |
| 2 | deepseek_action | ✅ 覆盖 | ⚠️ 列存在但语义错误 | 列名是 deepseek_advice_action，但存的是 override 后的系统 action，需改为存 AI 原始 action |
| 3 | deepseek_target_pct | ✅ 覆盖 | ❌ 缺失 | 需新增 DDL |
| 4 | deepseek_confidence | ✅ 覆盖 | ❌ 缺失 | 需新增 DDL |
| 5 | deepseek_reason | ❌ 未覆盖 | ❌ 缺失 | 方案B 7 字段中无 reason，但有 summary。reason 和 summary 有重叠，可合并 |
| 6 | deepseek_market_view | ✅ 覆盖 | ❌ 缺失 | 需新增 DDL |
| 7 | deepseek_risk_level | ✅ 覆盖 | ❌ 缺失 | 需新增 DDL |
| 8 | deepseek_time_horizon | ✅ 覆盖 | ❌ 缺失 | 需新增 DDL |
| 9 | deepseek_summary | ✅ 覆盖 | ❌ 缺失 | 需新增 DDL |
| 10 | advice_consistent | ❌ 未覆盖 | ❌ 缺失 | 方案B 未提及 G7 一致性字段，但这是双列对比的核心配套 |
| 11 | consistency_score | ❌ 未覆盖 | ❌ 缺失 | 同上 |
| 12 | consistency_note | ❌ 未覆盖 | ❌ 缺失 | 同上 |
| 13 | conflict_fields | ❌ 未覆盖 | ❌ 缺失 | 同上 |

### 2.3 缺失项清单

**方案B未覆盖但项目书设计的字段（3 个）**：
1. `deepseek_reason` — AI 建议的推理过程文本。方案B 的 `summary` 可部分替代，但 reason 更详细。**建议合并到 summary 或保留为独立字段**。
2. `advice_consistent` / `consistency_score` / `consistency_note` / `conflict_fields` — G7 一致性分析 4 列。方案B 的"结构化对比"隐含需要一致性分析，但未明确列出这些字段。**这是方案B的最大设计缺口**。

**当前 DB 缺失需新增的列（10 个）**：
- DeepSeek 独立字段：deepseek_target_pct, deepseek_confidence, deepseek_market_view, deepseek_risk_level, deepseek_time_horizon, deepseek_summary（6 列）
- 一致性分析：advice_consistent, consistency_score, consistency_note, conflict_fields（4 列）
- deepseek_advice_action 语义变更（无需新增列，但需改写入逻辑）

### 2.4 方案B 设计缺漏

方案B 提出"7 个独立字段与系统建议做结构化对比"，但 **未设计对比结果的存储方案**。项目书的 G7（4 列一致性分析）正是这个对比结果的存储。方案B 需补充：

- 一致性状态如何计算？（项目书已有定义：action 一致 + target_pct 差值 <5% = consistent）
- 一致性结果存在哪里？（需要 G7 的 4 列）
- 冲突字段如何记录？（需要 conflict_fields 列）

---

## 三、当前实现的核心问题深度分析

### 3.1 Override 机制导致一致性分析完全失效

**问题链路**：

```
14:45 系统建议写入 actual_action = 系统action（来自 daily_signal_snapshot.action_advice）
14:47 DeepSeek 调用，解析模型首行得到 advice_action
      → 如果 advice_action ≠ system_action_code，强制 override
      → deepseek_advice_action = system_action_code（= actual_action）
14:47 一致性计算：actual_action vs deepseek_advice_action
      → 永远 == → 永远 "consistent"
```

**证据**：
- scheduler.py L2716: `snap_action = snap_row.action_advice`（系统 action 来源）
- scheduler.py L2840: `system_action_code = _action_cn_to_code.get(system_action, "hold")`
- scheduler.py L2844: `final_action = system_action_code`（override）
- scheduler.py L2867: `db_record.deepseek_advice_action = final_action`（存 override 值）
- snapshot_router.py L950-952: `sys_action = today_data["actual_action"]` vs `ai_action = today_data["deepseek_advice_action"]` → 永远相等

**结论**：当前的双列对比 UI 展示的是一个"假对比"——左列和右列的 action 永远相同，一致性横条永远绿色。用户看到的"AI 分析"实际上是系统建议的翻译版。

### 3.2 T+1 回验测的是系统准确率不是 AI 准确率

**问题链路**：

```
T+1 17:35 回验：
  ds_action = record.deepseek_advice_action  ← 这是 override 后的系统 action
  if ds_action == "increase":
      deepseek_advice_correct = 1 if actual_trend == "up" else 0
```

由于 `deepseek_advice_action` 永远等于系统 action，`deepseek_advice_correct` 实际测的是 **系统建议准确率**，不是 AI 建议准确率。

**但有一个补救机制**：override 发生时，原始模型 action 被存入 `ext_text1`（JSON 格式 `{"raw_action": "xxx", "flag": "model_mismatch"}`）。理论上可以用这个字段回溯 AI 的真实准确率，但：
- 只有发生 mismatch 时才写入 ext_text1
- 未发生 mismatch 时（模型恰好和系统一致），AI 的真实 action 丢失
- ext_text1 是 String(200)，JSON 解析有风险

### 3.3 前端组件评估

**AIAnalysisPanel.tsx（452 行）当前状态**：

| 方面 | 当前实现 | 方案B 需要 |
|------|---------|-----------|
| ValidationRecord 接口 | 40+ 字段，DeepSeek 仅 3 个 | 需新增 6-7 个 DeepSeek 字段定义 |
| 双列对比 | 左列系统 / 右列 AI，但 action 永远相同 | 需展示 AI 独立 action（可能不同于系统） |
| 一致性横条 | 永远绿色（consistent） | 需支持真实的 conflict/partial 状态 |
| AI 建议详情 | 仅展示 deepseek_advice 全文 | 需结构化展示 confidence/risk_level/market_view 等 |
| AI 置信度 | 无展示 | 需新增置信度可视化 |
| T+1 回验 | 展示 deepseek_advice_correct（测的是系统） | 需区分系统准确率 vs AI 准确率 |

**改动力度估算**：
- 接口定义：+6-7 行（新增字段类型）
- AI 建议列重构：~60-80 行（新增 confidence/risk/view 展示卡片）
- 一致性逻辑：~10 行（后端改后前端自动适配，但需加 conflict 状态的 UI 提示）
- T+1 回验区域：~20-30 行（区分系统准确率 vs AI 准确率）
- 免责声明：~10 行
- **总计：~110-140 行变更（约 25-30% 改动率）**

---

## 四、产品风险矩阵

| # | 风险项 | 严重度 | 影响范围 | 缓解措施 |
|---|-------|--------|---------|---------|
| R1 | **用户信任风险**：AI 说"减仓"系统说"持有"，用户听谁的？ | 🔴 高 | 所有持仓基金 | 1) 展示双方历史准确率让数据说话 2) AI 建议标注"仅供参考" 3) conflict 时提供"决策权重"提示（如：系统建议有 Gate 风控支撑，AI 建议有宏观视角补充） |
| R2 | **数据断层风险**：翻译器模式的历史数据与独立顾问模式不兼容 | 🟡 中 | 历史回验分析 | 1) 用 ext_text1 或新增 mode 列标记数据模式 2) AI 准确率统计从独立顾问模式上线日起重新计算 3) 翻译器模式的历史数据仅用于系统准确率分析 |
| R3 | **一致性假象风险**：如果只去掉 override 但不建 G7 字段，一致性计算仍可能出错 | 🟡 中 | 前端展示 | 1) 同步实现 G7 一致性字段 2) 后端计算一致性而非前端推断 3) conflict 场景加人工决策提示 |
| R4 | **AI 幻觉风险**：独立顾问模式下 AI 自由发挥，可能给出不合理建议 | 🟡 中 | 投资决策 | 1) Prompt 中约束 AI 在给定数据范围内分析 2) 后端校验 AI 输出的 action 是否在 increase/hold/decrease 范围内 3) target_pct 校验是否在 0-1 范围 |
| R5 | **API 成本风险**：独立分析比翻译需要更多 token | 🟢 低 | 运营成本 | 1) 监控 token 用量 2) 设置 max_tokens 上限 3) 考虑用 JSON 结构化输出减少冗余文本 |
| R6 | **前端改动力度风险**：452 行组件需 25-30% 改动 | 🟢 低 | 开发周期 | 1) 分阶段实施（见第五节）2) Phase 1 只需后端改动，前端一致性横条自动生效 |
| R7 | **Prompt 注入风险**：独立模式下 AI 有更多自由度 | 🟢 低 | 系统安全 | 1) 基金名称等用户数据做脱敏 2) 要求 JSON 格式输出 3) 后端校验所有 AI 输出字段 |
| R8 | **双轨回验混淆风险**：系统准确率和 AI 准确率混在一起展示 | 🟡 中 | 数据分析 | 1) 前端明确区分"系统准确率"和"AI 准确率"两个指标 2) validation-stats API 分别返回两个准确率 3) CSV 下载增加 AI 独立 action 列 |

---

## 五、推荐分阶段实施路径

方案B 一次性做完 7 层改造 + 4 列 G7 一致性 = 11 列 DDL + prompt 重构 + 前端重构，风险过高。推荐 3 阶段渐进实施：

### Phase 1: 去 Override + 修回验 Bug（零 DDL，纯代码改动）

**目标**：让现有的双列对比和一致性分析真正生效

| 改动项 | 文件 | 改动内容 | 工作量 |
|-------|------|---------|--------|
| 去除 override | scheduler.py L2838-2872 | 删除强制 override 逻辑，`deepseek_advice_action` 直接存模型解析的原始 action | ~15 行 |
| 修 T+1 回验 | scheduler.py L3062-3070 | `deepseek_advice_correct` 已自动修复（因为 action 不再被 override） | 0 行（自动修复） |
| 一致性自动生效 | snapshot_router.py L948-958 | 无需改动，`actual_action` vs `deepseek_advice_action` 现在可能不同 | 0 行（自动生效） |
| 前端自动适配 | AIAnalysisPanel.tsx | 一致性横条会显示真实的 consistent/partial/conflict | 0 行（自动适配） |

**风险**：极低。纯删除 override 逻辑，不新增任何字段。
**收益**：双列对比和一致性分析立即从"假对比"变为"真对比"。
**前置条件**：Prompt 需微调，让 AI 知道它可以给出独立判断（当前 prompt 要求"复述系统建议"，需改为"给出你的独立判断"）。

### Phase 2: 核心 3 字段（3 列 DDL + Prompt 重构 + 前端增强）

**目标**：让 AI 的建议有结构化的置信度、仓位、理由

| 新增字段 | 类型 | 用途 |
|---------|------|------|
| deepseek_confidence | String(20) | AI 置信度（high/medium/low） |
| deepseek_target_pct | Numeric(5,4) | AI 建议目标仓位 |
| deepseek_reason | Text | AI 建议理由（结构化） |

| 改动项 | 文作 | 改动内容 |
|-------|------|---------|
| DDL | strategy_validation_log.py | 新增 3 列 |
| Prompt 重构 | scheduler.py L2762-2774 | 改为要求 JSON 输出：`{"action":"...", "target_pct":0.xx, "confidence":"...", "reason":"..."}` |
| API 扩展 | snapshot_router.py L868-939 | `_serialize_advice` 新增 3 字段返回 |
| 前端增强 | AIAnalysisPanel.tsx | AI 建议列新增置信度标签 + 目标仓位展示 |
| 一致性增强 | snapshot_router.py L948-958 | 一致性计算加入 target_pct 差值判断（项目书设计：差值 <5% = consistent） |

**风险**：中等。需要 prompt 工程确保 AI 输出可靠的结构化数据。
**收益**：用户能看到 AI 的置信度和具体仓位建议，对比更有意义。

### Phase 3: 完整 7 字段 + G7 一致性（7 列 DDL + 4 列 G7 + 前端完整版）

**目标**：完全对齐项目书设计

| 新增字段 | 类型 | 用途 |
|---------|------|------|
| deepseek_market_view | String(50) | AI 市场观点（bullish/neutral/bearish） |
| deepseek_risk_level | String(20) | AI 风险等级（high/medium/low） |
| deepseek_time_horizon | String(20) | AI 时间维度（short/medium/long） |
| deepseek_summary | Text | AI 摘要（区别于 deepseek_advice 全文） |
| advice_consistent | String(20) | 一致性状态（consistent/partial/conflict） |
| consistency_score | Numeric(5,2) | 一致性评分（0-100） |
| consistency_note | Text | 一致性说明 |
| conflict_fields | String(200) | 冲突字段列表 |

**风险**：中高。完整 prompt 重构 + 前端大改 + G7 后端计算逻辑。
**收益**：完全实现项目书设计，AI 成为真正的独立顾问。

---

## 六、7 个 DeepSeek 独立字段必要性排序

| 优先级 | 字段 | 必要性论证 | Phase |
|--------|------|-----------|-------|
| **P0** | action（AI 独立方向） | **最核心字段**。没有独立 action，一切都是假的。当前已存在列但被 override，Phase 1 去除 override 即可生效。 | Phase 1 |
| **P0** | confidence（AI 置信度） | 用户决策的关键依据。AI 说"减仓"但置信度 low vs 置信度 high，用户的应对完全不同。也是一致性评分的输入。 | Phase 2 |
| **P1** | target_pct（AI 目标仓位） | 一致性分析的核心输入（项目书设计：action 一致 + target_pct 差值 <5% = consistent）。没有这个字段，一致性只能判断方向不能判断幅度。 | Phase 2 |
| **P1** | reason / summary（AI 理由） | 用户需要知道 AI 为什么给出不同建议。当前 deepseek_advice 全文已包含理由，但结构化 reason 更便于对比和回验分析。 | Phase 2 |
| **P2** | market_view（AI 市场观点） | 提供宏观上下文，帮助用户理解 AI 建议的背景。但与 action 的相关性较弱，非决策必需。 | Phase 3 |
| **P2** | risk_level（AI 风险等级） | 与系统 Gate 体系有重叠。系统的 Gate 已经提供了结构化风控，AI 的 risk_level 是补充视角。 | Phase 3 |
| **P3** | time_horizon（AI 时间维度） | 对基金投资有一定参考价值，但基金本身是中长期投资品，时间维度的区分度有限。锦上添花。 | Phase 3 |

**核心判断**：action + confidence + target_pct 是"独立顾问"的最低可行集（MVDP）。这 3 个字段让用户能做出有意义的对比决策。其余 4 个字段是增强体验。

---

## 七、产品问题回答

### 7.1 方案B是否完整对齐项目书设计？

**不完整，对齐度约 54%**。方案B 的 7 个字段覆盖了项目书 G6 的 7/9 字段（缺 deepseek_advice 全文和 deepseek_reason），但完全未覆盖 G7 的 4 个一致性分析字段。方案B 的"结构化对比"隐含需要一致性分析，但未设计其存储和计算方案。

### 7.2 "系统 vs AI 双列对比"在产品层面是否合理？

**合理，但需要配套决策框架**。双列对比的核心价值是提供"第二意见"，类似医疗诊断中的第二诊疗意见。但两个建议打架时，产品必须提供决策辅助：

1. **数据驱动**：展示双方历史准确率（系统准确率 vs AI 准确率），让数据说话
2. **权重提示**：系统建议有 Gate 风控 + 14 因子引擎支撑，AI 建议有宏观视角 + 模式识别能力。conflict 时提示"系统建议侧重技术面风控，AI 建议侧重宏观判断"
3. **默认行为**：当 conflict 时，默认遵循系统建议（因为有 Gate 风控），AI 建议作为"风险提示"
4. **用户记录**：记录用户最终选择了谁的建议，用于后续优化权重

### 7.3 独立顾问模式下，AI 的建议是否需要明确标注"仅供参考"？

**必须标注**。三个理由：

1. **法律/合规**：AI 给出投资方向建议，即使标注"仅供参考"，也比无标注安全得多
2. **用户预期管理**：翻译器模式下 AI 只是复述系统，不需要免责；独立顾问模式下 AI 有独立判断，用户需要明确知道这是"建议"不是"指令"
3. **信任分层**：系统建议 = 执行层（有 Gate 风控），AI 建议 = 参考层（宏观视角补充）。标注"仅供参考"建立这个分层

**建议在前端 AI 建议列底部添加**："AI 建议仅供参考，最终决策请结合系统 Gate 风控综合判断"

### 7.4 是否有更简单的分阶段实施路径？

**有，见第五节**。核心思路：

- **Phase 1（零 DDL）**：只删 override 逻辑 + 改 prompt 让 AI 给独立判断。一致性分析自动生效，T+1 回验 bug 自动修复。**这是 ROI 最高的改动**。
- **Phase 2（3 列 DDL）**：加 confidence + target_pct + reason。让对比有意义。
- **Phase 3（7 列 DDL）**：补全剩余字段 + G7 一致性。完全对齐项目书。

### 7.5 7 层改造的优先级排序建议

见第六节。核心排序：action (P0) > confidence (P0) > target_pct (P1) > reason/summary (P1) > market_view (P2) > risk_level (P2) > time_horizon (P3)。

**可并行的改造**：
- Phase 1 的"去 override"和"改 prompt"可并行（不同文件/不同逻辑）
- Phase 2 的"DDL"和"前端增强"可并行（后端先加列，前端同时开发）
- Phase 3 的"4 列 G7"和"4 列 DeepSeek 增强字段"可并行

**不可并行的改造**：
- Phase 1 必须先于 Phase 2（Phase 2 依赖独立 action 生效）
- Prompt 重构必须先于前端展示（前端展示的字段依赖 prompt 输出）

---

## 八、总结与建议

### 8.1 方案B 可行性判断

**可行，但需分阶段实施**。一次性 11 列 DDL + prompt 重构 + 前端重构风险过高，推荐 3 阶段渐进。

### 8.2 最高优先级行动

**立即执行 Phase 1（零 DDL，纯代码改动）**：
1. 删除 scheduler.py 中的 override 逻辑（L2838-2856）
2. 修改 prompt，从"复述系统建议"改为"给出独立判断"
3. 验证一致性横条是否显示真实状态
4. 验证 T+1 回验是否测 AI 真实准确率

这一步 **零 DDL、零前端改动**，但能让整个双列对比系统从"假对比"变为"真对比"，ROI 最高。

### 8.3 关键风险提醒

1. **用户信任风险是最大风险**。AI 独立后可能与系统频繁冲突，如果 AI 准确率不如系统，用户会对整个系统失去信任。建议 Phase 1 上线后观察 2-4 周，统计 AI vs 系统准确率，再决定是否进入 Phase 2。

2. **数据断层不可避免**。翻译器模式的历史数据无法用于 AI 准确率分析。建议在 Phase 1 上线日做一个明确的数据分界点标记。

3. **Prompt 工程是关键**。从"翻译"到"独立顾问"不是简单改几行 prompt，而是需要重新设计 AI 的角色定位、输入数据范围、输出格式约束。建议 Phase 1 先用最小 prompt 改动验证可行性，Phase 2 再做完整 prompt 重构。

### 8.4 对方案B设计的补充建议

方案B 应补充以下设计要素：

1. **G7 一致性分析字段**（4 列）：这是双列对比的配套存储，不能省略
2. **数据模式标记**：新增列或复用 ext_text1 标记"translator_mode" vs "independent_mode"
3. **AI 准确率独立统计**：validation-stats API 应分别返回系统准确率和 AI 准确率
4. **前端免责声明**：AI 建议列添加"仅供参考"标注
5. **冲突决策提示**：conflict 状态下提供决策权重提示

---

*报告结束*
