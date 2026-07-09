# 方案B（独立顾问模式）代码变更点映射与风险评估报告

**日期**：2026-07-09  
**分析师**：gstack-investigator  
**任务性质**：纯研究（严禁修改任何文件）  
**范围**：映射方案B所需的全部代码变更点、依赖关系、隐藏风险，并评估结构化输出可行性

---

## 目录

1. [V2阶段精读分析（scheduler.py L2527-2846）](#1-v2阶段精读分析)
2. [T+1回验精读分析（scheduler.py L2883-3070）](#2-t1回验精读分析)
3. [数据模型精读分析（strategy_validation_log.py）](#3-数据模型精读分析)
4. [前端精读分析（AIAnalysisPanel.tsx）](#4-前端精读分析)
5. [API层精读分析（snapshot_router.py）](#5-api层精读分析)
6. [完整变更点矩阵](#6-完整变更点矩阵)
7. [T+1 Bug精确分析与修复方案](#7-t1-bug精确分析与修复方案)
8. [结构化输出可行性评估](#8-结构化输出可行性评估)
9. [隐藏依赖与风险清单](#9-隐藏依赖与风险清单)
10. [推荐实施顺序与依赖关系图](#10-推荐实施顺序与依赖关系图)

---

## 1. V2阶段精读分析

### 1.1 当前prompt喂给DeepSeek的数据（段1-段5）

**system_prompt（L2630-2649）**：定义角色为"基金投资策略分析师"，8条规则强制模型做翻译器：
- 规则1-3：闸门优先级、Gate触发提示、方向限定加仓/持有/减仓
- 规则4：回复500-2000字，必须包含操作方向
- 规则5：**【强制首行格式】** 操作方向必须等于系统建议方向，金额/仓位/市值必须等于系统推导值
- 规则6-8：5问分析为补充、全文方向一致性、偏差提示限制

**user_parts 各段内容**：

| 段 | 行号 | 内容 | 关键数据 |
|----|------|------|---------|
| 段1 | L2653-2670 | 今日预演数据 | fund_code, fund_name, gszzl, preview_score, preview_signal, preview_confidence, elasticity, score_delta, Gate-1/2状态, overall_status |
| 段2 | L2672-2682 | 市场上下文 | 大盘涨跌幅, 板块涨跌幅, 浮盈亏%, 成本净值 |
| 段3 | L2684-2695 | 历史回验 | 近30天信号/建议/Gate准确率（可能为"暂无历史数据"） |
| 段4 | L2697-2698 | 系统建议参考 | system_advice_text 全文 |
| 段4.5 | L2700-2760 | 系统已推导金额区块 | **核心约束区**：当前持仓市值/占比、目标仓位、系统总资产、系统建议方向、系统推导建议金额。标注"请勿修改任何数字，仅供翻译" |
| 段5 | L2762-2774 | 回复结构要求 | 第一步复述首行（不得改数字），第二步5问策略分析 |

### 1.2 方案B需要改prompt的哪些部分？改成什么样？

| prompt部分 | 当前内容 | 方案B改动 | 改动行号 |
|-----------|---------|----------|---------|
| system_prompt 规则3 | "建议方向只能是：加仓/持有/减仓" | 保留方向枚举，但去掉"必须等于系统建议方向"约束 | L2635 |
| system_prompt 规则5 | 首行格式强制=系统方向+系统金额 | **删除或重写**：改为要求输出JSON格式，含7个字段 | L2637-2641 |
| system_prompt 规则6-8 | 全文方向一致性、偏差提示限制 | **删除规则7-8**（不再需要，因为AI有独立方向）；规则6改为"分析部分为JSON之后的自然语言补充" | L2643-2648 |
| 段4.5 | "仅供翻译，请勿修改任何数字" | **改为"系统推导参考"**：仍提供系统金额作为参考，但AI可以给出不同的target_pct | L2752-2760 |
| 段5 | "复述首行+5问分析" | **改为"输出JSON+分析说明"**：第一步输出7字段JSON，第二步自然语言分析 | L2762-2774 |

**方案B prompt 新结构建议**：

```
system_prompt:
  "你是基金投资策略独立顾问。基于系统预演数据，独立给出投资建议。
   输出格式要求：
   1. 第一行必须是一个合法JSON对象，包含以下7个字段：
      {"action": "increase|hold|decrease",
       "target_pct": 0.0-1.0,
       "confidence": 1-5,
       "market_view": "bullish|neutral|bearish",
       "risk_level": "low|medium|high",
       "time_horizon": "short|medium|long",
       "summary": "一句话建议摘要"}
   2. JSON之后可以附加详细分析说明（500-2000字）。
   3. 你的action可以与系统建议方向不同，但需在分析中说明理由。
   4. target_pct是你建议的目标仓位比例，可以与系统不同。"

user_parts:
  段1-段4: 保持不变（预演数据/市场上下文/历史回验/系统建议参考）
  段4.5: 改为"【系统推导参考（仅供参考，你可以给出不同建议）】"
  段5: 改为"请先输出JSON建议，然后附上分析说明"
```

### 1.3 结构化JSON输出可行性

**当前状态**：prompt要求自由文本，首行格式为 `【操作方向】{加仓/持有/减仓} | 当前市值¥X | 目标仓位Y% | 建议金额≈¥Z`。代码通过首行字符串扫描解析action（L2831-2836）。

**改为JSON的风险**：

| 风险项 | 严重度 | 说明 |
|--------|--------|------|
| JSON解析失败 | **高** | DeepSeek可能输出不完整JSON、JSON前后有多余文本、字段名不一致 |
| 字段值不合规 | 中 | target_pct可能超出0-1范围，confidence可能不是整数 |
| 首行不再是action | 中 | 当前Fix B依赖首行扫描（L2831），改JSON后解析逻辑必须同步改 |
| max_tokens=2000可能不够 | 低 | JSON+分析可能超2000 token，但当前也是2000，影响不大 |
| temperature=0.3 | 低 | 低温度有助于稳定JSON输出，当前配置可接受 |

**结论**：可行，但必须配fallback策略（详见第8节）。

### 1.4 action override机制在方案B下如何改？

**当前机制（L2830-2856）**：
```python
# L2831-2836: 从首行解析advice_action
first_line = ai_response.strip().split("\n")[0]
advice_action = "hold"
if "加仓" in first_line: advice_action = "increase"
elif "减仓" in first_line: advice_action = "decrease"

# L2838-2856: 强制override为系统action
system_action_code = _action_cn_to_code.get(system_action, "hold")
final_action = advice_action
if system_action_code != advice_action:
    final_action = system_action_code  # 强制采用系统方向
    action_mismatch = True
    ai_response = override_note + ai_response  # 插入override标注
```

**方案B改动**：

| 项目 | 当前 | 方案B |
|------|------|-------|
| action来源 | 系统强制override | **AI独立给出，不override** |
| deepseek_advice_action | 存储 final_action（=系统action） | **存储AI的原始action** |
| override标注 | 插入到ai_response前 | **删除**，不再override |
| ext_text1 | 存 `{"raw_action": "...", "flag": "model_mismatch"}` | **可改为存AI的完整JSON原始响应**或废弃 |
| action_mismatch | 标记不一致 | **保留为一致性分析输入**，但不强制修改 |

**关键改动行号**：L2830-2856 整体重写，L2866-2867 的DB写入改为存储AI原始action。

---

## 2. T+1回验精读分析

### 2.1 T+1 Bug的精确代码位置和根因

**Bug位置**：`scheduler.py` L3061-3070

```python
# 11. DeepSeek准确度
deepseek_advice_correct = None
if record.deepseek_advice_action:          # L3063: 读取的是deepseek_advice_action
    ds_action = record.deepseek_advice_action  # L3064
    if ds_action == "increase":
        deepseek_advice_correct = 1 if actual_trend == "up" else 0
    elif ds_action == "decrease":
        deepseek_advice_correct = 1 if actual_trend == "down" else 0
    else:
        deepseek_advice_correct = 1 if actual_trend == "flat" else 0
```

**根因**：`record.deepseek_advice_action` 存储的是 **override后的 final_action**（见L2867: `db_record.deepseek_advice_action = final_action`），而非AI模型原始解析的 action。

**证据链**：
1. L2841: `final_action = advice_action` （初始赋值）
2. L2843-2844: `if system_action_code != advice_action: final_action = system_action_code` （override）
3. L2867: `db_record.deepseek_advice_action = final_action` （写入override后的值）
4. L3063-3064: T+1回验读取 `record.deepseek_advice_action` → 得到的是系统action而非AI action

**后果**：`deepseek_advice_correct` 实际计算的是 **系统建议的准确率**，而非AI建议的准确率。AI建议准确率指标完全无效。

### 2.2 方案B下T+1回验应该怎么算AI准确率？

**方案B下**：deepseek_advice_action 将存储AI的独立action（不再override），因此 L3061-3070 的代码逻辑本身是正确的——只要 override 机制被移除，`record.deepseek_advice_action` 就是AI的真实action。

**但需要增强**：
- 当前只有 0/1 两值（正确/错误），方案B可以考虑引入 confidence 加权
- hold 的判定逻辑（L3070: `flat`才算正确）可能过于严格，建议引入 0.5 部分正确

**方案B T+1回验增强建议**：
```python
# 方案B: 使用AI独立action计算准确率（override已移除，deepseek_advice_action即为AI原始action）
if record.deepseek_advice_action:
    ds_action = record.deepseek_advice_action
    if ds_action == "increase":
        deepseek_advice_correct = 1 if actual_trend == "up" else 0
    elif ds_action == "decrease":
        deepseek_advice_correct = 1 if actual_trend == "down" else 0
    else:  # hold
        deepseek_advice_correct = 1 if actual_trend == "flat" else 0
    # 可选：引入AI confidence加权
    # if record.deepseek_advice_confidence:
    #     deepseek_advice_correct_weighted = deepseek_advice_correct * record.deepseek_advice_confidence / 5
```

### 2.3 历史30天数据的deepseek_advice_correct怎么处理？

**当前状态**：历史数据中 `deepseek_advice_action` 存储的是 override 后的系统 action，因此 `deepseek_advice_correct` 实际反映的是系统准确率，不是AI准确率。

**处理方案**：

| 方案 | 操作 | 优点 | 缺点 |
|------|------|------|------|
| A. 标记废弃 | 将历史记录的 `deepseek_advice_correct` 设为 NULL 或新增标记列 | 简单、不丢数据 | 丢失历史基线 |
| B. 重算 | 用系统action重算（因为历史deepseek_advice_action=系统action），标记为"系统action准确率" | 数据可复用 | 语义混淆 |
| C. 原始action恢复 | 从 `ext_text1` 中的 `raw_action` 字段恢复AI原始action，重算 | 最准确 | 部分记录可能无ext_text1（只有mismatch时才写） |

**推荐方案C+fallback A**：
1. 先尝试从 `ext_text1` 提取 `raw_action`（仅 action_mismatch=True 的记录有此数据）
2. 对于无 ext_text1 的记录（action本来就一致），`deepseek_advice_action` 既是系统action也是AI action，可以直接用
3. 对于 DEEPSEEK_CALL_FAILED 的记录，保持 NULL
4. 新增 `deepseek_advice_correct_v2` 列存储重算值，保留原始值不覆盖

**但注意**：如果 action 没有不一致（即AI本来就同意系统方向），则 `deepseek_advice_action` 就是AI的真实action，历史数据中只有 `action_mismatch=True` 的记录才有问题。这部分可以通过 ext_text1 恢复。

---

## 3. 数据模型精读分析

### 3.1 当前schema vs 项目书设计的差异

**当前实际**（strategy_validation_log.py）：
- G6: 3列 — deepseek_advice (Text), deepseek_advice_action (String(20)), deepseek_advice_correct (Integer)
- G7: 6列（混在回验评分中）— validation_score, signal_accuracy, advice_accuracy, gate_accuracy, system_advice_text, advice_reason
- **无独立一致性分析列**

**项目书设计**：
- G6: 9列 — deepseek_advice, deepseek_action, deepseek_target_pct, deepseek_confidence, deepseek_reason, deepseek_market_view, deepseek_risk_level, deepseek_time_horizon, deepseek_summary
- G7: 4列 — advice_consistent, consistency_score, consistency_note, conflict_fields

**注意**：当前代码的组划分与项目书不同。当前代码把回验评分放在G7，项目书把一致性分析放在G7。实际列名也不同（当前用 `deepseek_advice_action`，项目书用 `deepseek_action`）。

### 3.2 方案B需要新增哪些列？

| 新列名 | 类型 | 可空 | 默认值 | 说明 | 对应JSON字段 |
|--------|------|------|--------|------|-------------|
| deepseek_advice_target_pct | Numeric(5,4) | Yes | NULL | AI建议目标仓位(0.0-1.0) | target_pct |
| deepseek_advice_confidence | Integer | Yes | NULL | AI置信度(1-5) | confidence |
| deepseek_advice_market_view | String(20) | Yes | NULL | AI市场观点(bullish/neutral/bearish) | market_view |
| deepseek_advice_risk_level | String(10) | Yes | NULL | AI风险等级(low/medium/high) | risk_level |
| deepseek_advice_time_horizon | String(10) | Yes | NULL | AI时间维度(short/medium/long) | time_horizon |
| deepseek_advice_summary | String(500) | Yes | NULL | AI建议摘要 | summary |
| advice_consistent | Integer | Yes | NULL | 系统vs AI方向一致性(1=一致 0=不一致) | G7一致性 |
| consistency_score | Numeric(5,2) | Yes | NULL | 一致性评分(0-100) | G7一致性 |
| consistency_note | String(200) | Yes | NULL | 一致性说明 | G7一致性 |
| conflict_fields | String(200) | Yes | NULL | 冲突字段列表(JSON) | G7一致性 |

**总计新增10列**（6列G6扩展 + 4列G7一致性分析）。

**对现有57列的影响**：
- 现有列不变，仅追加新列
- `deepseek_advice_action` 保留，但语义变化（从override后的action改为AI原始action）
- `deepseek_advice_correct` 保留，但语义修正（从系统action准确率改为AI原始action准确率）
- `ext_text1` 可废弃override标记用途，改为存储AI JSON原始响应

### 3.3 G7一致性分析的4列怎么算？

**算法逻辑**：

```python
# advice_consistent (Integer 0/1):
#   系统action == AI action → 1
#   否则 → 0

# consistency_score (Numeric 0-100):
#   action一致: 80分起步
#   target_pct偏差 < 5%: +10分
#   target_pct偏差 < 10%: +5分
#   action不一致但AI confidence <= 2: 30分（低置信度分歧影响小）
#   action不一致且AI confidence >= 4: 10分（高置信度分歧影响大）
#   action相反(increase vs decrease): 0分

# consistency_note (String):
#   一致: "系统与AI建议方向一致"
#   分歧: "系统建议加仓，AI建议减仓，AI置信度4星"
#   冲突: "系统与AI方向完全相反"

# conflict_fields (String, JSON数组):
#   ["action"] — 方向不同
#   ["action", "target_pct"] — 方向和仓位都不同
#   [] — 完全一致
```

**计算时机**：14:47 V2阶段，DeepSeek返回后立即计算，与G6同时写入。

### 3.4 新增列对现有57列的影响

**无影响**。所有新列都是 nullable，追加到表末尾即可。现有查询不受影响。但需要注意：
- `VALIDATION_CSV_COLUMNS`（snapshot_router.py L406-477）需要追加新列
- `_serialize_advice()` 函数（snapshot_router.py L868-939）需要序列化新列
- `_format_validation_value()` 函数（snapshot_router.py L480-533）需要格式化新列

---

## 4. 前端精读分析

### 4.1 前端期望的数据结构

**ValidationRecord 接口**（AIAnalysisPanel.tsx L19-87）：
当前已定义57个字段，与DB列一一对应。另有6个"阶段1元金额字段"（total_assets, current_position_pct, target_position_pct, suggested_amount, system_action），由后端实时计算。

**ApiResponse 接口**（L89-95）：
```typescript
interface ApiResponse {
  today: ValidationRecord | null;
  consistency: 'consistent' | 'partial' | 'conflict' | null;
  has_system_advice: boolean;
  has_deepseek_advice: boolean;
  backfill_history: ValidationRecord[];
}
```

### 4.2 方案B的7个新字段前端是否已有渲染逻辑？

**否，前端完全没有渲染以下字段**：
- target_pct（AI建议目标仓位）
- confidence（AI置信度）
- market_view（市场观点）
- risk_level（风险等级）
- time_horizon（时间维度）
- summary（建议摘要）

**当前前端渲染的AI字段**（L243-262）：
- `deepseek_advice_action` → 显示方向图标+标签
- `deepseekSuggestedAmount`（从首行正则提取，L170-173）→ 显示建议金额
- `deepseek_advice`（全文，L292-301）→ 显示在文本框

**需要新增的前端渲染**：

| 新字段 | 渲染位置 | 渲染方式 | 改动量 |
|--------|---------|---------|--------|
| AI target_pct | DeepSeek建议列 | 仓位百分比文本 | 小 |
| AI confidence | DeepSeek建议列 | 星级/进度条 | 小 |
| AI market_view | DeepSeek建议列 | 图标+文字(bullish=牛/neutral=中/bearish=熊) | 中 |
| AI risk_level | DeepSeek建议列 | 颜色标签(low=绿/medium=黄/high=红) | 小 |
| AI time_horizon | DeepSeek建议列 | 文字标签(短期/中期/长期) | 小 |
| AI summary | DeepSeek建议详情上方 | 摘要文本 | 小 |
| advice_consistent | 一致性横条区域 | 替换或增强当前consistency字段 | 中 |

**一致性横条改造**：
- 当前 `consistency` 由后端计算（snapshot_router.py L947-958），仅比较 actual_action vs deepseek_advice_action
- 方案B下应改为比较 system_action vs AI action（因为 actual_action 是T+1才回填的，当天可能为NULL）
- 前端CONSISTENCY_MAP（L109-113）和横条渲染（L267-276）无需大改，只需后端 consistency 计算逻辑改

**改动量评估**：中等。主要是 ValidationRecord 接口扩展 + DeepSeek建议列UI重构。

### 4.3 一致性横条的判定逻辑

**前端**（L109-113）：
```typescript
const CONSISTENCY_MAP = {
  consistent: { label: '一致', ... bar: 'bg-green-400' },
  partial: { label: '部分一致', ... bar: 'bg-amber-400' },
  conflict: { label: '分歧', ... bar: 'bg-red-400' },
};
```

**后端计算**（snapshot_router.py L947-958）：
```python
if today_data and today_data.get("actual_action") and today_data.get("deepseek_advice_action"):
    sys_action = today_data["actual_action"]
    ai_action = today_data["deepseek_advice_action"]
    if sys_action == ai_action:
        consistency = "consistent"
    elif (sys_action == "increase" and ai_action == "decrease") or \
         (sys_action == "decrease" and ai_action == "increase"):
        consistency = "conflict"
    else:
        consistency = "partial"
```

**方案B问题**：
1. 当前用 `actual_action` 比较，但 `actual_action` 是T+1才回填的（L3085: `db_record.actual_action = actual_action`），当天14:47时此字段为NULL → **当天一致性永远为NULL**
2. 应改用 `system_action`（实时计算的金额字段中已有，L938: `"system_action": amount_fields["system_action"]`）

**方案B修正**：
```python
# 改用 system_action（实时计算）而非 actual_action（T+1回填）
sys_action = today_data.get("system_action")  # 从amount_fields
ai_action = today_data.get("deepseek_advice_action")
```

但注意：`system_action` 是中文（"加仓"/"持有"/"减仓"），而 `deepseek_advice_action` 是英文（"increase"/"hold"/"decrease"），需要统一映射。

---

## 5. API层精读分析

### 5.1 validation-today 端点现状

**已实现**（snapshot_router.py L825-973）：
- 查询当天记录 + 最近3天回验记录
- `_compute_validation_amounts()` 实时算金额（L768-822）
- 一致性分析（L947-958，但有上述bug）
- `_serialize_advice()` 序列化所有字段（L868-939）

**方案B需要改的部分**：

| 函数/区域 | 行号 | 改动 |
|----------|------|------|
| `_serialize_advice()` | L868-939 | 追加序列化6个新G6字段 + 4个G7字段 |
| 一致性计算 | L947-958 | 改用system_action比较；增加consistency_score等计算 |
| `_compute_validation_amounts()` | L768-822 | 无需改（金额计算逻辑不变） |
| `VALIDATION_CSV_COLUMNS` | L406-477 | 追加10个新列 |
| `_format_validation_value()` | L480-533 | 追加新列格式化 |

### 5.2 其他API端点

- `validation-history`（L596-672）：需要追加新列到records序列化
- `validation-stats`（L675-761）：可以新增AI建议准确率统计（按AI原始action计算）
- `validation-download`（L536-593）：CSV列自动从VALIDATION_CSV_COLUMNS生成，追加即可

---

## 6. 完整变更点矩阵

### 6.1 变更点总览

| # | 文件 | 函数/区域 | 行号 | 改动描述 | 依赖 | 风险等级 |
|---|------|----------|------|---------|------|---------|
| 1 | scheduler.py | system_prompt构造 | L2630-2649 | 重写prompt：翻译器→独立顾问，要求JSON输出 | 无 | **高** |
| 2 | scheduler.py | user_parts段4.5 | L2752-2760 | 改文案："仅供翻译"→"仅供参考" | #1 | 中 |
| 3 | scheduler.py | user_parts段5 | L2762-2774 | 改回复结构要求：复述首行→输出JSON+分析 | #1 | 中 |
| 4 | scheduler.py | DeepSeek API body | L2789-2794 | 添加response_format参数（可选） | #1 | 中 |
| 5 | scheduler.py | action解析 | L2830-2836 | 从首行扫描改为JSON解析 | #1 | **高** |
| 6 | scheduler.py | action override | L2838-2856 | **删除override机制**，保留AI原始action | #5 | **高** |
| 7 | scheduler.py | DB写入 | L2858-2873 | 写入7个新G6字段+4个G7字段 | #5,#6,DDL | **高** |
| 8 | scheduler.py | T+1 deepseek_advice_correct | L3061-3070 | 语义已正确（因#6移除override），可选增强 | #6 | 低 |
| 9 | strategy_validation_log.py | G6/G7列定义 | L200-209后 | 追加10个新列定义 | 无 | 中 |
| 10 | snapshot_router.py | _serialize_advice() | L868-939 | 追加10个新字段序列化 | #9 | 中 |
| 11 | snapshot_router.py | 一致性计算 | L947-958 | 改用system_action比较+计算4个G7字段 | #7,#9 | **高** |
| 12 | snapshot_router.py | VALIDATION_CSV_COLUMNS | L406-477 | 追加10个新CSV列 | #9 | 低 |
| 13 | snapshot_router.py | _format_validation_value() | L480-533 | 追加新列格式化 | #9 | 低 |
| 14 | snapshot_router.py | validation-history records | L637-667 | 追加新字段 | #9 | 低 |
| 15 | AIAnalysisPanel.tsx | ValidationRecord接口 | L19-87 | 追加10个新字段定义 | #10 | 低 |
| 16 | AIAnalysisPanel.tsx | DeepSeek建议列UI | L243-262 | 重构：显示7个新字段 | #15 | 中 |
| 17 | AIAnalysisPanel.tsx | 一致性横条 | L267-276 | 可选增强：显示consistency_score | #11 | 低 |
| 18 | config.py | DEEPSEEK参数 | L301-305 | 可选：调整temperature/max_tokens | 无 | 低 |
| 19 | DDL/Migration | ALTER TABLE | N/A | 新增10列的DDL迁移脚本 | 无 | 中 |

### 6.2 变更依赖关系图

```
DDL迁移(#19) ──────────────────────────────────────┐
  │                                                │
  ▼                                                ▼
schema定义(#9) ──→ scheduler.py DB写入(#7)    API序列化(#10)
                    ↑                              │
                    │                              ├──→ CSV列(#12,#13)
  prompt改造(#1) ──┼──→ JSON解析(#5)              ├──→ validation-history(#14)
                    │      │                       │
                    │      ▼                       ▼
                    │  移除override(#6) ──→ T+1修正(#8)  前端接口(#15)
                    │      │                              │
                    │      ▼                              ▼
                    │  DB写入(#7) ──────────────→  前端UI(#16)
                    │                              │
                    │                              ▼
                    └──→ 段4.5改(#2) ──→ 段5改(#3)  一致性横条(#17)
                    
API参数(#4) ←── prompt改造(#1)
一致性计算(#11) ←── DB写入(#7), schema(#9)
config(#18) ←── 独立（可并行）
```

**关键路径**：DDL(#19) → schema(#9) → prompt(#1) → JSON解析(#5) → 移除override(#6) → DB写入(#7) → API序列化(#10) → 前端(#15,#16)

---

## 7. T+1 Bug精确分析与修复方案

### 7.1 Bug定义

**位置**：scheduler.py L3061-3070  
**现象**：`deepseek_advice_correct` 实际计算的是系统action的准确率，而非AI action的准确率  
**根因**：`record.deepseek_advice_action`（L3063-3064）读取的是 override 后的 `final_action`（L2867写入），而非AI模型原始解析的 `advice_action`

### 7.2 数据流追踪

```
V2阶段 (L2830-2867):
  ai_response = DeepSeek API response
  advice_action = parse_from_first_line(ai_response)   # AI原始action
  system_action_code = map(system_action)               # 系统action
  final_action = advice_action                          # 初始
  if system_action_code != advice_action:
      final_action = system_action_code                 # OVERRIDE!
  db_record.deepseek_advice_action = final_action       # 写入override后的值

V3阶段 (L3061-3070):
  ds_action = record.deepseek_advice_action             # 读到的是final_action(=系统action)
  deepseek_advice_correct = compare(ds_action, actual_trend)  # 实际比较的是系统action vs 实际趋势
```

### 7.3 影响范围

- **所有历史记录**的 `deepseek_advice_correct` 都是系统action准确率，不是AI准确率
- `validation-stats` API（L698: `func.avg(StrategyValidationLog.deepseek_advice_correct)`）返回的AI准确率统计是错误的
- 前端 T+1回验记录中的 `AI ✓/✗` 标记（AIAnalysisPanel.tsx L429-433）展示的也是错误数据

### 7.4 方案B修复方案

**方案B本身就修复了此bug**——因为方案B移除了override机制（变更点#6），`deepseek_advice_action` 将直接存储AI原始action，T+1回验代码（L3061-3070）无需修改即可正确计算AI准确率。

**但需注意**：
1. 历史数据的 `deepseek_advice_correct` 仍然是错误的，需要按2.3节方案处理
2. 对于 `action_mismatch=False` 的历史记录（AI本来就同意系统方向），`deepseek_advice_action` 既是系统action也是AI action，数据是正确的
3. 对于 `action_mismatch=True` 的历史记录，可以从 `ext_text1` 中的 `{"raw_action": "...", "flag": "model_mismatch"}` 恢复AI原始action并重算

### 7.5 历史数据修复SQL（参考）

```sql
-- 1. 查看受影响记录数
SELECT COUNT(*) FROM strategy_validation_log 
WHERE ext_text1 LIKE '%model_mismatch%' 
  AND deepseek_advice_correct IS NOT NULL;

-- 2. 从ext_text1恢复AI原始action并重算（需在Python中执行，因JSON解析+趋势比较逻辑复杂）
-- 不建议纯SQL，建议写一次性脚本

-- 3. 标记历史数据为"系统action准确率"（保守方案）
-- ALTER TABLE strategy_validation_log ADD COLUMN deepseek_correct_version VARCHAR(10) DEFAULT 'v1';
-- UPDATE strategy_validation_log SET deepseek_correct_version = 'v1' WHERE deepseek_advice_correct IS NOT NULL;
```

---

## 8. 结构化输出可行性评估

### 8.1 DeepSeek能否可靠输出JSON？

**有利因素**：
- 模型为 `deepseek-v4-flash`，支持JSON模式
- temperature=0.3（低温度，输出稳定）
- 当前prompt已经有严格的首行格式要求，模型遵守度较高

**风险因素**：
- DeepSeek API 不保证100%输出合法JSON（即使使用 response_format）
- 模型可能在JSON前后添加解释文字
- 字段值可能不符合预期格式（如 target_pct 写成 "50%" 而非 0.5）

### 8.2 推荐的API调用参数变更

| 参数 | 当前值 | 建议值 | 理由 |
|------|--------|--------|------|
| temperature | 0.3 | **0.1-0.2** | 更低温度提高JSON格式稳定性 |
| max_tokens | 2000 | **3000** | JSON+分析可能需要更多token |
| response_format | 未设置 | **{"type": "json_object"}** | 强制JSON输出（如果API支持） |
| DEEPSEEK_TIMEOUT | 60 | 60 | 保持不变 |

**注意**：`response_format: {"type": "json_object"}` 是OpenAI兼容API的参数，DeepSeek API是否支持需要验证。如果不支持，则依赖prompt约束 + 代码层fallback。

### 8.3 JSON解析fallback策略

```python
import json
import re

def parse_deepseek_json(response: str) -> dict | None:
    """解析DeepSeek返回的JSON，带多层fallback"""
    
    # 尝试1：直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # 尝试2：提取第一个JSON对象（应对JSON前后有文本的情况）
    json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # 尝试3：提取 ```json ... ``` 代码块
    code_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试4：从首行提取action（兼容旧格式）
    first_line = response.strip().split("\n")[0]
    action = "hold"
    if "加仓" in first_line or "increase" in first_line.lower():
        action = "increase"
    elif "减仓" in first_line or "decrease" in first_line.lower():
        action = "decrease"
    return {
        "action": action,
        "target_pct": None,
        "confidence": None,
        "market_view": None,
        "risk_level": None,
        "time_horizon": None,
        "summary": None,
        "_parse_fallback": True,  # 标记使用了fallback
    }
```

### 8.4 字段验证与默认值

```python
def validate_deepseek_fields(parsed: dict) -> dict:
    """验证并填充默认值"""
    # action: 必须是 increase/hold/decrease
    action = parsed.get("action", "hold")
    if action not in ("increase", "hold", "decrease"):
        # 尝试中文映射
        cn_map = {"加仓": "increase", "持有": "hold", "减仓": "decrease"}
        action = cn_map.get(action, "hold")
    
    # target_pct: 0.0-1.0
    target_pct = parsed.get("target_pct")
    if target_pct is not None:
        try:
            target_pct = float(target_pct)
            if target_pct > 1:  # 可能是百分比形式(如50)
                target_pct = target_pct / 100
            target_pct = max(0.0, min(1.0, target_pct))
        except (ValueError, TypeError):
            target_pct = None
    
    # confidence: 1-5
    confidence = parsed.get("confidence")
    if confidence is not None:
        try:
            confidence = int(confidence)
            confidence = max(1, min(5, confidence))
        except (ValueError, TypeError):
            confidence = None
    
    # market_view, risk_level, time_horizon: 枚举验证
    market_view = parsed.get("market_view")
    if market_view not in ("bullish", "neutral", "bearish"):
        market_view = None
    
    risk_level = parsed.get("risk_level")
    if risk_level not in ("low", "medium", "high"):
        risk_level = None
    
    time_horizon = parsed.get("time_horizon")
    if time_horizon not in ("short", "medium", "long"):
        time_horizon = None
    
    summary = parsed.get("summary")
    if summary and len(summary) > 500:
        summary = summary[:500]
    
    return {
        "action": action,
        "target_pct": target_pct,
        "confidence": confidence,
        "market_view": market_view,
        "risk_level": risk_level,
        "time_horizon": time_horizon,
        "summary": summary,
    }
```

### 8.5 可行性结论

| 维度 | 评估 | 置信度 |
|------|------|--------|
| JSON输出可靠性 | 中高（低温度+prompt约束+fallback） | 80% |
| 字段值合规性 | 中（需验证层） | 70% |
| 解析fallback覆盖度 | 高（4层fallback） | 95% |
| 对现有流程的影响 | 中（解析逻辑+DB写入需改） | — |
| 总体可行性 | **可行，但需严格的解析+验证+fallback** | 75% |

---

## 9. 隐藏依赖与风险清单

### 9.1 隐藏依赖

| # | 依赖描述 | 涉及组件 | 严重度 |
|---|---------|---------|--------|
| H1 | **改prompt格式→T+1解析也受影响** | 当前T+1不解析prompt（只读DB字段），但如果JSON解析失败且fallback用了首行扫描，需要确保fallback输出的action也被正确存储 | 中 |
| H2 | **移除override→一致性计算逻辑变了** | snapshot_router.py L947-958 当前比较 actual_action vs deepseek_advice_action。移除override后，deepseek_advice_action变为AI原始action，但actual_action仍是T+1才回填。当天一致性比较应改用system_action | **高** |
| H3 | **system_action是中文，deepseek_advice_action是英文** | 一致性计算需要统一映射。当前 `_compute_validation_amounts()` 返回的 system_action 是中文（"加仓"/"持有"/"减仓"），而 deepseek_advice_action 是英文（"increase"/"hold"/"decrease"） | **高** |
| H4 | **ext_text1列被当前override机制占用** | L2870-2872: `ext_text1` 存了 `{"raw_action": "...", "flag": "model_mismatch"}`。方案B如果要用 ext_text1 存其他数据，需先清理历史用法 | 中 |
| H5 | **deepseekSuggestedAmount前端正则提取** | AIAnalysisPanel.tsx L170-173 从 deepseek_advice 首行正则提取建议金额。改JSON后首行是JSON，正则会失败。需要改为从JSON字段或新列提取 | **高** |
| H6 | **历史准确率查询影响prompt** | L2593-2615: V2阶段查询近30天历史准确率（signal_accuracy, advice_accuracy, gate_accuracy）喂给prompt。这些值当前不受override bug影响（不是deepseek_advice_correct），但如果重算历史数据，avg值会变 | 低 |
| H7 | **validation-stats API的avg_deepseek_accuracy** | snapshot_router.py L698: `func.avg(StrategyValidationLog.deepseek_advice_correct)` 返回的是错误的历史值。方案B修复后新数据正确，但混合历史数据会拉偏统计 | 中 |
| H8 | **DEEPSEEK_TIMEOUT从10改为60** | config.py 中 DEEPSEEK_TIMEOUT 已从10改为60（对比 .bak 文件），但项目书仍写10s。方案B如果输出JSON，响应可能更长，60s合理 | 低 |
| H9 | **JSON输出可能触发content filter** | DeepSeek API可能对某些JSON内容触发安全过滤，导致返回截断。fallback需要处理截断JSON | 低 |
| H10 | **并发写DB** | V2阶段逐基金调用DeepSeek（L2621 for循环），每个基金单独开session写DB。如果JSON解析+验证增加了处理时间，整体V2阶段耗时会增加 | 低 |

### 9.2 风险等级汇总

| 风险等级 | 数量 | 关键风险 |
|---------|------|---------|
| **高** | 4 | H2(一致性计算), H3(中英文映射), H5(前端金额提取), 变更#1(prompt重写) |
| **中** | 5 | H1, H4, H7, 变更#2,#3,#5 |
| **低** | 4 | H6, H8, H9, H10 |

---

## 10. 推荐实施顺序与依赖关系图

### 10.1 实施阶段

```
阶段0: DDL迁移（前置）
  │
  ├──→ 19. ALTER TABLE 新增10列
  │
  ▼
阶段1: 后端核心（prompt + 解析 + DB写入）
  │
  ├──→ 9. strategy_validation_log.py 新增列定义
  ├──→ 1. system_prompt 重写（翻译器→独立顾问）
  ├──→ 2. 段4.5 改文案
  ├──→ 3. 段5 改回复结构
  ├──→ 4. API body 添加response_format（可选）
  ├──→ 5. action解析 改为JSON解析+fallback
  ├──→ 6. 移除override机制
  └──→ 7. DB写入 新增10个字段
  │
  ▼
阶段2: 一致性计算 + T+1修正
  │
  ├──→ 11. snapshot_router.py 一致性计算改用system_action
  ├──→ 8. T+1 deepseek_advice_correct（语义已自动修正）
  └──→ 历史数据修复脚本（从ext_text1恢复raw_action）
  │
  ▼
阶段3: API序列化 + CSV
  │
  ├──→ 10. _serialize_advice() 追加新字段
  ├──→ 12. VALIDATION_CSV_COLUMNS 追加新列
  ├──→ 13. _format_validation_value() 追加格式化
  └──→ 14. validation-history records 追加新字段
  │
  ▼
阶段4: 前端
  │
  ├──→ 15. ValidationRecord接口扩展
  ├──→ 16. DeepSeek建议列UI重构（7字段展示）
  └──→ 17. 一致性横条增强（可选）
  │
  ▼
阶段5: 配置 + 测试
  │
  ├──→ 18. config.py 参数调优（可选）
  └──→ 端到端测试
```

### 10.2 关键约束

1. **阶段0必须最先执行**：DDL迁移是所有后续改动的基础
2. **阶段1内#1→#5→#6→#7是关键路径**：prompt改了才能改解析，解析改了才能移除override，移除了override才能正确写DB
3. **阶段2的#11依赖阶段1的#7**：一致性计算需要G7字段已写入DB
4. **阶段3依赖阶段1的DDL**：序列化新字段需要列已存在
5. **阶段4依赖阶段3**：前端接口字段需要后端API已返回
6. **历史数据修复可以在阶段2之后任意时间执行**，不影响新数据流程

### 10.3 最小可行方案（MVP）

如果资源有限，可以分两批实施：

**批次1（核心功能）**：
- #19 DDL + #9 schema
- #1 prompt + #5 JSON解析 + #6 移除override + #7 DB写入
- #11 一致性计算修正
- #10 API序列化
- #15 前端接口 + #16 前端UI（基本展示）

**批次2（增强）**：
- #2,#3 prompt细节优化
- #4 response_format参数
- #8 T+1增强（confidence加权）
- #12,#13 CSV列
- #14 validation-history
- #17 一致性横条增强
- #18 config调优
- 历史数据修复脚本

---

## 附录A：当前代码关键行号快速索引

| 功能 | 文件 | 行号 |
|------|------|------|
| V1预演持久化入口 | scheduler.py | L1996 (`_run_validation_persist`) |
| Fix A: yesterday_nav从fund_nav直取 | scheduler.py | L2113-2131 |
| V2 DeepSeek建议入口 | scheduler.py | L2553 (`_run_validation_deepseek_advice`) |
| system_prompt构造 | scheduler.py | L2630-2649 |
| user_parts段1(预演数据) | scheduler.py | L2653-2670 |
| user_parts段2(市场上下文) | scheduler.py | L2672-2682 |
| user_parts段3(历史回验) | scheduler.py | L2684-2695 |
| user_parts段4(系统建议) | scheduler.py | L2697-2698 |
| user_parts段4.5(金额区块) | scheduler.py | L2700-2760 |
| user_parts段5(回复结构) | scheduler.py | L2762-2774 |
| DeepSeek API调用 | scheduler.py | L2784-2811 |
| action首行解析(Fix B) | scheduler.py | L2830-2836 |
| action override机制 | scheduler.py | L2838-2856 |
| DB写入(deepseek_advice) | scheduler.py | L2858-2873 |
| V3 T+1回验入口 | scheduler.py | L2888 (`_run_validation_backfill`) |
| T+1 deepseek_advice_correct(bug) | scheduler.py | L3061-3070 |
| T+1 DB UPDATE | scheduler.py | L3072-3093 |
| G6列定义(3列) | strategy_validation_log.py | L200-209 |
| ValidationRecord接口 | AIAnalysisPanel.tsx | L19-87 |
| 前端金额正则提取 | AIAnalysisPanel.tsx | L170-173 |
| 前端一致性横条 | AIAnalysisPanel.tsx | L267-276 |
| _compute_validation_amounts() | snapshot_router.py | L768-822 |
| validation-today端点 | snapshot_router.py | L825-973 |
| 一致性计算(bug) | snapshot_router.py | L947-958 |
| _serialize_advice() | snapshot_router.py | L868-939 |
| DeepSeek配置 | config.py | L301-305 |

---

## 附录B：DeepSeek API当前配置

| 配置项 | 值 | 位置 |
|--------|---|------|
| DEEPSEEK_MODEL | `deepseek-v4-flash` | config.py L301 |
| DEEPSEEK_TIMEOUT | 60秒 | config.py L302 |
| DEEPSEEK_MAX_TOKENS | 2000 | config.py L303 |
| DEEPSEEK_MAX_RETRIES | 1 | config.py L304 |
| DEEPSEEK_TEMPERATURE | 0.3 | config.py L305 |
| response_format | 未设置 | scheduler.py L2789-2794 |

---

**报告结束。**
