#!/usr/bin/env bash
# ============================================================
# rotate_secrets.sh — 阶段 3 P3-2 安全凭证轮换
# ============================================================
# 功能：
#   1. 生成新的强随机 SECRET_KEY
#   2. 自动更新 backend/.env 文件
#   3. 备份旧 .env 为 .env.bak.YYYYMMDD_HHMMSS
#   4. 打印新凭证强度报告
#
# 用法：
#   bash scripts/rotate_secrets.sh           # 轮换 SECRET_KEY
#   bash scripts/rotate_secrets.sh --audit   # 只审计，不修改
#   bash scripts/rotate_secrets.sh --length 64  # 自定义长度（默认 48）
#
# 注意：
#   - 轮换后所有现有 JWT 失效（用户需重新登录）
#   - 生产环境执行前务必先停服
#   - 此脚本**不会**同步到服务器（需手动 scp）
# ============================================================

set -euo pipefail

# ---- 参数解析 ----
AUDIT_ONLY=false
KEY_LENGTH=48
while [[ $# -gt 0 ]]; do
    case "$1" in
        --audit)
            AUDIT_ONLY=true
            shift
            ;;
        --length)
            KEY_LENGTH="$2"
            shift 2
            ;;
        *)
            echo "❌ 未知参数: $1"
            exit 1
            ;;
    esac
done

# ---- 路径 ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$BACKEND_DIR/.env"

# ---- 工具检测 ----
PYTHON_CMD="${PYTHON:-python}"

# ---- 函数：生成强密钥 ----
generate_secret() {
    "$PYTHON_CMD" - "$1" <<'PYEOF'
import secrets, string, sys
length = int(sys.argv[1])
alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
print("".join(secrets.choice(alphabet) for _ in range(length)))
PYEOF
}

# ---- 函数：审计 .env ----
audit_env() {
    echo "🔍 审计 .env 凭证强度..."
    BACKEND_DIR="$BACKEND_DIR" "$PYTHON_CMD" - "$ENV_FILE" <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["BACKEND_DIR"])
from app.core.secrets import audit_env_secrets
issues = audit_env_secrets(sys.argv[1])
if not issues:
    print("✅ 所有凭证强度合格")
    sys.exit(0)
print(f"⚠️  发现 {len(issues)} 个弱凭证:")
for issue in issues:
    print(f"  - {issue['key']}: score={issue['score']}, issues={issue['issues']}")
sys.exit(1)
PYEOF
}

# ---- 函数：备份 .env ----
backup_env() {
    if [[ -f "$ENV_FILE" ]]; then
        local bak="$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$bak"
        echo "📦 已备份旧 .env 到 $bak"
    fi
}

# ---- 函数：轮换 SECRET_KEY ----
rotate_secret_key() {
    if [[ ! -f "$ENV_FILE" ]]; then
        echo "❌ .env 文件不存在: $ENV_FILE"
        exit 1
    fi

    echo "🔄 生成新 SECRET_KEY（长度 $KEY_LENGTH）..."
    local new_key
    new_key="$(generate_secret "$KEY_LENGTH")"

    # 备份
    backup_env

    # 替换（用 Python 保留其他字段 + 注释）
    "$PYTHON_CMD" - "$ENV_FILE" "$new_key" <<'PYEOF'
import re, sys
env_file, new_key = sys.argv[1], sys.argv[2]
with open(env_file, 'r', encoding='utf-8') as f:
    content = f.read()
new_content = re.sub(
    r'^SECRET_KEY=.*$',
    f'SECRET_KEY={new_key}',
    content,
    flags=re.MULTILINE,
)
if 'SECRET_KEY=' not in new_content:
    new_content += f'\nSECRET_KEY={new_key}\n'
with open(env_file, 'w', encoding='utf-8') as f:
    f.write(new_content)
print("✅ .env 已更新")
PYEOF

    # 验证
    echo ""
    echo "📊 新凭证强度报告："
    BACKEND_DIR="$BACKEND_DIR" "$PYTHON_CMD" - "$ENV_FILE" <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["BACKEND_DIR"])
from app.core.secrets import validate_secret_strength
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('SECRET_KEY='):
            value = line.split('=', 1)[1].strip()
            result = validate_secret_strength(value, env='production')
            print(f"  SECRET_KEY: score={result['score']}/100, is_strong={result['is_strong']}")
            if result['issues']:
                print(f"  ⚠️ Issues: {result['issues']}")
            break
PYEOF

    echo ""
    echo "⚠️  重要：所有现有 JWT 将失效（用户需重新登录）"
    echo "⚠️  生产环境：scp .env 到服务器 + 重启服务"
    echo ""
    echo "示例（部署到阿里云）："
    echo "  scp $ENV_FILE root@47.103.67.106:/opt/fund-sentiment/backend/.env"
    echo "  ssh root@47.103.67.106 'systemctl restart fund-sentiment'"
}

# ---- 主流程 ----
echo "=========================================="
echo "🔐 Fund Sentiment V5.0 — 凭证轮换工具"
echo "=========================================="
echo ""

if [[ "$AUDIT_ONLY" == true ]]; then
    audit_env
    exit $?
fi

# 默认：先审计
if audit_env; then
    echo "✅ 凭证强度已合格，无需轮换"
    exit 0
fi

echo ""
read -p "是否继续轮换 SECRET_KEY？(y/N) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 1
fi

rotate_secret_key
echo ""
echo "✅ 凭证轮换完成"
