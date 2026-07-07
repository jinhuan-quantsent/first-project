# AI 分析面板 — 开发完成

## 概述

新增 AI 分析面板，在持仓详情中展示系统建议 vs DeepSeek AI 建议的双列对比，以及 T+1 回验结果。

## 变更文件

| 文件 | 变更 |
|------|------|
| `backend/app/api/v5/snapshot_router.py` | 新增 `GET /validation-today/{fund_code}` API |
| `frontend/src/components/portfolio/AIAnalysisPanel.tsx` | 新建组件 (339行) |
| `frontend/src/components/portfolio/PositionDetailPanel.tsx` | 导入+嵌入 AIAnalysisPanel |

## 后端 API

**端点**: `GET /api/v5/validation-today/{fund_code}`

**返回数据**:
- `today`: 当天记录（系统建议 system_advice_text + DeepSeek deepseek_advice + 预演数据 + Gate状态）
- `consistency`: 一致性分析 (consistent / partial / conflict)
- `has_system_advice` / `has_deepseek_advice`: 布尔标志
- `backfill_history`: 最近3天有T+1回验结果的记录

**时间线**:
- 14:45 系统建议写入
- 14:47 DeepSeek AI 建议写入
- 次日17:35 T+1回验回填

## 前端组件

**AIAnalysisPanel.tsx** 布局:
1. 标题栏: "AI 分析面板" + 一致性标签 + 风控状态 + 日期
2. 操作建议对比: 左列系统建议(加仓/持有/减仓) vs 右列 DeepSeek 建议
3. 一致性横条: 绿(一致) / 黄(部分一致) / 红(分歧)
4. 系统建议详情: 完整文本(可滚动)
5. DeepSeek AI 分析: 完整文本(可滚动)
6. 预演摘要: 一段话总结
7. 关键数据芯片: gszzl / 情绪分 / 分变化 / 弹性 / 大盘 / 板块 / 浮盈亏 / 星级
8. Gate 状态: 触发警告或安全距离
9. T+1回验记录: 最近3天，含评分/准确率/实际趋势

**特性**: 5分钟自动刷新, 可折叠, 无数据时不渲染

## 部署状态

- ✅ 3个文件已 SCP 到 ECS
- ✅ ECS 前端构建成功 (10.55s)
- ✅ 后端服务重启成功 (active)
- ✅ API 验证: `validation-today/008888` 返回 200 OK
- ✅ Health API: healthy (db=15.5ms, redis=0.4ms)
- ✅ Scheduler: 14:45/14:47/17:35 三个任务已注册
- ✅ TypeScript 零新增错误
- commit: 1a5c9cf (本地), GitHub push 进行中

## 后续验证

- 14:45 系统建议首次写入 → 检查 strategy_validation_log 表
- 14:47 DeepSeek AI 建议首次生成 → 检查 deepseek_advice 字段
- 前端面板在有数据后自动显示
