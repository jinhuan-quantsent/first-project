# 方案B（DeepSeek独立顾问模式）全面验证报告

**日期**：2026-07-09
**场景**：全流程交付验证（产品设计 + 代码可行性 + 安全审计）
**参与成员**：产品评审员 + 调查员 + 安全官

---

## 📌 TL;DR（执行摘要）

- **整体结论**：🟡 有条件通过 — 方案B技术可行，DB迁移风险极低（18行表，Instant DDL <1ms），但发现2个Critical级安全问题（生产环境AUTH_DISABLED=true + API无鉴权）必须在方案B上线前修复
- **关键修正**：之前认为"4个API全未实现"是错的 — 4个API全部已实现且前端已联通，方案B工作量大幅降低
- **推荐路径**：3阶段渐进实施 — Phase 0（安全紧急修复）→ Phase 1（零DDL去override）→ Phase 2（3列DDL+JSON输出）→ Phase 3（全量对齐项目书）
- **最大风险**：不是代码改动，而是Prompt重写质量和用户信任（AI与系统建议冲突时用户听谁的）

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| Go / No-Go | 🟡 条件 Go — 先修2个Critical安全问题 |
| 严重度分布 | 🔴 2（安全）/ 🟠 4（代码+安全）/ 🟡 6（产品+安全+代码）/ 🟢 3 |
| 关键行动项 | 10 条 |
| 建议负责人 | 安全官（P0鉴权）→ 主理人（Phase 1 去override）→ 调查员（Phase 2 JSON解析） |
| DB迁移风险 | 🟢 极低 — 18行表，MySQL 8.0 Instant ADD COLUMN，<1ms，无需pt-osc |
| 方案B对齐项目书 | ~54% → Phase 3后100% |
| 预估工作量 | Phase 1: ~1天 / Phase 2: ~3天 / Phase 3: ~4天 |

---

## 1. 各成员核心结论

### 🔍 产品评审员（产品评审）
- **核心判断**：方案B与项目书对齐度约54%。7个独立字段覆盖了G6的7/9，但完全未覆盖G7的4列一致性分析字段——这是方案B的最大设计缺口。一致性分析的双列对比配套存储不能省略
- **关键建议**：推荐3阶段渐进实施。Phase 1（零DDL，只删override+改prompt）ROI最高——双列对比从"假对比"立即变为"真对比"，T+1回验bug自动修复。AI建议必须标注"仅供参考"。Phase 1上线后观察2-4周AI vs 系统准确率再决定是否进入Phase 2
- **重要修正**：4个validation API全部已实现（snapshot_router.py），前端已联通。问题不是API缺失，而是返回数据结构简化（只有3个DeepSeek字段）+ 一致性计算因override永远返回"consistent"（假对比）

### 🔧 调查员（代码可行性与变更映射）
- **核心判断**：方案B涉及19个变更点、5个文件，技术可行。T+1 bug精确根因已确认（L3061-3070用override后的action测AI准确率）。结构化JSON输出可行性75%，需配4层fallback（直接解析→正则提取→代码块提取→首行扫描）
- **关键建议**：4个高风险隐藏依赖必须同步处理：H2（一致性计算需改用system_action而非actual_action）、H3（system_action中文vs deepseek_advice_action英文需映射）、H5（前端正则提取金额L170-173会因JSON格式失效）、Prompt重写是最高风险点。关键路径：DDL→schema→prompt→JSON解析→移除override→DB写入→API→前端
- **T+1 bug自动修复**：方案B移除override后，deepseek_advice_action即为AI原始action，L3061-3070代码逻辑无需修改即可正确计算AI准确率

### 🛡️ 安全官（OWASP+STRIDE审计）
- **核心判断**：DB迁移风险极低（18行表，MySQL 8.0.46 Instant ADD COLUMN <1ms，无需pt-osc/gh-ost）。但发现2个Critical级安全问题：生产环境AUTH_DISABLED=true导致全部API无鉴权，任何人可curl下载全量策略验证数据
- **关键建议**：方案B上线前必须完成7项修复（设AUTH_DISABLED=false、4个端点加鉴权、CSV注入防护、Feature Flag、JSON Schema校验、字段白名单、保留Gate安全边界）。建议引入DEEPSEEK_MODE=translator|independent Feature Flag，回滚仅需2分钟（改.env+重启）。OWASP评分D级（因AUTH_DISABLED+无鉴权）
- **重要发现**：历史18行数据deepseek_advice_correct全为NULL（T+1未执行），ext_text1全为NULL（无mismatch）——意味着历史数据问题目前影响为零，但必须在首个T+1回验（明天17:35）前修复

---

## 2. 综合审查发现（去重合并后按严重度排序）

| # | 严重度 | 类别 | 位置 | 问题描述 | 建议 | 来源 |
|---|--------|------|------|---------|------|------|
| 1 | 🔴 | 安全 | ECS .env | AUTH_DISABLED=true，生产环境认证完全禁用，任何人可curl下载全量策略验证数据含持仓市值 | 立即设AUTH_DISABLED=false，确保SUPABASE_JWT_SECRET已配置 | 安全官 |
| 2 | 🔴 | 安全 | snapshot_router.py L536-973 | 4个validation API端点无Depends(get_current_user)鉴权依赖，即使修复AUTH_DISABLED仍开放 | 为所有4个端点添加user_id: str = Depends(get_current_user)，按user_id过滤 | 安全官 |
| 3 | 🟠 | 代码 | scheduler.py L3061-3070 | T+1回验bug：deepseek_advice_correct用override后的action（=系统action），测的是系统准确率不是AI准确率 | 方案B移除override后自动修复；历史18行correct全为NULL（T+1未执行），影响为零 | 全员确认 |
| 4 | 🟠 | 代码 | snapshot_router.py L947-958 | H2: 移除override后，一致性计算用actual_action（T+1才回填，当天为NULL），导致当天一致性永远NULL | 改用system_action（实时计算的金额字段中已有） | 调查员 |
| 5 | 🟠 | 代码 | snapshot_router.py L947-958 + L938 | H3: system_action是中文（"加仓"/"持有"/"减仓"），deepseek_advice_action是英文（"increase"/"hold"/"decrease"），一致性计算需统一映射 | 代码层加中英文映射表 | 调查员 |
| 6 | 🟠 | 代码 | AIAnalysisPanel.tsx L170-173 | H5: 前端正则从deepseek_advice首行提取建议金额，改JSON格式后正则失效 | 改为从新列ds_target_pct或JSON字段提取 | 调查员 |
| 7 | 🟠 | 安全 | scheduler.py L2838-2856 | 方案B移除override后DeepSeek独立action不受约束，若被注入恶意指令可能输出非预期action | 保留Gate安全边界：Gate-1/Gate-2触发时仍强制系统action；action白名单校验 | 安全官 |
| 8 | 🟡 | 安全 | snapshot_router.py L536-593 | CSV公式注入：validation-download导出的文本字段若以=+-@开头，Excel打开可触发公式执行 | _format_validation_value中加_sanitize_csv_cell转义 | 安全官 |
| 9 | 🟡 | 产品 | 全局 | 用户信任风险：AI说"减仓"系统说"持有"，用户听谁的 | 展示双方历史准确率让数据说话；AI建议标注"仅供参考"；conflict时提示系统有Gate风控支撑 | 产品官 |
| 10 | 🟡 | 产品 | 方案B设计 | 方案B未设计G7一致性分析的存储方案（4列），双列对比的配套存储缺失 | Phase 3补充G7的4列（advice_consistent/consistency_score/consistency_note/conflict_fields） | 产品官 |
| 11 | 🟡 | 安全 | 全部API | 无速率限制，validation-download可被无限制调用导出大量数据 | 添加slowapi或FastAPI中间件实现速率限制（如每IP每分钟30次） | 安全官 |
| 12 | 🟡 | 代码 | scheduler.py L2630-2649 | Prompt重写是最高风险点——从"翻译器"到"独立顾问"不是改几行prompt，是重新设计AI角色定位 | Phase 1先用最小prompt改动验证可行性，Phase 2再做完整JSON prompt重构 | 调查员+产品官 |
| 13 | 🟡 | 安全 | scheduler.py L2789-2794 | JSON解析失败风险——DeepSeek可能输出不完整JSON、JSON前后有多余文本 | 4层fallback：直接解析→正则提取→代码块提取→首行扫描；Pydantic Schema校验 | 调查员+安全官 |
| 14 | 🟢 | 安全 | main.py L66-76 | 全局异常处理将str(exc)直接返回客户端，可能泄露内部信息 | 生产环境返回通用错误消息，详细错误仅记日志 | 安全官 |
| 15 | 🟢 | 安全 | snapshot_router.py L825 | fund_code路径参数无格式校验，可传入任意字符串 | 添加Path(..., regex=r'^\d{6}$') | 安全官 |
| 16 | 🟢 | 产品 | 历史数据 | 翻译器模式的历史数据与独立顾问模式不兼容，AI准确率统计需从切换日起重新计算 | 用ds_action_source列标记模式；stats API分别返回两个准确率 | 产品官 |

---

## 3. 方案B与项目书设计对齐度

### 当前状态 → 方案B目标 → 项目书设计

| 字段组 | 当前DB | 方案B Phase 1 | 方案B Phase 2 | 方案B Phase 3 | 项目书设计 |
|--------|--------|-------------|-------------|-------------|-----------|
| G6 DeepSeek建议 | 3列 | 3列（语义修正） | 6列（+3新列） | 9列（+3增强） | 9列 |
| G7 一致性分析 | 0列（被回验评分占用） | 0列（自动计算但不存储） | 0列 | 4列 | 4列 |
| 4个API | ✅ 已实现 | ✅ 已实现（一致性自动生效） | ✅ 扩展返回字段 | ✅ 完整返回 | ✅ |
| 前端双列对比 | ✅ 已有但假对比 | ✅ 真对比（自动生效） | ✅ 增强展示 | ✅ 完整展示 | ✅ |
| T+1回验 | ❌ bug（测系统非AI） | ✅ 自动修复 | ✅ | ✅ +confidence加权 | ✅ |
| 对齐度 | ~20% | ~35% | ~65% | ~100% | 100% |

---

## 4. 推荐实施路径（三成员建议综合）

### Phase 0：安全紧急修复（独立于方案B，立即执行）

| # | 行动 | 文件 | 耗时 |
|---|------|------|------|
| 0.1 | ECS .env 设 AUTH_DISABLED=false | ECS /opt/fund-sentiment/v5-deploy/backend/.env | 1min |
| 0.2 | 4个validation端点添加Depends(get_current_user) | snapshot_router.py L536/596/675/825 | 30min |
| 0.3 | CSV公式注入防护（_sanitize_csv_cell） | snapshot_router.py L480-533 | 15min |

### Phase 1：零DDL去Override（ROI最高，~1天）

| # | 行动 | 文件/行号 | 依赖 |
|---|------|----------|------|
| 1.1 | 实现 Feature Flag: DEEPSEEK_MODE=translator|independent | config.py + .env | 无 |
| 1.2 | 移除override逻辑（L2838-2856），deepseek_advice_action存AI原始action | scheduler.py L2838-2872 | 1.1 |
| 1.3 | 最小prompt改动：从"复述系统建议"改为"给出你的独立判断" | scheduler.py L2630-2649, L2762-2774 | 1.1 |
| 1.4 | 修复H2：一致性计算改用system_action而非actual_action | snapshot_router.py L947-958 | 1.2 |
| 1.5 | 修复H3：中英文action映射表 | snapshot_router.py L947-958 | 1.4 |
| 1.6 | 保留Gate安全边界：Gate-1/Gate-2触发时仍强制系统action | scheduler.py L2838附近 | 1.2 |

**自动修复**：T+1 bug（L3061-3070）、一致性假对比、deepseek_advice_correct语义
**零改动**：DB（无新列）、前端（一致性横条自动显示真实状态）
**观察期**：上线后2-4周，统计AI vs 系统准确率

### Phase 2：3列DDL + JSON结构化输出（~3天）

| # | 行动 | 文件/行号 | 依赖 |
|---|------|----------|------|
| 2.1 | ALTER TABLE 新增3列（Instant DDL <1ms） | ECS MySQL | 无 |
| 2.2 | strategy_validation_log.py 新增3列定义 | model文件 | 2.1 |
| 2.3 | Prompt重构：要求JSON输出7字段 | scheduler.py L2630-2774 | 2.2 |
| 2.4 | JSON解析4层fallback + Pydantic Schema校验 | scheduler.py L2830附近 | 2.3 |
| 2.5 | 字段白名单校验（action/market_view/risk_level/time_horizon） | scheduler.py 解析层 | 2.4 |
| 2.6 | API序列化扩展（_serialize_advice追加3字段） | snapshot_router.py L868-939 | 2.2 |
| 2.7 | 前端接口扩展 + DeepSeek建议列UI增强 | AIAnalysisPanel.tsx L19-87, L243-262 | 2.6 |
| 2.8 | 修复H5：前端正则提取金额改为从新列读取 | AIAnalysisPanel.tsx L170-173 | 2.7 |
| 2.9 | temperature降至0.1-0.2，max_tokens升至3000 | config.py L301-305 | 2.3 |

### Phase 3：全量对齐项目书（~4天）

| # | 行动 | 依赖 |
|---|------|------|
| 3.1 | ALTER TABLE 新增剩余7列（4个G6增强 + 4个G7一致性 - Phase 2已建3列 = 实际新增5列+索引） | 无 |
| 3.2 | G7一致性分析计算逻辑（advice_consistent/consistency_score/consistency_note/conflict_fields） | 3.1 |
| 3.3 | 完整7字段JSON prompt + 解析 | Phase 2 |
| 3.4 | API完整序列化 + CSV列扩展 + validation-history扩展 | 3.1 |
| 3.5 | 前端完整重构：DeepSeek建议列展示7字段 + 一致性横条增强 | 3.4 |
| 3.6 | ds_advice_correct_v2列 + T+1回验增强（可选confidence加权） | 3.1 |
| 3.7 | 历史数据标记（ds_action_source='translator_mode'） | 3.1 |

---

## 5. DDL设计建议（安全官+调查员综合）

### 列命名约定

两个成员提出了不同的命名方案，综合建议采用 `ds_` 前缀（更短，与现有 `deepseek_advice_*` 区分清晰）：

```sql
-- Phase 2: 3列（Instant DDL, <1ms）
ALTER TABLE strategy_validation_log
  ADD COLUMN ds_target_pct DECIMAL(5,4) DEFAULT NULL COMMENT 'AI建议目标仓位(0.0-1.0)',
  ADD COLUMN ds_confidence INT DEFAULT NULL COMMENT 'AI置信度(1-5)',
  ADD COLUMN ds_summary VARCHAR(500) DEFAULT NULL COMMENT 'AI建议摘要';

-- Phase 3: 7列 + 2索引（Instant DDL, <1ms）
ALTER TABLE strategy_validation_log
  ADD COLUMN ds_market_view VARCHAR(50) DEFAULT NULL COMMENT 'AI市场观点(bullish/neutral/bearish)',
  ADD COLUMN ds_risk_level VARCHAR(20) DEFAULT NULL COMMENT 'AI风险等级(low/medium/high)',
  ADD COLUMN ds_time_horizon VARCHAR(20) DEFAULT NULL COMMENT 'AI时间维度(short/medium/long)',
  ADD COLUMN ds_action_consistency VARCHAR(20) DEFAULT NULL COMMENT '一致性(consistent/partial/conflict)',
  ADD COLUMN ds_consistency_score DECIMAL(5,2) DEFAULT NULL COMMENT '一致性评分(0-100)',
  ADD COLUMN ds_consistency_note VARCHAR(200) DEFAULT NULL COMMENT '一致性说明',
  ADD COLUMN ds_conflict_fields VARCHAR(200) DEFAULT NULL COMMENT '冲突字段列表(JSON)',
  ADD COLUMN ds_advice_correct_v2 INT DEFAULT NULL COMMENT 'AI独立action准确度(0/1,T+1回填)',
  ADD COLUMN ds_action_source VARCHAR(20) DEFAULT NULL COMMENT 'action来源(system/deepseek/translator_mode)',
  ADD INDEX idx_validation_ds_action_consistency (ds_action_consistency),
  ADD INDEX idx_validation_ds_correct_v2 (ds_advice_correct_v2);
```

### 回滚DDL

```sql
-- 安全回滚（列均为DEFAULT NULL，删除不影响现有数据）
ALTER TABLE strategy_validation_log
  DROP INDEX idx_validation_ds_correct_v2,
  DROP INDEX idx_validation_ds_action_consistency,
  DROP COLUMN ds_conflict_fields, DROP COLUMN ds_consistency_note,
  DROP COLUMN ds_consistency_score, DROP COLUMN ds_action_consistency,
  DROP COLUMN ds_time_horizon, DROP COLUMN ds_risk_level,
  DROP COLUMN ds_market_view, DROP COLUMN ds_advice_correct_v2,
  DROP COLUMN ds_action_source, DROP COLUMN ds_summary,
  DROP COLUMN ds_confidence, DROP COLUMN ds_target_pct;
```

---

## 6. JSON解析4层Fallback策略（调查员设计）

```
DeepSeek响应
    │
    ▼
┌─ 尝试1: json.loads(response) ────────────── 成功 → Pydantic校验
│                                               失败 ↓
├─ 尝试2: 正则提取第一个{...}JSON对象 ────── 成功 → Pydantic校验
│                                               失败 ↓
├─ 尝试3: 提取```json...```代码块 ────────── 成功 → Pydantic校验
│                                               失败 ↓
├─ 尝试4: 首行action扫描（兼容旧格式） ───── 成功 → 填充action,其余NULL
│                                               失败 ↓
└─ 降级: action="hold", 所有字段NULL, 标记_parse_fallback=True
```

**Pydantic Schema校验**：
- action: 白名单 increase/hold/decrease（中文自动映射）
- target_pct: float, 0.0-1.0（>1自动除100）
- confidence: int, 1-5
- market_view: 白名单 bullish/neutral/bearish
- risk_level: 白名单 low/medium/high
- time_horizon: 白名单 short/medium/long
- summary: str, max 500字符

---

## ✅ 行动清单

| # | 行动 | 负责方 | 紧急度 | 期望完成 |
|---|------|--------|--------|---------|
| 1 | **设AUTH_DISABLED=false** + 4个端点加鉴权 + CSV注入防护 | 安全官/主理人 | **P0** | 今天14:47前 |
| 2 | **Phase 1: 去override + Feature Flag + 最小prompt改动 + 修H2/H3** | 主理人 | **P0** | 明天14:47前 |
| 3 | **验证门#13**: 今天14:50后验证Fix A+B效果 | 主理人 | **P0** | 今天14:50 |
| 4 | Phase 1上线后观察2-4周AI vs 系统准确率 | 主理人 | P1 | 2-4周后 |
| 5 | **Phase 2: 3列DDL + JSON prompt重构 + 4层fallback + 前端增强** | 调查员/主理人 | P1 | Phase 1验证后 |
| 6 | **Phase 3: G7一致性4列 + 剩余字段 + 前端完整重构** | 全员 | P2 | Phase 2验证后 |
| 7 | Gate安全边界保留：Gate-1/Gate-2触发时仍强制系统action | 主理人 | P0 | Phase 1同步 |
| 8 | API速率限制（slowapi中间件） | 安全官 | P1 | Phase 2同步 |
| 9 | 历史数据标记ds_action_source='translator_mode' | 主理人 | P2 | Phase 3 |
| 10 | 前端AI建议列添加"仅供参考"免责声明 | 产品官/主理人 | P1 | Phase 2同步 |

---

## ⚠️ 待完善 / 已知局限

- **JSON输出可靠性未实测**：4层fallback设计完备，但DeepSeek-v4-flash实际JSON输出稳定性需Phase 2上线后验证
- **Prompt重写质量是最大不确定性**：从"翻译器"到"独立顾问"的prompt重写需要反复调试，预估3-5轮迭代
- **列命名未最终确定**：调查员建议 `deepseek_advice_*` 前缀，安全官建议 `ds_*` 前缀，本报告采用 `ds_*`（更短），需用户确认
- **G7一致性算法是设计而非实现**：consistency_score的评分逻辑（80分起步+target_pct偏差加分等）是产品评审员基于项目书设计的，未经实际验证
- **历史18行数据影响为零**：deepseek_advice_correct全为NULL（T+1未执行），ext_text1全为NULL（无mismatch），当前无错误数据需修复
- **HTTPS未确认**：安全官发现直接访问8765端口为HTTP，未确认是否有反向代理终止TLS

---

## 📚 成员产出索引

- **gstack-product-reviewer（产品官）原始产出**：`deliverables/gstack/product-review-deepseek-planb-2026-07-09.md`
  - 关键修正：4个API已实现、前端已联通
  - 3阶段实施路径、7字段必要性排序、产品风险矩阵8项
  
- **gstack-investigator（调查员）原始产出**：`deliverables/gstack/code-review-deepseek-planb-2026-07-09.md`
  - 19个变更点矩阵（文件/函数/行号/依赖/风险）
  - T+1 bug精确数据流追踪、JSON 4层fallback伪代码、10个隐藏依赖
  
- **gstack-security-officer（安全官）原始产出**：`deliverables/gstack/security-audit-deepseek-planb-2026-07-09.md`
  - DB迁移风险评估（18行表实查）、11列DDL设计、6个安全发现（2C/3M/2L）
  - Feature Flag回滚策略（2分钟）、STRIDE威胁模型、OWASP Top 10检查

---

> 本报告由软件工坊 AI 协作生成（产品官 + 调查员 + 安全官 三成员并行验证），关键决策请由工程负责人复核。
