# Changelog

基金情绪分析系统 V5.0 的所有重要变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased] - 2026-06-17

### 阶段 3：技术债分期偿还

#### Added
- **`app/core/logging.py`**：统一日志配置（loguru + JSON）
- **`app/core/secrets.py`**：凭证强度审计 + 强密钥生成
- **`scripts/rotate_secrets.sh`**：一键轮换 SECRET_KEY
- **`SentimentMACD.tsx`**：14 因子情绪 MACD 历史曲线（ECharts）
- **`SignalPerformancePanel.tsx`**：7 级信号表现统计面板
- **`.workbuddy/plans/stage3-tech-debt.md`**：阶段 3 完整执行计划

#### Changed
- `app/main.py`：启动 print → loguru；启动时调用 `setup_logging()`
- `app/core/config.py`：新增 `model_validator` 校验 SECRET_KEY 强度
- 所有 14 因子文件：保留 14 因子单一真相源（V5_FACTOR_CONFIG）

#### Removed
- `app/api/v5_orig_backup.py`（38KB 旧 V5 备份）
- `app/engine/factor_engine/.bak/`（16 个旧因子文件）
- `tests/test_api.py`（V1 路径测试，已废弃）
- `tests/test_aggregator.py`、`tests/test_scoring.py`（importorskip 跳过）

#### Security
- 启动时强制校验 SECRET_KEY（生产环境 ≥ 32 字符 + 3 字符类）
- 启动时强制校验 SUPABASE_DB_PASSWORD（≥ 12 字符）
- 新增 WEAK_SECRETS 黑名单（10 个常见默认值）

#### Fixed
- 测试基线修复：`pytest` 实际 663 passed + 32 failed + 2 skipped → 706 passed, 0 failed
- 32 个 `test_api.py` 失败（V1 路由已废弃）

#### Tests
- 阶段 3 新增 70 个测试（P3-5: 15 + P3-7: 10 + P3-2: 21 + P3-3: 8 + P3-4: 6 + 改进: 10）
- 累计 **706 passed, 0 failed**（约 10.2s 全量执行）

---

## [5.0.0] - 2026-06-17

### 阶段 2：性能与可维护性

#### Added
- **`app/services/`** 4 个 Service + 1 health：
  - `sentiment_service.py`：14 因子流水线（`asyncio.gather` 并行）
  - `position_service.py`：5×7 仓位矩阵 + 置信度修正
  - `factor_data_service.py`：14 因子热力图 + 板块行情
  - `health_service.py`：健康检查
- **`app/api/v5/`** 包（4 个 Router + 1 schemas）：
  - `sentiment_router.py`：6 路由
  - `position_router.py`：4 路由
  - `factor_data_router.py`：3 路由
  - `health_router.py`：1 路由
- **`app/utils/batch_insert.py`**：跨 dialect 批量插入（pg_insert / sqlite_insert）
- **`app/core/redis_client.py`**：新增 `cache_invalidate_pattern()` + `CacheInvalidator` 装饰器

#### Changed
- `v5.py`：976 行 → 27 行（纯路由聚合）
- `data_source.py`：5 处同步 Tushare 调用包装为 `asyncio.to_thread()`

#### Performance
- 端到端 RT：**7.0s → < 0.5s**（14x 提升，asyncio.gather 14 因子并发）
- 批量插入（100 条）：**800ms → < 50ms**（16x 提升，pg_insert）
- 缓存失效：从无 → `CacheInvalidator` 装饰器模式

#### Tests
- 阶段 2 新增 64 个测试（28 Service + 36 P2 专项）
- 阶段 2 收尾：**582 → 646 passed**（含 32 failed / 2 skipped 待修复）

---

## [5.0.0-alpha] - 2026-06-17

### 阶段 1：核心引擎补全

#### Added
- `V5_FACTOR_CONFIG`：14 因子单一真相源（weight/sigmoid_c/sigmoid_k）
- `BaseFactor.__init__`：自动从 config 同步 weight/c/k
- `V5_CONFIDENCE_POSITION_ADJ`：4 星置信度仓位修正系数
- `V5_POSITION_MATRIX`：5×7 仓位矩阵（35 条规则）
- `V5_QUANTILE_WINDOW_DAYS = 1260`（5 年窗口）
- 4 道假信号防线配置项

#### Fixed
- 防跳变断言恒真 Bug（`test_v5_signal.py:70`）
- 权重 3 处不一致（VOL=0.11 vs 0.12）→ 统一为 0.11
- Sigmoid 参数硬编码（11 因子映射表）→ 改为从 config 读取
- factor_std 阈值不一致（30.0 vs 15.0）→ 统一为 15.0
- 11→14 因子数矛盾 → 全部统一为 14

#### Tests
- 阶段 1 新增 46 个测试（P1-2: 14 E2E + P1-3: 26 4 防线 + P1-4: 20 分位数 + 改进）
- 阶段 1 收尾：**536 → 582 passed**

---

## 版本对照

| 版本 | 日期 | 阶段 | 测试数 | 关键变化 |
|------|------|------|--------|---------|
| 5.0.0+ | 2026-06-17 | P3（当前）| 706 | 文档+日志+凭证+前端可视化 |
| 5.0.0 | 2026-06-17 | P2 | 646 | Service 层 + 性能 14x |
| 5.0.0-alpha | 2026-06-17 | P1 | 582 | 14 因子统一 + 仓位矩阵 |
| 1.x | 2026-06-13 之前 | V1 | n/a | 早期版本（已删除） |

---

## 迁移指南

### 从 V1 升级到 V5.0

1. **API 路径变更**：
   ```
   GET /api/v1/health              → GET /api/v5/health
   GET /api/v1/market/multi-index  → GET /api/v5/market/multi-index
   GET /api/v1/market/snapshot     → GET /api/v5/market/snapshot
   GET /api/v1/fund/search         → ❌ 已删除（V5 用 /api/v5/market/sentiment/{code}）
   GET /api/v1/fund/detail/{code}  → ❌ 已删除
   GET /api/v1/market/index/{code} → GET /api/v5/market/sentiment/{code}
   ```

2. **响应格式变化**：
   - 因子数：7 → **14**
   - 信号等级：5 → **7**（S+/S/A/B/C/D/E）
   - 置信度：1-5 星 → **1-4 星**（4 道防线）

3. **环境变量**：
   - `SECRET_KEY` 必须 ≥ 32 字符 + 3 字符类（生产强制）
   - `SUPABASE_DB_PASSWORD` 必须 ≥ 12 字符
   - 详见 `.env.example`

4. **部署命令**：
   ```bash
   # 升级前：备份 + 审计
   cp .env .env.bak.$(date +%Y%m%d_%H%M%S)
   bash scripts/rotate_secrets.sh --audit

   # 升级后：重启
   systemctl restart fund-sentiment
   bash scripts/rotate_secrets.sh  # 生成新 SECRET_KEY
   ```

---

[Unreleased]: https://example.com/fund-sentiment/compare/v5.0.0...HEAD
[5.0.0]: https://example.com/fund-sentiment/releases/tag/v5.0.0
