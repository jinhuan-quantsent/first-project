# ExpandableReason 组件设计规格

> 基金情绪分析 V5.0 — 信号理由三段式可展开组件

---

## 1. 概述

将信号理由从当前单行 `truncate` 文本改为"三段式"可展开组件，信息结构化为 **观察→分析→行动** 逻辑链，默认折叠只显示第一段摘要，点击展开完整三段。

### 当前状态

| 位置 | 现状 | 问题 |
|------|------|------|
| `FundResultList` 搜索结果行 | `<p className="text-[13px] text-gray-500 truncate">{reason}</p>` | 单行截断，信息丢失 |
| `FundDetailPanel` 右侧面板 | `<p className="text-xs text-gray-600 leading-relaxed">{sentiment.reason}</p>` | 全文展示但无结构 |
| `PositionDetailPanel` 持仓详情 | `<span className="text-[10px] text-gray-400 truncate max-w-[120px]">{data.signalReason}</span>` | 截断更严重 |
| `SectorWarnings` 风险警示 | `<p className="text-[10px] text-gray-400 max-w-[140px] truncate">{item.reason}</p>` | 同样截断 |

**reason 数据来源**：`buildReasonFromFactors()` 拼接 `"波动率82分+北向资金78分触发极度恐惧"` — 仅包含触发原因，无市场现状和操作建议。

---

## 2. 组件结构（JSX 层级）

### 2.1 顶层组件

```
<ExpandableReason>
  ├── <ReasonHeader>                    ← 折叠态摘要行（始终可见）
  │     ├── <SectionIcon type="observe"/>   ← 眼睛图标
  │     ├── <SummaryText>                   ← 第一段前 N 字 + "..."
  │     └── <ChevronIcon expanded/>         ← 展开/折叠箭头
  │
  └── <ReasonBody>                      ← 展开态内容区（条件渲染）
        ├── <ReasonSection type="observe">   ← 市场现状
        │     ├── <SectionLabel>
        │     │     ├── <SectionIcon type="observe"/>
        │     │     └── <SectionTitle> "市场现状" </SectionTitle>
        │     └── <SectionContent> {text} </SectionContent>
        │
        ├── <ReasonConnector/>              ← 段间视觉连接符 "→"
        │
        ├── <ReasonSection type="analysis">  ← 触发原因
        │     ├── <SectionLabel>
        │     │     ├── <SectionIcon type="analysis"/>
        │     │     └── <SectionTitle> "触发原因" </SectionTitle>
        │     └── <SectionContent> {text} </SectionContent>
        │
        ├── <ReasonConnector/>
        │
        └── <ReasonSection type="action">    ← 操作建议
              ├── <SectionLabel>
              │     ├── <SectionIcon type="action"/>
              │     └── <SectionTitle> "操作建议" </SectionTitle>
              └── <SectionContent> {text} </SectionContent>
</ExpandableReason>
```

### 2.2 内联 / 弹出变体

| 变体 | 用途 | 展开行为 |
|------|------|----------|
| `inline` | FundResultList 列表行内 | 原地向下展开，推开下方元素 |
| `panel` | FundDetailPanel / PositionDetailPanel | 原地向下展开（面板内空间充裕） |
| `compact` | SectorWarnings / 卡片内 | 原地向下展开，间距更紧凑 |

---

## 3. 交互状态

### 3.1 状态机

```
collapsed ←→ expanding ←→ expanded ←→ collapsing ←→ collapsed
                                     ↓ (auto 5s)
                                   auto-collapse (仅 compact 变体)
```

| 状态 | 视觉表现 |
|------|----------|
| `collapsed` | 仅显示 ReasonHeader，单行摘要 + 右侧箭头 `↓` |
| `expanding` | ReasonBody 从 `height:0` → `height:auto`，`opacity: 0→1` |
| `expanded` | 三段完整展示，箭头旋转 180° 变为 `↑` |
| `collapsing` | ReasonBody `height:auto` → `height:0`，`opacity: 1→0` |

### 3.2 过渡动画

| 属性 | 值 | 说明 |
|------|-----|------|
| `transition-duration` | `250ms` | 与 V5 `--duration-normal` 一致 |
| `transition-timing-function` | `cubic-bezier(0.4, 0, 0.2, 1)` | 与 V5 `--ease-default` 一致 |
| `transition-property` | `height, opacity` | 高度+透明度双动画 |
| Chevron 旋转 | `transform: rotate(180deg)` | 250ms 同曲线 |

### 3.3 触发方式

- **点击** ReasonHeader 整行 → toggle 展开/折叠
- **键盘** Enter / Space 在 Header focus 时触发 toggle
- **无障碍**：`role="button"`, `aria-expanded`, `aria-controls`

### 3.4 自动折叠

- `compact` 变体：展开 5 秒后自动折叠（避免小卡片撑开过高）
- `inline` / `panel` 变体：不自动折叠，需用户手动收起

---

## 4. 视觉 Token

### 4.1 色彩

| 元素 | Token | 值 | 说明 |
|------|-------|-----|------|
| Header 背景 | `--color-bg-surface` | `#FFFFFF` | 白底 |
| Header hover | `--color-bg-hover` | `rgba(0,0,0,0.04)` | 极淡 hover |
| Body 背景 | `--color-bg-base` | `#F1F5F9` | 浅灰底 |
| 段标题文字 | `--color-text-tertiary` | `#94A3B8` | 灰色标签 |
| 段内容文字 | `--color-text-secondary` | `#475569` | 次要文字 |
| 摘要文字 | `--color-text-secondary` | `#475569` | 同段内容 |
| 连接符 `→` | `--color-text-tertiary` | `#94A3B8` | 弱化 |
| Chevron 图标 | `--color-text-tertiary` | `#94A3B8` | 默认灰 |
| Chevron hover | `--color-text-primary` | `#0F172A` | hover 黑 |
| 展开时 Header 底部边框 | `--color-border-subtle` | `rgba(0,0,0,0.06)` | 分隔线 |

#### 信号色关联（三段标签左侧竖线）

| 段 | 竖线颜色 | 说明 |
|----|----------|------|
| 市场现状（observe） | `--color-primary` `#14B8A6` | 青色 — 观察客观事实 |
| 触发原因（analysis） | 信号等级色 | 动态取自 `SIGNAL_COLORS[level]` |
| 操作建议（action） | 语义色 | 买入=绿 `--signal-s` / 卖出=红 `--signal-d` / 持有=黄 `--signal-b` |

### 4.2 间距

| 元素 | 间距 | 值 |
|------|------|-----|
| Header padding | `px-3 py-2` | 12px 8px |
| Body padding | `px-3 pt-2 pb-3` | 12px 8px 12px |
| 段间距（Section 间） | `gap-2` | 8px |
| 段标签与内容 | `gap-1` | 4px |
| 连接符上下 margin | `my-0.5` | 2px |
| 竖线宽度 | `w-0.5` | 2px |
| 竖线高度 | `h-full` | 与段内容同高 |
| 竖线左偏移 | `-ml-3` / absolute | 对齐段内容起始 |

**compact 变体**：所有垂直间距减半（`py-1`, `gap-1`, `my-0`）。

### 4.3 字体

| 元素 | font-size | font-weight | font-family | line-height |
|------|-----------|-------------|-------------|-------------|
| 摘要文本 | 13px (`text-[13px]`) | 400 | `--font-body` | 1.5 |
| 段标题 | 11px (`text-[11px]`) | 600 | `--font-body` | 1.4 |
| 段内容 | 12px (`text-xs`) | 400 | `--font-body` | 1.6 |
| 连接符 | 12px (`text-xs`) | 400 | `--font-mono` | 1 |
| Chevron | 14px (`w-3.5 h-3.5`) | - | SVG | - |

### 4.4 圆角与边框

| 元素 | 圆角 | 边框 |
|------|------|------|
| 整体容器 | `--radius-md` (10px) | `1px solid var(--color-border-subtle)` |
| 折叠态 | `--radius-md` | 同上 |
| 展开态 | `--radius-md` | 同上（无变化） |
| 段内容区 | 无 | 无 |
| Header hover 背景 | `--radius-sm` (6px) | 无 |

### 4.5 图标

| 位置 | 图标 | 来源 | 尺寸 |
|------|------|------|------|
| 市场现状 | `Eye` | lucide-react | 14×14 |
| 触发原因 | `Zap` | lucide-react | 14×14 |
| 操作建议 | `Target` (或 `Crosshair`) | lucide-react | 14×14 |
| Chevron | `ChevronDown` | lucide-react | 14×14 |

---

## 5. 三段之间的视觉区分方式

### 5.1 左侧竖线 + 图标

每段左侧有一条 **2px 竖线** 作为视觉锚点，颜色区分三段职能：

```
┌─────────────────────────────────────┐
│ 👁 市场现状  ···                    │  ← 青色竖线 #14B8A6
│   沪深300近5日连续下跌，成交量萎缩    │
│         至月均的60%，情绪持续走低     │
│                 ↓                    │  ← 连接符
│ ⚡ 触发原因  ···                    │  ← 信号色竖线（动态）
│   波动率82分+北向资金78分触发极度恐惧  │
│                 ↓                    │
│ 🎯 操作建议  ···                    │  ← 语义色竖线
│   建议小仓位试探性买入，设置8%止损    │
└─────────────────────────────────────┘
```

### 5.2 段间连接符

段与段之间用 `→` 箭头连接，表示逻辑推演链路（观察→分析→行动）：
- 颜色：`--color-text-tertiary`
- 字体：`--font-mono`
- 上下各 2px 间距
- 居中对齐

### 5.3 不使用卡片嵌套

三段同处一个浅灰底容器中，不各自独立成卡片，避免层级过深。视觉区分依靠：
1. 左侧竖线颜色差异
2. 段标题图标+文字
3. 段间 `→` 连接符

---

## 6. Props 接口定义

```typescript
/** 三段式理由数据 */
export interface ThreePartReason {
  /** 市场现状（观察） */
  observation: string;
  /** 触发原因（分析） */
  analysis: string;
  /** 操作建议（行动） */
  action: string;
}

/** 信号等级，用于动态着色 */
import type { SignalLevel } from '../../types';

/** 操作类型，用于操作建议段竖线颜色 */
export type ActionAdvice = 'buy' | 'sell' | 'hold';

export interface ExpandableReasonProps {
  /** 三段式理由数据 */
  reason: ThreePartReason;

  /** 当前信号等级，用于"触发原因"段竖线着色 */
  signalLevel: SignalLevel;

  /** 操作建议类型，用于"操作建议"段竖线着色 */
  actionAdvice?: ActionAdvice;

  /** 显示变体 */
  variant?: 'inline' | 'panel' | 'compact';

  /** 初始展开状态（受控） */
  defaultExpanded?: boolean;

  /** 展开状态变更回调 */
  onToggle?: (expanded: boolean) => void;

  /** 摘要最大字符数（折叠态显示），默认 40 */
  summaryMaxLength?: number;

  /** 自定义类名 */
  className?: string;
}
```

### 6.1 向后兼容适配

当前 `reason` 在多处是 `string` 类型（如 `FundSentiment.reason`、`sentimentMap[code].reason`）。需做适配：

```typescript
/** 将旧 string reason 转为 ThreePartReason（渐进迁移用） */
export function adaptReason(
  oldReason: string | ThreePartReason | undefined,
  signalLevel: SignalLevel,
  actionAdvice?: ActionAdvice,
): ThreePartReason {
  if (!oldReason) {
    return {
      observation: '暂无市场现状数据',
      analysis: signalLevel ? `${SIGNAL_LABELS[signalLevel]}信号触发` : '暂无分析数据',
      action: '暂无操作建议',
    };
  }
  if (typeof oldReason === 'string') {
    // 旧格式: "波动率82分+北向资金78分触发极度恐惧"
    return {
      observation: '—',           // 旧数据无观察段
      analysis: oldReason,        // 原文放分析段
      action: '—',                // 旧数据无建议段
    };
  }
  return oldReason;
}
```

---

## 7. 与 V5 设计系统一致性说明

### 7.1 颜色一致性

| 设计系统 Token | 本组件使用点 | 匹配 |
|---------------|-------------|------|
| `--color-bg-surface` #FFFFFF | Header 背景 | ✅ |
| `--color-bg-base` #F1F5F9 | Body 背景 | ✅ 与 `detail-reason`、`position-advice-reason` 一致 |
| `--color-text-secondary` #475569 | 段内容文字 | ✅ |
| `--color-text-tertiary` #94A3B8 | 段标题、连接符、Chevron | ✅ |
| `--color-border-subtle` rgba(0,0,0,0.06) | 容器边框 | ✅ |
| `--color-primary` #14B8A6 | 观察段竖线 | ✅ 品牌色一致性 |
| `--radius-md` 10px | 容器圆角 | ✅ |
| 信号色 `SIGNAL_COLORS` | 分析段竖线 | ✅ 复用现有映射 |

### 7.2 间距一致性

- 所有间距为 **4px 基数**的倍数（2/4/8/12px）
- Body 区域 `padding: 12px` 与 V5 模板 `detail-reason` 一致
- 段间距 8px 与 V5 模板中组件间 gap 一致

### 7.3 排版一致性

- 摘要 `text-[13px]` 与 FundResultList 当前 reason 文字大小一致
- 段内容 `text-xs` (12px) 与 FundDetailPanel 的 reason 一致
- 字体使用 `--font-body`，与全局一致

### 7.4 交互一致性

- 过渡 250ms + `cubic-bezier(0.4, 0, 0.2, 1)` 与 V5 `--duration-normal` + `--ease-default` 一致
- hover 背景 `rgba(0,0,0,0.04)` 与 V5 全局 hover 效果一致
- Chevron 旋转与 PositionDetailPanel 的 `portfolio-expand-btn` 展开箭头行为一致

### 7.5 白底 + 信号色 dot 风格一致性

组件整体白底，信号色仅出现在左侧竖线（非大面积填充），与 V5 确认的信号色方案（白底 + A/B/C 三级信号色 dot）一致：
- 信号色作为 **点缀**，不喧宾夺主
- 主色调保持浅色极简
- 信息层级通过灰度差（primary/secondary/tertiary）区分

---

## 8. 各接入点改造指引

### 8.1 FundResultList（搜索结果行） — `inline` 变体

**当前**：`<p className="text-[13px] text-gray-500 truncate">{reason}</p>`

**替换为**：
```tsx
<ExpandableReason
  reason={adaptReason(s?.reason, level, adviceAction)}
  signalLevel={level}
  actionAdvice={adviceAction}
  variant="inline"
  summaryMaxLength={35}
/>
```

**布局影响**：展开时卡片高度增加，下方卡片下移。需确保外层 `space-y-3` 可正常推展。

### 8.2 FundDetailPanel（右侧详情面板） — `panel` 变体

**当前**：
```tsx
<div className="bg-gray-50 rounded-lg p-3">
  <p className="text-xs text-gray-600 leading-relaxed">{sentiment.reason}</p>
</div>
```

**替换为**：
```tsx
<ExpandableReason
  reason={adaptReason(sentiment.reason, level, adviceAction)}
  signalLevel={level}
  actionAdvice={adviceAction}
  variant="panel"
  defaultExpanded={true}   // 面板内默认展开
/>
```

### 8.3 PositionDetailPanel（持仓详情） — `panel` 变体

**当前**：`<span className="text-[10px] text-gray-400 truncate max-w-[120px]">{data.signalReason}</span>`

**替换为**：
```tsx
<ExpandableReason
  reason={adaptReason(data.signalReason, data.signalLevel, ...)}
  signalLevel={data.signalLevel}
  variant="panel"
  defaultExpanded={true}
/>
```

### 8.4 SectorWarnings（风险警示） — `compact` 变体

**当前**：`<p className="text-[10px] text-gray-400 max-w-[140px] truncate shrink-0">{item.reason}</p>`

**替换为**：
```tsx
<ExpandableReason
  reason={adaptReason(item.reason, ...)}
  signalLevel={...}
  variant="compact"
  summaryMaxLength={20}
/>
```

---

## 9. 状态管理

组件使用 `useState` 管理展开/折叠状态：

```tsx
const [expanded, setExpanded] = useState(defaultExpanded ?? false);
```

展开动画通过 `max-height` + `overflow: hidden` 实现（无需测量实际高度）：

```tsx
<ReasonBody
  style={{
    maxHeight: expanded ? '500px' : '0px',
    opacity: expanded ? 1 : 0,
    overflow: 'hidden',
    transition: 'max-height 250ms cubic-bezier(0.4,0,0.2,1), opacity 250ms cubic-bezier(0.4,0,0.2,1)',
  }}
/>
```

> `max-height: 500px` 远超实际内容高度（三段文本约 120-200px），确保动画流畅不截断。如需精确动画，可改用 `ref` 测量实际高度。

---

## 10. 无障碍

| 属性 | 值 |
|------|-----|
| Header `role` | `button` |
| Header `tabIndex` | `0` |
| Header `aria-expanded` | `true/false` |
| Header `aria-controls` | `reason-body-{id}` |
| Body `id` | `reason-body-{id}` |
| Body `role` | `region` |
| Body `aria-labelledby` | `reason-header-{id}` |
| 键盘 Enter/Space | toggle |
| `prefers-reduced-motion` | 禁用动画，直接 display none/block |

---

## 11. 文件位置

```
src/components/common/ExpandableReason.tsx    ← 主组件
src/components/common/ExpandableReason.css    ← 样式（可选，也可 Tailwind 内联）
```

放在 `common/` 目录，因为被 `fundsearch/`、`portfolio/`、`dashboard/` 多个模块引用。

---

## 12. 设计决策记录

| 决策 | 理由 |
|------|------|
| 左侧竖线而非背景色区分三段 | 竖线更克制，不增加视觉噪音，与 V5 浅色极简风格一致 |
| 段间用 `→` 文字符号而非 SVG 线条 | 轻量、可读、无需额外组件，语义清晰（逻辑推演链路） |
| `max-height` 动画而非 `height:auto` | CSS 过渡需要固定值；`max-height: 500px` 够用且性能好 |
| 三段同容器不嵌套卡片 | 避免卡片套卡片的视觉层级混乱，保持扁平 |
| `adaptReason()` 兼容函数 | 渐进迁移：API 尚未返回三段数据时，旧 string 格式自动适配 |
| `compact` 变体自动折叠 | 小卡片内展开后过高影响浏览，5 秒自动收起 |
| 观察段竖线用品牌色而非信号色 | 品牌色代表"客观观察"，信号色代表"主观判断"，语义区分 |
