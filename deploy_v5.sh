#!/bin/bash
# ============================================================
# 基金情绪分析系统 V5.0 — 生产部署脚本
# 服务器: 47.103.67.106
# 分支: v5-dev (85 files, +8828/-1025)
# 日期: 2026-06-14
# ============================================================

set -e  # 任何命令失败就停止

echo "=========================================="
echo "  FundSent V5.0 生产部署"
echo "=========================================="

# ------ 第1步：定位项目目录 ------
echo ""
echo "[1/7] 🔍 定位项目目录..."
if [ -d "/root/first-project" ]; then
    PROJECT_DIR="/root/first-project"
elif [ -d "/workspace/fund-sentiment" ]; then
    PROJECT_DIR="/workspace/fund-sentiment"
else
    echo "❌ 找不到项目目录，请手动设置 PROJECT_DIR"
    echo "   常见位置："
    find / -name "main.py" -path "*/backend/*" 2>/dev/null | head -5
    exit 1
fi
echo "✅ 项目目录: $PROJECT_DIR"

cd "$PROJECT_DIR"

# ------ 第2步：备份当前版本 ------
echo ""
echo "[2/7] 💾 备份当前版本..."
BACKUP_DIR="/root/backup-v4-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r backend/ "$BACKUP_DIR/backend/"
if [ -d frontend/dist ]; then
    cp -r frontend/dist/ "$BACKUP_DIR/dist/"
fi
echo "✅ 备份完成: $BACKUP_DIR"

# ------ 第3步：拉取最新代码 ------
echo ""
echo "[3/7] 📥 拉取 v5-dev 分支..."
git fetch origin
git checkout v5-dev
git pull origin v5-dev
echo "✅ 代码已更新"

# ------ 第4步：安装后端依赖 ------
echo ""
echo "[4/7] 📦 安装后端依赖..."
cd backend
pip install -r requirements.txt -q 2>/dev/null || pip3 install -r requirements.txt -q
echo "✅ 依赖安装完成"

# ------ 第5步：验证 Tushare 连接 ------
echo ""
echo "[5/7] 🔌 验证 Tushare 数据源连接..."
python3 -c "
import asyncio
from app.utils.data_source import data_source

async def check():
    await data_source.initialize()
    ts = data_source._tushare_available
    print(f'Tushare: {\"✅ 可用\" if ts else \"❌ 不可用\"}')

    # 快速测试6个B类因子
    from app.utils.data_source import fetch_fund_flow, fetch_etf_change, fetch_fund_position, fetch_northbound_flow, fetch_put_call_ratio, fetch_new_fund_heat
    print(f'FLOW: {await fetch_fund_flow(\"SH000300\")}')
    print(f'ETF:  {await fetch_etf_change(\"SH000300\")}')
    print(f'POS:  {await fetch_fund_position()}')
    print(f'NBF:  {await fetch_northbound_flow()}')
    print(f'PCR:  {await fetch_put_call_ratio()}')
    print(f'NEWF: {await fetch_new_fund_heat()}')

asyncio.run(check())
" 2>&1
echo "✅ 因子数据源验证完成"

# ------ 第6步：重启后端服务 ------
echo ""
echo "[6/7] 🔄 重启后端服务..."
# 查找并杀掉旧的 uvicorn 进程
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2

# 用 nohup 后台启动
cd "$PROJECT_DIR/backend"
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 > /root/uvicorn.log 2>&1 &
sleep 3

# 检查是否启动成功
if curl -s http://localhost:8000/api/v1/health | grep -q "4.0.0\|5.0.0\|ok"; then
    echo "✅ 后端启动成功"
else
    echo "⚠️ 后端可能未启动，检查日志: tail -50 /root/uvicorn.log"
fi

# ------ 第7步：验证API端点 ------
echo ""
echo "[7/7] 🧪 验证 API 端点..."

echo ""
echo "--- /api/v1/health ---"
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool 2>/dev/null || echo "❌ health 检查失败"

echo ""
echo "--- /api/v1/market/snapshot ---"
curl -s http://localhost:8000/api/v1/market/snapshot | python3 -m json.tool 2>/dev/null | head -20 || echo "❌ snapshot 检查失败"

echo ""
echo "--- /api/v1/market/multi-index ---"
curl -s http://localhost:8000/api/v1/market/multi-index | python3 -m json.tool 2>/dev/null | head -20 || echo "❌ multi-index 检查失败"

# V5 专属端点
echo ""
echo "--- /api/v5/signal/SH000300 ---"
curl -s http://localhost:8000/api/v5/signal/SH000300 | python3 -m json.tool 2>/dev/null | head -30 || echo "⚠️ V5 endpoint 可能未注册"

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "访问地址："
echo "  后端API:  http://47.103.67.106:8000/api/v1/health"
echo "  V5信号:   http://47.103.67.106:8000/api/v5/signal/SH000300"
echo "  日志:     tail -f /root/uvicorn.log"
echo ""
echo "回滚命令（如果出问题）："
echo "  cd $PROJECT_DIR && git checkout main"
echo "  cp -r $BACKUP_DIR/backend/* backend/"
echo "  pkill -f uvicorn && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"
