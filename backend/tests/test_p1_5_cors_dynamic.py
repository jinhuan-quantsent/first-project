"""
P1-5 复检：CORS 动态配置
验证 effective_cors_origins 在不同环境下的行为
"""
import pytest
from unittest.mock import patch

from app.core.config import Settings


class TestCORSDefault:
    """默认 CORS 配置测试"""

    def test_default_cors_origins_contains_localhost(self):
        """默认 CORS_ORIGINS 包含 localhost 域名"""
        s = Settings()
        assert any("localhost" in origin for origin in s.CORS_ORIGINS)
        assert "http://localhost:5173" in s.CORS_ORIGINS

    def test_default_cors_origins_list(self):
        """默认 CORS_ORIGINS 包含预期的域名"""
        s = Settings()
        expected = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "https://fsa.vercel.app",
            "https://fundsent.top",
        ]
        assert s.CORS_ORIGINS == expected


class TestEffectiveCORSNonProduction:
    """非生产环境下 effective_cors_origins"""

    def test_non_production_returns_cors_origins(self):
        """非生产环境下 effective_cors_origins 返回与 CORS_ORIGINS 相同的列表"""
        s = Settings(ENVIRONMENT="development")
        result = s.effective_cors_origins
        assert result == s.CORS_ORIGINS

    def test_non_production_no_supabase_extraction(self):
        """非生产环境下即使有 SUPABASE_URL 也不提取域名"""
        s = Settings(
            ENVIRONMENT="development",
            SUPABASE_URL="https://abc123.supabase.co",
        )
        result = s.effective_cors_origins
        assert result == s.CORS_ORIGINS
        assert "https://abc123.supabase.co" not in result


class TestEffectiveCORSProduction:
    """生产环境下 effective_cors_origins"""

    def test_production_extracts_supabase_domain(self):
        """生产环境 + SUPABASE_URL 设置时自动提取域名"""
        s = Settings(
            ENVIRONMENT="production",
            SUPABASE_URL="https://myproject.supabase.co",
        )
        result = s.effective_cors_origins
        # 应包含原有 CORS_ORIGINS + 自动提取的域名
        assert "https://myproject.supabase.co" in result
        # 原有 localhost 域名仍在
        assert "http://localhost:5173" in result

    def test_production_no_supabase_url(self):
        """生产环境但无 SUPABASE_URL 时不额外添加"""
        s = Settings(
            ENVIRONMENT="production",
            SUPABASE_URL="",
        )
        result = s.effective_cors_origins
        assert result == s.CORS_ORIGINS

    def test_production_no_duplicate(self):
        """生产环境下不会重复添加已存在的域名"""
        s = Settings(
            ENVIRONMENT="production",
            SUPABASE_URL="https://fsa.vercel.app",  # 已在默认列表中
        )
        result = s.effective_cors_origins
        # 不应重复
        count = result.count("https://fsa.vercel.app")
        assert count == 1


class TestCORSEnvParsing:
    """CORS 环境变量（逗号分隔）解析"""

    def test_cors_origins_from_env(self):
        """CORS_ORIGINS 环境变量能正确解析"""
        s = Settings(CORS_ORIGINS=["http://custom1.com", "http://custom2.com"])
        assert s.CORS_ORIGINS == ["http://custom1.com", "http://custom2.com"]

    def test_cors_origins_single_value(self):
        """CORS_ORIGINS 单个值"""
        s = Settings(CORS_ORIGINS=["http://single.com"])
        assert s.CORS_ORIGINS == ["http://single.com"]
        assert s.effective_cors_origins == ["http://single.com"]
