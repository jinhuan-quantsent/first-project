"""
凭证强度审计 — 阶段 3 P3-2

提供：
- validate_secret_strength()：通用密码/key 强度检查
- generate_strong_secret()：生成强随机密钥（基于 secrets 模块）
- audit_env_secrets()：扫描 .env 找出弱凭证

设计原则：
- 不在日志中泄露任何凭证
- 不写文件，纯函数式审计
"""
import re
import secrets
import string
from pathlib import Path
from typing import Dict, List, Any


# 弱密码黑名单（常见 dev/test 默认值）
WEAK_SECRETS = frozenset({
    "dev-secret-key-change-in-production",
    "secret",
    "password",
    "changeme",
    "123456",
    "12345678",
    "test",
    "default",
    "your-secret-key",
    "replace-me",
})


def validate_secret_strength(value: str, env: str = "development") -> Dict[str, Any]:
    """
    校验密钥强度

    返回：
        {
            "is_strong": bool,
            "is_production": bool,
            "issues": List[str],  # 问题列表（人类可读）
            "score": int,         # 0-100 强度分
        }
    """
    issues: List[str] = []
    score = 100
    is_production = env.lower() == "production"

    # 1. 黑名单检查
    if value in WEAK_SECRETS:
        issues.append(f"使用常见默认/弱密钥")
        score -= 80

    # 2. 长度检查
    min_len = 32 if is_production else 16
    if len(value) < min_len:
        issues.append(f"长度不足 ({len(value)} < {min_len})")
        score -= 30

    # 3. 复杂度检查（至少 3/4 字符类）
    has_lower = bool(re.search(r"[a-z]", value))
    has_upper = bool(re.search(r"[A-Z]", value))
    has_digit = bool(re.search(r"\d", value))
    has_special = bool(re.search(r"[^A-Za-z0-9]", value))
    char_classes = sum([has_lower, has_upper, has_digit, has_special])
    if char_classes < 3:
        issues.append(f"复杂度不足 (仅 {char_classes}/4 字符类)")
        score -= 20

    # 4. 连续字符检查（aaaa, 1111 等）
    if re.search(r"(.)\1{3,}", value):
        issues.append("含 4+ 连续相同字符")
        score -= 10

    return {
        "is_strong": (
            score >= 70
            and len(value) >= min_len  # 长度必须满足
            and value not in WEAK_SECRETS  # 不可在黑名单
            and char_classes >= 3  # 复杂度必须够
        ),
        "is_production": is_production,
        "issues": issues,
        "score": max(0, score),
    }


def generate_strong_secret(length: int = 48) -> str:
    """
    生成强随机密钥

    使用 `secrets` 模块（密码学安全 PRNG），包含大小写字母+数字+特殊字符。
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def audit_env_secrets(env_path: str | Path = ".env") -> List[Dict[str, Any]]:
    """
    扫描 .env 文件中的凭证强度

    返回问题列表：
        [{"key": "SUPABASE_DB_PASSWORD", "value": "***" (脱敏), "issues": [...], "score": 60}, ...]
    """
    env_path_str = str(env_path)
    # Windows / Git Bash 路径兼容：/c/Users/foo → C:/Users/foo
    if env_path_str.startswith("/c/"):
        env_path_str = "C:/" + env_path_str[3:]
    elif env_path_str.startswith("/d/"):
        env_path_str = "D:/" + env_path_str[3:]
    env_path = Path(env_path_str)
    if not env_path.exists():
        return []  # 文件不存在时返回空（不报错）

    # 关注哪些 key
    sensitive_keys = {
        "SECRET_KEY",
        "SUPABASE_DB_PASSWORD",
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "TUSHARE_TOKEN",
        "UPSTASH_REDIS_TOKEN",
        "REDIS_URL",
        "CELERY_BROKER_URL",
    }

    issues: List[Dict[str, Any]] = []

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key not in sensitive_keys or not value:
                continue
            result = validate_secret_strength(value, env="production")
            if not result["is_strong"] or result["issues"]:
                issues.append({
                    "key": key,
                    "value_masked": value[:2] + "***" + value[-2:] if len(value) > 4 else "***",
                    "issues": result["issues"],
                    "score": result["score"],
                })

    return issues
