"""
P1-4 复检：AKShare 异常分类
验证 _classify_exception 分类逻辑和各异常类的 retry_possible 属性
"""
import pytest

from app.utils.exceptions import (
    DataSourceError,
    NetworkError,
    RateLimitError,
    DataFormatError,
    AuthError,
    _classify_exception,
)


class TestClassifyException:
    """_classify_exception 分类测试"""

    def test_connection_error_to_network_error(self):
        """ConnectionError → NetworkError（retry_possible=True）"""
        e = ConnectionError("connection refused")
        result = _classify_exception(e)
        assert isinstance(result, NetworkError)
        assert result.retry_possible is True

    def test_timeout_error_to_network_error(self):
        """TimeoutError → NetworkError（retry_possible=True）"""
        e = TimeoutError("request timed out")
        result = _classify_exception(e)
        assert isinstance(result, NetworkError)
        assert result.retry_possible is True

    def test_os_error_to_network_error(self):
        """OSError → NetworkError（retry_possible=True）"""
        e = OSError("network unreachable")
        result = _classify_exception(e)
        assert isinstance(result, NetworkError)
        assert result.retry_possible is True

    def test_rate_limit_429(self):
        """异常信息含 429 → RateLimitError"""
        e = Exception("429 Too Many Requests")
        result = _classify_exception(e)
        assert isinstance(result, RateLimitError)
        assert result.retry_possible is False

    def test_rate_limit_keyword_limit(self):
        """异常信息含 limit → RateLimitError"""
        e = Exception("API rate limit exceeded")
        result = _classify_exception(e)
        assert isinstance(result, RateLimitError)

    def test_rate_limit_keyword_rate(self):
        """异常信息含 rate → RateLimitError"""
        e = Exception("rate exceeded")
        result = _classify_exception(e)
        assert isinstance(result, RateLimitError)

    def test_key_error_to_data_format_error(self):
        """KeyError → DataFormatError"""
        e = KeyError("missing_key")
        result = _classify_exception(e)
        assert isinstance(result, DataFormatError)
        assert result.retry_possible is False

    def test_value_error_to_data_format_error(self):
        """ValueError → DataFormatError"""
        e = ValueError("invalid value")
        result = _classify_exception(e)
        assert isinstance(result, DataFormatError)

    def test_attribute_error_to_data_format_error(self):
        """AttributeError → DataFormatError"""
        e = AttributeError("no attribute 'close'")
        result = _classify_exception(e)
        assert isinstance(result, DataFormatError)

    def test_index_error_to_data_format_error(self):
        """IndexError → DataFormatError"""
        e = IndexError("list index out of range")
        result = _classify_exception(e)
        assert isinstance(result, DataFormatError)

    def test_auth_401(self):
        """异常信息含 401 → AuthError"""
        e = Exception("401 Unauthorized")
        result = _classify_exception(e)
        assert isinstance(result, AuthError)
        assert result.retry_possible is False

    def test_auth_403(self):
        """异常信息含 403 → AuthError"""
        e = Exception("403 Forbidden")
        result = _classify_exception(e)
        assert isinstance(result, AuthError)

    def test_auth_token(self):
        """异常信息含 token → AuthError"""
        e = Exception("Invalid token")
        result = _classify_exception(e)
        assert isinstance(result, AuthError)

    def test_unknown_runtime_error_to_data_source_error(self):
        """RuntimeError（未知异常）→ DataSourceError，原始异常作为 __cause__"""
        e = RuntimeError("unknown error")
        result = _classify_exception(e)
        assert isinstance(result, DataSourceError)
        assert not isinstance(result, NetworkError)
        assert not isinstance(result, RateLimitError)
        assert not isinstance(result, DataFormatError)
        assert not isinstance(result, AuthError)
        assert result.__cause__ is e

    def test_unknown_exception_preserves_message(self):
        """分类后的异常保留原始信息"""
        e = RuntimeError("custom error message")
        result = _classify_exception(e)
        assert "custom error message" in str(result)


class TestExceptionRetryPossible:
    """各异常类的 retry_possible 属性"""

    def test_data_source_error_default_retry_false(self):
        """DataSourceError 默认 retry_possible=False"""
        e = DataSourceError("base error")
        assert e.retry_possible is False

    def test_data_source_error_explicit_retry_true(self):
        """DataSourceError 可显式设置 retry_possible=True"""
        e = DataSourceError("base error", retry_possible=True)
        assert e.retry_possible is True

    def test_network_error_retry_true(self):
        """NetworkError.retry_possible=True"""
        e = NetworkError("conn failed")
        assert e.retry_possible is True

    def test_rate_limit_error_retry_false(self):
        """RateLimitError.retry_possible=False"""
        e = RateLimitError("too many requests")
        assert e.retry_possible is False

    def test_data_format_error_retry_false(self):
        """DataFormatError.retry_possible=False"""
        e = DataFormatError("bad format")
        assert e.retry_possible is False

    def test_auth_error_retry_false(self):
        """AuthError.retry_possible=False"""
        e = AuthError("unauthorized")
        assert e.retry_possible is False


class TestExceptionInheritance:
    """异常继承关系"""

    def test_all_subclass_data_source_error(self):
        """所有自定义异常都是 DataSourceError 的子类"""
        assert issubclass(NetworkError, DataSourceError)
        assert issubclass(RateLimitError, DataSourceError)
        assert issubclass(DataFormatError, DataSourceError)
        assert issubclass(AuthError, DataSourceError)

    def test_all_inherit_exception(self):
        """所有自定义异常都是 Exception 的子类"""
        assert issubclass(DataSourceError, Exception)
        assert issubclass(NetworkError, Exception)
