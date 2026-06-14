# 🚀 FundSent V5.0 生产部署指南

> 服务器：47.103.67.106 | 分支：v5-dev | 日期：2026-06-14

## 前置条件
- SSH 客户端（如 Xshell / MobaXterm / Windows Terminal）
- 服务器 root 密码

---

## 第1步：SSH 登录服务器

```bash
ssh root@47.103.67.106
```
输入密码后回车。

---

## 第2步：找到项目目录

```bash
find / -name "main.py" -path "*/backend/app/*" 2>/dev/null | head -3
```

记下输出路径（去掉 `/backend/app/main.py` 部分就是项目根目录）。
假设结果是 `/root/first-project/backend/app/main.py`，则项目目录为 `/root/first-project`。

---

## 第3步：备份当前版本

```bash
cd /root/first-project
cp -r backend /root/backup-backend-v4-$(date +%Y%m%d)
```

---

## 第4步：拉取 V5 代码

```bash
cd /root/first-project
git fetch origin
git checkout v5-dev
git pull origin v5-dev
```

如果提示 `detached HEAD` 或其他问题，用：
```bash
git branch -a  # 查看所有分支
git checkout -b v5-dev origin/v5-dev  # 创建并切换到 v5-dev
```

---

## 第5步：安装新依赖（如果有）

```bash
cd /root/first-project/backend
pip3 install -r requirements.txt -q
```

---

## 第6步：验证 Tushare + B类因子

```bash
cd /root/first-project/backend
python3 -c "
import asyncio
from app.utils.data_source import data_source, fetch_fund_flow, fetch_etf_change, fetch_fund_position, fetch_northbound_flow, fetch_put_call_ratio, fetch_new_fund_heat

async def check():
    await data_source.initialize()
    ts = data_source._tushare_available
    print(f'Tushare: {\"✅\" if ts else \"❌\"}')
    print(f'FLOW: {await fetch_fund_flow(\"SH000300\")}')
    print(f'ETF:  {await fetch_etf_change(\"SH000300\")}')
    print(f'POS:  {await fetch_fund_position()}')
    print(f'NBF:  {await fetch_northbound_flow()}')
    print(f'PCR:  {await fetch_put_call_ratio()}')
    print(f'NEWF: {await fetch_new_fund_heat()}')

asyncio.run(check())
"
```

**预期输出**（Tushare可用时）：
```
Tushare: ✅
FLOW: <真实值>
ETF:  <真实值>
POS:  <回归估算值>
NBF:  <真实值>
PCR:  <真实值或0.6~0.8>
NEWF: <真实值>
```

**如果 Tushare 不可用**，各因子会走二级降级，返回近似估算值（非硬编码）。

---

## 第7步：重启后端

### 方式A：直接 uvicorn（推荐）

```bash
# 杀掉旧进程
pkill -f "uvicorn app.main" || true
sleep 2

# 启动新进程
cd /root/first-project/backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 > /root/uvicorn.log 2>&1 &
sleep 3

# 验证
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

### 方式B：Docker 重新部署

```bash
cd /root/first-project/backend
docker build -t fundsent-backend:v5 .
docker stop fundsent-backend 2>/dev/null || true
docker rm fundsent-backend 2>/dev/null || true
docker run -d --name fundsent-backend -p 8000:8000 \
  -e TUSHARE_TOKEN=你的token \
  fundsent-backend:v5
```

---

## 第8步：验证 API 端点

```bash
# 健康检查
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool

# 市场快照（应返回真实 close 值）
curl -s http://localhost:8000/api/v1/market/snapshot | python3 -m json.tool | head -15

# V5 信号端点
curl -s http://localhost:8000/api/v5/signal/SH000300 | python3 -m json.tool | head -25
```

**V5/signal 预期返回**：
```json
{
  "index_code": "SH000300",
  "composite_score": 45~55,
  "signal_level": "B" 或 "C",
  "confidence_stars": 2~3,
  "factor_results": { ... 11个因子 ... }
}
```

---

## 第9步：前端部署（如果需要）

V5 前端有两种部署方式：

### 方式A：Vercel 部署（推荐）
```bash
# 在本地（你的Windows电脑）执行
cd C:\Users\pc\WorkBuddy\2026-06-13-16-20-35\first-project\frontend
npm run build
# 上传 dist/ 到 Vercel
```

### 方式B：服务器直接补丁
```bash
# 在服务器上构建
cd /root/first-project/frontend
npm install
npm run build
# 将 dist/ 目录配置到 nginx 或直接 serve
```

---

## ⚠️ 常见问题

### Q: git pull 报 SSL 错误
```bash
git -c http.sslVerify=false pull origin v5-dev
```

### Q: Tushare 报 429 限流
正常！moneyflow_hsgt 限流 1次/分钟，已加 Redis 缓存（TTL=3600s）。
等1分钟后重试即可。

### Q: uvicorn 启动失败
```bash
# 查看日志
cat /root/uvicorn.log

# 端口被占用
lsof -i :8000
kill -9 <PID>
```

### Q: 想回滚到 V4.0
```bash
cd /root/first-project
git checkout main
cp -r /root/backup-backend-v4-*/  backend/
pkill -f uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📊 部署验证清单

| 检查项 | 命令 | 预期 |
|--------|------|------|
| Tushare 连接 | 第6步 | `✅` |
| /health | `curl .../health` | `version: 4.0.0` |
| /market/snapshot | `curl .../snapshot` | 真实 close 值 |
| /v5/signal/SH000300 | `curl .../signal` | 11因子+信号 |
| B类6因子非硬编码 | 第6步 | 非默认值 |

全部 ✅ → 部署成功！🎉
