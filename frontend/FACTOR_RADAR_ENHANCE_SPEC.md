# FactorRadar 增强设计 Spec

> 基金情绪分析系统 V5.0 — 14因子雷达图增强方案
> 设计师：gstack-designer ｜ 风格：浅色极简，与 DashboardV5 设计语言一致

---

## 0. 设计理念（一句话）

**让 14 因子雷达图从"只能看形状"升级为"一眼读懂情绪全貌"：中心叠加聚合分/信号/置信度，顶点气泡编码权重，恐惧→贪婪色编码贯穿填充与气泡，MACD 情绪动量条补足趋势维度。**

---

## 1. 数据来源（关键决策）

经核查现有 API，**可靠数据源**如下（注意规避一个后端 bug）：

| 数据 | 来源 API | 字段 | 备注 |
|------|---------|------|------|
| 因子 label / direction / percentile(0-100) / weight | `GET /api/v5/market/factor-radar` | `factors[].{name,label,direction,percentile,weight}` | ✅ 干净 JSON |
| 聚合分 / 信号等级 / 置信度星 | `GET /api/v5/market/sentiment/{code}` | `composite_score` / `signal_level` / `confidence_stars` | ✅ |
| 因子 sigmoid_score(0-100) | `GET /api/v5/market/sentiment/{code}` | `factor_details[].{factor_name,sigmoid_score,percentile(0-1)}` | ✅ |
| MACD 快照 | `GET /api/v5/market/sentiment/{code}` | `macd.{macd_line,signal_line,histogram,trend,cross,same_direction_days,momentum}` | ✅ 仅快照 |

> ⚠️ **后端 bug**：`GET /api/v5/market/factor-heatmap` 的 `factors[]` 当前返回的是 Python `repr` 字符串（如 `"FactorSigmoidResult(factor_name='VOL', ...)"`），**不是 JSON 对象**，前端无法解析 `f.raw_value`/`f.weight`。**增强组件不要依赖该接口**，改用 `factor-radar` + `sentiment` 双接口合并（按 `factor_name`/`name` 对齐）。

**实现建议**：增强组件同时调用 `fetchFactorRadar(code)` 与 `fetchV5Sentiment(code)`，合并为单一因子数组：
```ts
type EnhancedFactor = FactorRadarItem & {
  sigmoid_score: number;      // 来自 sentiment.factor_details
  contribution: number;       // = sigmoid_score * weight
};
const merged = radarFactors.map(r => {
  const d = sentiment.factor_details.find(x => x.factor_name === r.name);
  return { ...r, sigmoid_score: d?.sigmoid_score ?? r.percentile, contribution: (d?.sigmoid_score ?? r.percentile) * r.weight };
});
```

> ⚠️ **MACD 历史缺失**：`sentiment` 接口仅返回当前 MACD 快照，无法画 DIF/DEA 历史折线。后端 `sentiment_service._compute_macd_and_history` 内部已计算 120 日 composite 序列与 MACD 全序列，但未暴露。**Phase 1 的 MACD 面板用快照做"信号状态条"**；建议后端在 `sentiment` 响应中追加 `macd_history: [{date,dif,dea,hist}]`（最近 30~60 日），届时面板可升级为完整迷你 K 线（见 §7 Phase 2）。

---

## 2. 配色方案（与 DashboardV5 / index.css 完全一致）

### 2.1 信号语义色（复用现有 token）
| 信号 | 含义 | 色值 | 用途 |
|------|------|------|------|
| S+ | 极度恐惧 | `#059669` | 中心叠加/标签 |
| S | 恐惧 | `#10B981` | |
| A | 偏恐惧 | `#6EE7B7` | |
| B | 中性 | `#FBBF24` | 当前数据：composite=38.8 |
| C | 偏贪婪 | `#FCA5A5` | |
| D | 贪婪 | `#EF4444` | |
| E | 极度贪婪 | `#DC2626` | |

### 2.2 恐惧→贪婪渐变色阶（增强核心）
A股习惯"红涨绿跌" + 团队要求"恐惧=绿(买)、贪婪=红(卖)"，二者统一：

| 区间 | 色值 | 含义 |
|------|------|------|
| 0–30 | `#22C55E`（绿，market-down） | 恐惧·买入区 |
| 30–50 | `#FBBF24`（黄，signal-b） | 中性 |
| 50–70 | `#F59E0B`（琥珀） | 偏热 |
| 70–100 | `#EF4444`（红，market-up） | 贪婪·卖出区 |

> 这套色阶**复用** index.css 的 `--market-down`(#22C55E)、`--signal-b`(#FBBF24)、`--market-up`(#EF4444)，无需新增 token。

### 2.3 中性/UI 色（复用现有）
- 卡片底 `#FFFFFF`、页面底 `#F8FAFC`、悬停 `#F1F5F9`
- 边框 `#E2E8F0`、分割 `#F1F5F9`
- 雷达网格 splitArea：`['#F9FAFB','#F3F4F6','#E5E7EB','#D1D5DB']`（保持现状）
- splitLine `#E5E7EB`、axisLine `#D1D5DB`、轴标签 `#6B7280`
- 文字 主`#0F172A` / 次`#475569` / 弱`#94A3B8`

**对比度**：所有数值文字使用 `#0F172A`/`#475569`（≥7:1，满足 WCAG AAA）；黄色背景上的文字用 `#92400E`（amber-800，对比度 >4.5:1，满足 AA）。

---

## 3. 布局方案

组件内部自上而下三段，外层仍是 DashboardV5 现有的 `.card p-5`：

```
┌─ Card: 因子雷达图 ──────────────────────────────────────┐
│ [标题 因子雷达图]              [信号chip B·中性]  [日期]  │  ← header
│ ┌──────────────────────────────────────────────────┐   │
│ │            ECharts radar (height 340)            │   │
│ │        ┌──────────────┐                           │   │
│ │        │   38.8       │ ← 中心叠加(HTML绝对定位)   │   │
│ │        │  B · 中性     │                          │   │
│ │        │  ★☆☆☆        │                          │   │
│ │        └──────────────┘                           │   │
│ │   (14轴 + 顶点权重气泡 + 渐变填充)                 │   │
│ └──────────────────────────────────────────────────┘   │
│ [色阶图例: 恐惧·买 中性 偏热 贪婪·卖]  [气泡=权重 小→大]  │  ← legend
│ ┌─ MACD 情绪动量 ───────────────────────────────────┐   │
│ │ 空头↓ │ DIF -2.91 │ DEA -1.01 │ 柱 -1.90 │ ...    │   │  ← macd strip
│ └─────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

- **雷达容器** `position: relative`，高度 `340px`（桌面）/ `300px`（移动）。
- **中心叠加**用 HTML `div` 绝对定位 `left:50%; top:50%; transform:translate(-50%,-50%)`，叠加在 ECharts canvas 之上（`pointer-events: none`）。ECharts radar `center: ['50%','50%']`、`radius: '62%'`，确保多边形几何中心与叠加层对齐。
- **MACD 条**位于雷达下方，高度 `64px`，背景 `#F8FAFC` + `#E2E8F0` 边框圆角 8。
- 不改变 DashboardV5 现有 `lg:grid-cols-2`（雷达卡 | 信号验证看板）的外层栅格；增强全部在雷达卡内部完成。

---

## 4. 增强点详解

### 增强1：中心叠加显示
- 半透明白底卡片 `rgba(255,255,255,0.92)` + `1px solid #E2E8F0`，圆角 10，宽约 108–120px。
- 内容三行：
  1. **聚合分** `composite_score.toFixed(1)`，字号 26–28px，`font-weight:700`，颜色 = 该信号等级色（B→`#FBBF24`，可用深一档 `#F59E0B` 提升可读性）。
  2. **信号标签** `{signal_level} · {中文}`（S+极度恐惧 … E极度贪婪），12px 500，颜色取信号色的深色变体（黄信号用 `#92400E`）。
  3. **置信度星标** 4 颗星，亮星 `#FBBF24`、暗星 `#CBD5E1`，13px。复用 DashboardV5 的 lucide `Star` 图标或纯文本 `★/☆`。
- `pointer-events: none`，不阻挡雷达悬停。

### 增强2：颜色编码（恐惧→贪婪渐变）
- **绘图值统一为 sigmoid_score（0–100，已含方向归一）**，而非原始 percentile。理由：sigmoid 已把 fear/greed 方向折算成统一"贪婪度"（高=贪婪），且不会塌缩到 0（极端恐惧也有 ~12 分），形状可读；与 composite_score 同口径。
- **填充** `series.areaStyle.color` 用 ECharts 径向渐变（`type:'radial'`, x:0.5,y:0.5,r:0.5），colorStops：0→`rgba(34,197,94,0.30)`、0.5→`rgba(251,191,36,0.22)`、1→`rgba(239,68,68,0.16)`。半径越大越红，与"越外越贪婪"语义一致。
- **描边** `lineStyle.color` 取 composite 信号色（B→`#F59E0B`），width 1.5。
- **底部分位条**（保留现有 7 列 mini bar）：颜色按 sigmoid 分档（<30 绿 / 30–50 黄 / 50–70 琥珀 / ≥70 红），不再按 direction 反向。

### 增强3：因子权重可视化（顶点气泡）
- ECharts radar 单 series 的 `symbolSize`/`itemStyle` 是**整条统一**的，无法逐轴不同。采用 **custom series 叠加**方案：
  - 主 radar series 画多边形（`symbol:'none'` 隐藏默认点）。
  - 追加一个 `type:'custom'` series，`coordinateSystem:'radar'`，`renderItem` 依据 `params.coordSys`（含 `cx,cy,r`）逐顶点计算屏幕坐标 `(cx + r*(v/100)*cosθ, cy + r*(v/100)*sinθ)`，绘制 `<circle>`：
    - `r`(半径) = 权重映射：`3 + (weight - 0.02)/(0.12 - 0.02) * 5` → 权重 0.02→3px、0.12→8px。
    - `fill` = sigmoid 分档色（§2.2）。
    - `stroke:'#FFFFFF'` width 1.5，增强分离感。
- **悬停 tooltip**：custom series 的 `tooltip.formatter` 返回该因子完整信息：

  | 字段 | 示例 |
  |------|------|
  | 因子 | VOL · 波动率 |
  | 方向 | fear（恐惧向） |
  | 原始分位 | 100.0% |
  | Sigmoid | 18.2 |
  | 权重 | 0.12 |
  | 贡献度 | 2.19（=sigmoid×weight×0.1 归一展示，或直接 sigmoid×weight） |
  | 解读 | 恐惧·买入区 |

### 增强4：MACD 信号面板（快照版）
- 横向状态条（高度 64px），结构：`[趋势chip] [DIF] [DEA] [柱状] [动量] [同向] [交叉] [迷你柱]`。
- **趋势 chip**：`bullish`→绿底`#DCFCE7`/字`#16A34A` 文案"多头 ↑"；`bearish`→红底`#FEE2E2`/字`#DC2626` 文案"空头 ↓"；其他→灰。
- **数值**：DIF=`macd_line`、DEA=`signal_line`、柱状=`histogram`，正数红(`#EF4444`)负数也红? —— 因 MACD 在 composite 上：柱状>0 绿(`#22C55E`)、<0 红(`#EF4444`)（多头绿/空头红的常规配色）。
- **动量** `momentum`：正绿负红。
- **同向** `same_direction_days` + "日"。
- **交叉** `cross`：`golden`→"金叉"(绿)、`death`→"死叉"(红)、`null`→"无"(灰)。
- **迷你柱**：右侧 20×16 的零线柱，`histogram>0` 向上绿、`<0` 向下红，直观表示当前柱方向。
- 数据缺失（macd=null）时整条降级为"MACD 数据暂不可用"灰字。

---

## 5. ECharts 配置要点

```js
// —— radar.indicator：max=100，name 用短码（VOL/ADR…），全称进 tooltip ——
radar: {
  center: ['50%', '50%'],
  radius: '62%',
  indicator: merged.map(f => ({ name: f.name, max: 100 })),  // 短码，避免 14 标签拥挤
  shape: 'polygon',
  splitNumber: 4,
  axisName: {
    color: '#6B7280',
    fontSize: 11,           // 原 10 偏小，提到 11
    formatter: (name) => name, // 短码；可选 {name}\n{value}
  },
  splitArea: { areaStyle: { color: ['#F9FAFB','#F3F4F6','#E5E7EB','#D1D5DB'] } },
  splitLine: { lineStyle: { color: '#E5E7EB' } },
  axisLine: { lineStyle: { color: '#D1D5DB' } },
}

// —— 主多边形 series ——
series: [{
  type: 'radar',
  symbol: 'none',                       // 隐藏默认点，交给 custom
  lineStyle: { color: signalColor, width: 1.5 },
  areaStyle: {
    color: { type:'radial', x:0.5, y:0.5, r:0.5, colorStops:[
      { offset:0, color:'rgba(34,197,94,0.30)' },
      { offset:0.5, color:'rgba(251,191,36,0.22)' },
      { offset:1, color:'rgba(239,68,68,0.16)' },
    ]},
  },
  data: [{ value: merged.map(f => f.sigmoid_score), name: '情绪贪婪度' }],
}]

// —— 权重气泡 custom series（同图叠加）——
series.push({
  type: 'custom',
  coordinateSystem: 'radar',
  renderItem: (params, api) => {
    const cs = params.coordSys;            // { cx, cy, r, ... }
    const idx = api.value(0);              // 因子序号
    const f = merged[idx];
    const ang = (-90 + idx * (360/14)) * Math.PI/180;
    const rr = cs.r * (f.sigmoid_score/100);
    const x = cs.cx + rr * Math.cos(ang);
    const y = cs.cy + rr * Math.sin(ang);
    const size = 3 + ((f.weight - 0.02)/(0.12 - 0.02)) * 5;
    return { type:'circle', shape:{ cx:x, cy:y, r:size },
             style:{ fill: greedColor(f.sigmoid_score), stroke:'#fff', lineWidth:1.5 } };
  },
  data: merged.map((_, i) => [i]),        // 每项传因子序号
  tooltip: { formatter: (p) => factorTooltip(merged[p.dataIndex]) },
  z: 10,
});

// —— 贪婪色函数 ——
function greedColor(v){
  if (v < 30) return '#22C55E';
  if (v < 50) return '#FBBF24';
  if (v < 70) return '#F59E0B';
  return '#EF4444';
}
```

> custom series 与 radar 共坐标系时，`params.coordSys` 提供雷达几何（cx/cy/r），是逐顶点定位的关键。若该版本 ECharts 对 radar custom 支持有坑，降级方案：主 series 用 `symbol:'circle'` + 统一 `symbolSize`，权重改用轴标签字号/底部分位条宽度体现；逐点异色用多个"单值 radar series"（其余轴填 0）叠加，但更重，不推荐。

---

## 6. 交互设计

| 触发 | 行为 |
|------|------|
| 悬停顶点气泡 | tooltip 显示该因子：名称·中文、方向、原始分位%、sigmoid、权重、贡献度、解读色标 |
| 悬停多边形 | （可选）tooltip 汇总：composite、信号、置信度、恐惧/贪婪因子计数 |
| 悬停 MACD 数值 | tooltip 解释该字段含义（如"DIF=MACD线，上穿DEA为金叉"） |
| 点击因子轴 | 可选：emit `onFactorClick(factor)`，供父组件联动其他看板 |
| 响应窗口 resize | ECharts `resize()`；中心叠加用百分比定位自动跟随 |
| 数据加载 | 复用 `LoadingSpinner size="sm"`；error 显示 `text-xs text-red-400`（保持现状） |

无破坏性动效：多边形入场可用 `animationDuration:600, animationEasing:'cubicOut'`；气泡可 `scale` 入场。避免常驻循环动画（极简原则）。

---

## 7. 响应式适配

| 断点 | 雷达高度 | 轴标签 | 中心叠加 | MACD 条 |
|------|---------|--------|---------|---------|
| ≥1024px (lg) | 340px | 短码 11px | 26px 聚合分 | 横向单行 |
| 640–1024px (md) | 320px | 短码 11px | 24px | 横向单行，字段间距收紧 |
| <640px (sm) | 280px | 短码 10px，可旋转 -30° | 22px，星标 12px | 横向滚动或两行折行 |

- 14 个标签在窄屏易挤；**始终用短码**（VOL/ADR/ERP/FLOW/ETF/NHNL/TURN/POS/NBF/PCR/NEWF/MARGIN/RSI/DIVERGE），中文全称只在 tooltip 出现。
- 移动端可将 `axisName.formatter` 进一步缩写（如 `INDUSTRY_DIVERGENCE`→`DIV`）。
- 中心叠加宽度自适应内容，`max-width: 45%` 避免遮挡气泡。

---

## 8. 与现有设计语言的一致性核对

- 字体：系统无衬线（`-apple-system, PingFang SC…`），数值用 mono（`font-mono`）——与 DashboardV5 一致。
- 圆角：卡片 `rounded-lg`(8)、chip `rounded-full`/`rounded`——一致。
- 间距：卡内 `p-5`，段落 `space-y-4`，网格 `gap-3`——一致。
- 阴影：`.card` 的 `shadow-sm`，hover `shadow-md`——不新增阴影。
- 信号色/功能色全部复用 index.css token，**不引入新色值**（除琥珀 `#F59E0B` 作为黄→红过渡，可视为 signal-b 的深化，建议补一个 `--signal-warm:#F59E0B` token）。
- 浅色背景，无深色块；中心叠加半透明白而非深色蒙层。

---

## 9. 实现优先级 / 交付建议

| 阶段 | 内容 | 依赖 |
|------|------|------|
| Phase 1（本轮） | 增强1 中心叠加 + 增强2 渐变色 + 增强3 权重气泡 + 增强4 MACD 快照条 | 仅前端，双接口合并 |
| Phase 2（可选） | MACD 升级为完整 DIF/DEA 迷你折线 + 柱状 | 需后端 `sentiment` 响应追加 `macd_history` |
| Phase 2（可选） | 修复 `factor-heatmap` 序列化 bug，组件改回单接口 | 后端把 `factors[]` 转为 dict |

---

## 10. 当前真实数据校验（2026-06-24 SH000300）

- composite 38.8 / signal B(中性) / confidence 1★ / regime extreme_volatility
- MACD: DIF -2.91 / DEA -1.01 / 柱 -1.91 / trend bearish / cross null / 同向 2日 / 动量 -320
- 因子贪婪度(sigmoid)：多数 12–30(恐惧·绿)，PCR 31(黄)，RSI 60(琥珀)，NEWF 72.4 & MARGIN 72.6(贪婪·红)
- 形态：多边形大部分内缩(恐惧)，NEWF/MARGIN/RSI 三轴外凸(贪婪)——典型"因子分歧"，与 confidence 仅 1★、defenses 触发 `factor_std_high` 吻合。中心叠加 + 色编码能直观传达这一分歧，正是增强价值所在。
