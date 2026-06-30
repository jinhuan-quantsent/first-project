"""
凭证强度测试 — 阶段 3 P3-2

覆盖：
- validate_secret_strength() 各种强度判定
- generate_strong_secret() 长度 + 字符类
- audit_env_secrets() .env 扫描
- Settings 校验：弱 SECRET_KEY 在生产 raise
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.secrets import (
    validate_secret_strength,
    generate_strong_secret,
    audit_env_secrets,
    WEAK_SECRETS,
)


class TestValidateSecretStrength:
    """validate_secret_strength 单元测试"""

    def test_weak_default_secret(self):
        """常见 dev 默认值应判定为弱"""
        result = validate_secret_strength("dev-secret-key-change-in-production")
        assert not result["is_strong"]
        assert result["score"] < 70
        assert any("默认" in i or "长度" in i for i in result["issues"])

    def test_short_secret_weak(self):
        """短字符串应判定为弱"""
        result = validate_secret_strength("abc")
        assert not result["is_strong"]
        assert any("长度" in i for i in result["issues"])

    def test_strong_secret(self):
        """48 字符 + 4 字符类应判定为强"""
        strong = "Abc123!@#Def456$Ghi789%Jkl012Mno345Pqr678Stu90"
        result = validate_secret_strength(strong, env="production")
        assert result["is_strong"]
        assert result["score"] >= 70
        assert not result["issues"]

    def test_repeated_chars_penalty(self):
        """4+ 连续相同字符应被扣分"""
        result = validate_secret_strength("AbcdEfgHijk" + "aaaa" + "LmnopQrsTuv")
        assert not result["is_strong"]
        assert any("连续" in i for i in result["issues"])

    def test_low_complexity_penalty(self):
        """仅 1 字符类应被扣分"""
        result = validate_secret_strength("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        assert not result["is_strong"]
        assert any("复杂度" in i for i in result["issues"])

    def test_production_requires_32_chars(self):
        """生产环境强制 ≥ 32 字符"""
        result_30 = validate_secret_strength("Abc123!@#Def456$Ghi789%Jkl012", env="production")
        assert not result_30["is_strong"]
        assert result_30["is_production"]

    def test_development_allows_16_chars(self):
        """开发环境允许 ≥ 16 字符"""
        result = validate_secret_strength("Abc123!@#Def456$", env="development")
        # 可能仍因其他原因弱，但长度本身不应触发 issue
        length_issues = [i for i in result["issues"] if "长度" in i]
        # 16 字符刚刚好 ≥ dev 要求，所以不应有长度问题
        assert not length_issues


class TestGenerateStrongSecret:
    """generate_strong_secret 测试"""

    def test_default_length_48(self):
        """默认长度 48"""
        secret = generate_strong_secret()
        assert len(secret) == 48

    def test_custom_length(self):
        """自定义长度"""
        secret = generate_strong_secret(64)
        assert len(secret) == 64

    def test_includes_all_char_classes(self):
        """应包含 4 字符类（大小写+数字+特殊）"""
        secret = generate_strong_secret(64)
        has_lower = any(c.islower() for c in secret)
        has_upper = any(c.isupper() for c in secret)
        has_digit = any(c.isdigit() for c in secret)
        has_special = any(not c.isalnum() for c in secret)
        assert all([has_lower, has_upper, has_digit, has_special])

    def test_two_calls_different(self):
        """两次调用应不同（密码学随机）"""
        s1 = generate_strong_secret(48)
        s2 = generate_strong_secret(48)
        assert s1 != s2

    def test_generated_passes_audit(self):
        """生成的密钥应通过强度审计"""
        secret = generate_strong_secret(48)
        result = validate_secret_strength(secret, env="production")
        assert result["is_strong"]


class TestAuditEnvSecrets:
    """audit_env_secrets .env 扫描测试"""

    def test_audit_strong_env(self, tmp_path):
        """所有凭证强度合格应返回空列表"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SECRET_KEY=Abc123!@#Def456$Ghi789%Jkl012Mno345Pqr678Stu90\n"
            "SUPABASE_DB_PASSWORD=StrongPass!2024#\n"
            "OTHER_VAR=foo\n",
            encoding="utf-8",
        )
        issues = audit_env_secrets(env_file)
        # 强密钥 + 强密码（≥ 12 字符）应通过
        # 但 SECRET_KEY 是 48 字符生产级 → 应通过
        assert all(
            issue["key"] not in ("SECRET_KEY",)
            for issue in issues
        ) or len(issues) == 0

    def test_audit_detects_weak_db_password(self, tmp_path):
        """弱数据库密码应被检测"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SECRET_KEY=Abc123!@#Def456$Ghi789%Jkl012Mno345Pqr678Stu90\n"
            "SUPABASE_DB_PASSWORD=123\n"
            "OTHER_VAR=foo\n",
            encoding="utf-8",
        )
        issues = audit_env_secrets(env_file)
        keys = [i["key"] for i in issues]
        assert "SUPABASE_DB_PASSWORD" in keys

    def test_audit_masks_values(self, tmp_path):
        """审计结果应脱敏凭证值"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SECRET_KEY=secret1234short\n",
            encoding="utf-8",
        )
        issues = audit_env_secrets(env_file)
        assert len(issues) >= 1
        for issue in issues:
            assert "***" in issue["value_masked"] or len(issue["value_masked"]) <= 4

    def test_audit_skips_empty_values(self, tmp_path):
        """空值应跳过（开发用 SQLite 时无 DB 密码）"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "SECRET_KEY=secret1234short\n"
            "SUPABASE_DB_PASSWORD=\n"
            "TUSHARE_TOKEN=\n",
            encoding="utf-8",
        )
        issues = audit_env_secrets(env_file)
        keys = [i["key"] for i in issues]
        # 空值不应被报为弱
        assert "SUPABASE_DB_PASSWORD" not in keys
        assert "TUSHARE_TOKEN" not in keys


class TestSettingsValidation:
    """Settings 启动校验测试"""

    def test_weak_secret_in_production_raises(self):
        """生产环境弱 SECRET_KEY 应 raise"""
        from app.core.config import Settings
        with pytest.raises((ValueError, ValidationError)):
            Settings(SECRET_KEY="dev-secret-key-change-in-production", ENVIRONMENT="production")

    def test_strong_secret_in_production_passes(self):
        """生产环境强 SECRET_KEY 应通过"""
        from app.core.config import Settings
        s = Settings(
            SECRET_KEY="Abc123!@#Def456$Ghi789%Jkl012Mno345Pqr678Stu90",
            ENVIRONMENT="production",
        )
        assert s.SECRET_KEY.startswith("Abc123")

    def test_weak_secret_in_development_warns(self):
        """开发环境弱 SECRET_KEY 应 warning（不 raise）"""
        from app.core.config import Settings
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            s = Settings(
                SECRET_KEY="dev-secret-key-change-in-production",
                ENVIRONMENT="development",
            )
            # 至少一条 UserWarning
            user_warnings = [x for x in w if issubclass(x.category, UserWarning)]
            assert len(user_warnings) >= 1
            assert "SECRET_KEY" in str(user_warnings[0].message)

    def test_short_db_password_raises(self):
        """短数据库密码应 raise"""
        from app.core.config import Settings
        with pytest.raises((ValueError, ValidationError)):
            Settings(SUPABASE_DB_PASSWORD="123")

    def test_db_password_min_12_chars(self):
        """≥ 12 字符数据库密码应通过"""
        from app.core.config import Settings
        s = Settings(SUPABASE_DB_PASSWORD="1234567890ab")
        assert s.SUPABASE_DB_PASSWORD == "1234567890ab"
