"""
自定义异常类 — 数据源异常分类
用于区分网络错误、限流、数据格式异常、认证失败等不同类型的异常
"""


class DataSourceError(Exception):
    """数据源异常基类"""

    def __init__(self, message: str = "", *, retry_possible: bool = False) -> None:
        super().__init__(message)
        self.retry_possible = retry_possible


class NetworkError(DataSourceError):
    """网络连接/超时异常"""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, retry_possible=True)


class RateLimitError(DataSourceError):
    """API 限流/频率限制异常"""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, retry_possible=False)


class DataFormatError(DataSourceError):
    """数据格式异常（KeyError / ValueError / AttributeError / IndexError）"""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, retry_possible=False)


class AuthError(DataSourceError):
    """认证失败异常（401 / 403 / token 无效）"""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, retry_possible=False)


def _classify_exception(e: Exception) -> DataSourceError:
    """
    将原始异常分类为具体的 DataSourceError 子类。

    分类规则：
    - ConnectionError / TimeoutError / OSError（含 timeout/Connection 关键词）→ NetworkError
    - 异常信息含 429/limit/频率/rate → RateLimitError
    - KeyError / ValueError / AttributeError / IndexError → DataFormatError
    - 异常信息含 401/403/auth/token → AuthError
    - 其他 → DataSourceError（原始异常作为 __cause__）
    """
    msg = str(e).lower()

    # 1. 网络类异常
    if isinstance(e, (ConnectionError, TimeoutError, OSError)):
        return NetworkError(str(e))

    # 2. 限流类异常（检查异常信息中的关键词）
    rate_keywords = ["429", "limit", "频率", "rate"]
    if any(kw in msg for kw in rate_keywords):
        return RateLimitError(str(e))

    # 3. 数据格式异常
    if isinstance(e, (KeyError, ValueError, AttributeError, IndexError)):
        return DataFormatError(str(e))

    # 4. 认证失败异常
    auth_keywords = ["401", "403", "auth", "token"]
    if any(kw in msg for kw in auth_keywords):
        return AuthError(str(e))

    # 5. 其他未分类异常
    classified = DataSourceError(str(e))
    classified.__cause__ = e
    return classified
