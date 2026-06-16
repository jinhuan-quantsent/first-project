# 服务器部署手册 — 2026-06-16 Phase 3+4 部署

## 前置条件
- SSH 已恢复（需先通过阿里云控制台重启 ECS 实例）
- 本地 3 个 commit 已推送: 0a4f93e, 8b424c9, fdf9784
- 前端已构建: frontend/dist/ (1.1MB, 9 assets)

## 步骤 1: 验证 SSH 连接
```bash
ssh -i ~/fund-sentiment-key.txt -o ConnectTimeout=20 root@47.103.67.106 "echo SSH_OK && uptime"
```

## 步骤 2: 拉取最新代码
```bash
cd /opt/fund-sentiment
git fetch origin
git reset --hard origin/v5-dev
```
验证: `git log --oneline -5` 应看到 fdf9784

## 步骤 3: 上传前端构建产物
在本地执行:
```bash
scp -i ~/fund-sentiment-key.txt -r frontend/dist/* root@47.103.67.106:/opt/fund-sentiment/frontend/dist/
```

## 步骤 4: 安装新增 Python 依赖（如有）
```bash
cd /opt/fund-sentiment/backend
pip install -r requirements.txt 2>&1 | grep "Successfully installed"
```

## 步骤 5: 重启后端服务
```bash
# 查找当前 uvicorn 进程
ps aux | grep uvicorn

# 杀掉旧进程
pkill -f "uvicorn app.main:app"

# 确认已停止
ps aux | grep uvicorn

# 启动新进程
cd /opt/fund-sentiment/backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 > /var/log/uvicorn.log 2>&1 &

# 验证启动
sleep 3
ps aux | grep uvicorn
curl -s http://localhost:8000/api/v5/snapshot | head -50
```

## 步骤 6: 检查 nginx
```bash
nginx -t          # 测试配置
systemctl status nginx
# 如果未运行: systemctl start nginx
```

## 步骤 7: 验证线上 API
```bash
# 快照接口
curl -s http://localhost:8000/api/v5/snapshot | python3 -m json.tool | head -20

# HTTPS 外部访问
curl -s https://fundsent.top/api/v5/snapshot | head -50

# 新因子检查
curl -s http://localhost:8000/api/v5/market/multi-index | python3 -m json.tool | grep -c "factor_scores"

# 新 API 路由
curl -s http://localhost:8000/api/v5/market/recommendations | head -20
curl -s http://localhost:8000/api/v5/market/sector-heatmap | head -20
```

## 步骤 8: 验证回填结果
```bash
cd /opt/fund-sentiment/backend
python3 -c "
import asyncio
from app.core.database import get_session
from sqlalchemy import text

async def check():
    async for session in get_session():
        # 总数
        r = await session.execute(text('SELECT COUNT(*) FROM factor_history'))
        print(f'factor_history 总行数: {r.scalar()}')
        # 按因子统计
        r = await session.execute(text('SELECT factor_name, COUNT(*) as cnt FROM factor_history GROUP BY factor_name ORDER BY cnt DESC'))
        for row in r:
            print(f'  {row[0]}: {row[1]}')
        break

asyncio.run(check())
"
```

## 步骤 9: 清理 fail2ban 封禁（如需要）
```bash
# 查看当前封禁列表
fail2ban-client status sshd

# 解封特定 IP
# fail2ban-client set sshd unbanip <IP>

# 调整 fail2ban 配置（更宽松）
# vi /etc/fail2ban/jail.local
# maxretry = 20
# bantime = 600
```

## 变更清单（3 个 commit）
### 0a4f93e - Phase 4 前端功能
- PortfolioV5: 内联编辑持仓市值 + 仓位执行UI
- Advice history / Trade records 真实数据替换
- Toast 全局通知组件
- MarketInfoBar 显示信号原因
- SectorCards 真实 API 数据
- WatchlistV5 SignalRibbon 修复

### 8b424c9 - Phase 4 剩余
- OpportunityRadar 真实 API 数据
- market.py 路由注册到 main.py
- WatchlistV5 alert→toast 替换

### fdf9784 - Phase 3 新因子
- MARGIN 融资融券因子 (margin.py, weight=0.04)
- RSI 相对强弱因子 (rsi.py, weight=0.03)
- INDUSTRY_DIVERGENCE 行业分歧度因子 (industry_divergence.py, weight=0.03)
- 14因子权重再平衡（原11因子各减约0.01）
- config.py V5_FACTOR_CONFIG 更新
- __init__.py 注册3个新因子
