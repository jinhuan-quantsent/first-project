"""
P4-2: Locust 压测脚本

目标：模拟 100 并发用户访问 V5.0 API，输出 P50/P95/P99 性能基线

运行方法：
    # 1. 启动后端服务（生产模式）
    cd backend
    uvicorn app.main:app --host 0.0.0.0 --port 8000

    # 2. 启动 Locust（无头模式，30 个用户，60 秒）
    locust -f locustfile.py --headless -u 30 -r 5 --run-time 60s --host http://localhost:8000

    # 3. 输出报告
    # - 控制台实时打印 RPS + 失败率
    # - 结束后生成 HTML 报告（默认 report.html）

可调参数：
    -u NUM   模拟用户数（默认 30，推荐 50-100）
    -r NUM   每秒启动用户数（默认 5）
    --run-time 压测时长（默认 60s，推荐 120s）
"""
import random
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner


# ============================================================
# 1. 真实场景用户类
# ============================================================

class FundSentimentUser(HttpUser):
    """模拟个人基金投资者使用情绪分析系统的典型行为

    任务分布（按实际使用频率）：
    - 35% 查看多指数情绪（最高频，登录后看大盘）
    - 25% 查看信号灯（核心功能）
    - 20% 查看情绪快照（基金详情）
    - 10% 查看因子雷达图
    - 5%  查看因子热力图
    - 5%  健康检查（前端启动时）
    """

    # 用户思考时间：1-3 秒（真实用户）
    wait_time = between(1, 3)

    # 常见指数代码
    INDEX_CODES = ["000001", "000300", "000905", "399006", "000688"]
    FUND_CODES = ["000001", "161725", "005827", "161038", "519677"]

    def on_start(self):
        """用户启动时调用健康检查"""
        self.client.get("/api/v5/health", name="[启动] health")

    @task(35)
    def view_multi_index_emotion(self):
        """35% 概率：查看多指数情绪（核心场景）"""
        codes = random.sample(self.INDEX_CODES, k=random.randint(2, 4))
        self.client.get(
            "/api/v5/market/multi-index",
            params={"codes": ",".join(codes)},
            name="/api/v5/market/multi-index",
        )

    @task(25)
    def view_signal_lights(self):
        """25% 概率：查看信号灯"""
        code = random.choice(self.INDEX_CODES)
        self.client.get(
            f"/api/v5/market/signal-lights/{code}",
            name="/api/v5/market/signal-lights/{code}",
        )

    @task(20)
    def view_sentiment_snapshot(self):
        """20% 概率：查看情绪快照"""
        code = random.choice(self.FUND_CODES)
        self.client.get(
            f"/api/v5/fund/sentiment-snapshot/{code}",
            name="/api/v5/fund/sentiment-snapshot/{code}",
        )

    @task(10)
    def view_factor_radar(self):
        """10% 概率：查看因子雷达图"""
        code = random.choice(self.INDEX_CODES)
        self.client.get(
            f"/api/v5/factor-radar/{code}",
            name="/api/v5/factor-radar/{code}",
        )

    @task(5)
    def view_factor_heatmap(self):
        """5% 概率：查看因子热力图"""
        self.client.get(
            "/api/v5/factor-heatmap",
            params={"days": random.choice([7, 30, 60])},
            name="/api/v5/factor-heatmap",
        )

    @task(5)
    def health_check(self):
        """5% 概率：健康检查（前端定时心跳）"""
        self.client.get("/api/v5/health", name="[心跳] health")


# ============================================================
# 2. 极端压测用户类（重负载场景）
# ============================================================

class HeavyLoadUser(HttpUser):
    """模拟脚本机器人 / 极端负载（无思考时间）"""

    wait_time = between(0.1, 0.5)  # 极短思考时间

    @task
    def hammer_health(self):
        """持续打健康检查（模拟监控/健康检查脚本）"""
        self.client.get("/api/v5/health", name="[hammer] health")

    @task(3)
    def hammer_multi_index(self):
        """高频调用多指数"""
        self.client.get(
            "/api/v5/market/multi-index",
            params={"codes": "000001,000300,000905"},
            name="[hammer] multi-index",
        )


# ============================================================
# 3. 事件钩子：记录性能基线
# ============================================================

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """压测开始时打印配置"""
    print("\n" + "=" * 60)
    print("🚀 基金情绪分析系统 V5.0 - Locust 压测")
    print("=" * 60)
    print(f"目标主机: {environment.host}")
    print(f"用户数: {environment.runner.user_count if hasattr(environment.runner, 'user_count') else 'N/A'}")
    print(f"=" * 60 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """压测结束时输出性能基线报告"""
    print("\n" + "=" * 60)
    print("📊 性能基线报告")
    print("=" * 60)

    stats = environment.stats
    total = stats.total

    print(f"总请求数:     {total.num_requests}")
    print(f"失败数:       {total.num_failures}")
    print(f"失败率:       {total.fail_ratio * 100:.2f}%")
    print(f"RPS:          {total.total_rps:.2f}")
    print(f"中位延迟:     {total.median_response_time:.1f}ms")
    print(f"P95 延迟:     {total.get_response_time_percentile(0.95):.1f}ms")
    print(f"P99 延迟:     {total.get_response_time_percentile(0.99):.1f}ms")
    print(f"最大延迟:     {total.max_response_time:.1f}ms")
    print(f"=" * 60 + "\n")

    # 验收标准
    p95 = total.get_response_time_percentile(0.95)
    p99 = total.get_response_time_percentile(0.99)
    fail_ratio = total.fail_ratio

    print("📋 验收标准：")
    print(f"  P95 < 200ms:    {'✅ PASS' if p95 < 200 else '❌ FAIL'} ({p95:.1f}ms)")
    print(f"  P99 < 500ms:    {'✅ PASS' if p99 < 500 else '❌ FAIL'} ({p99:.1f}ms)")
    print(f"  失败率 < 1%:    {'✅ PASS' if fail_ratio < 0.01 else '❌ FAIL'} ({fail_ratio * 100:.2f}%)")
    print("=" * 60 + "\n")
