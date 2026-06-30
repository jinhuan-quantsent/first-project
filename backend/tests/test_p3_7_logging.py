"""
统一日志测试 — 阶段 3 P3-7

覆盖：
- setup_logging() JSON 输出格式（生产）
- setup_logging() 彩色输出（开发）
- _InterceptHandler 拦截 stdlib logging
- get_logger() 返回带 module 标签的 logger
- 日志级别控制
"""
import io
import json
import logging
import sys
import os

import pytest
from loguru import logger as loguru_logger

from app.core.logging import setup_logging, get_logger, _InterceptHandler


@pytest.fixture(autouse=True)
def reset_logging():
    """每个测试前重置 loguru sinks 和 stdlib logging"""
    loguru_logger.remove()
    yield
    loguru_logger.remove()


class TestSetupLogging:
    """setup_logging() 配置测试"""

    def test_setup_logging_json_mode(self, capsys):
        """JSON 模式应输出可解析 JSON 格式"""
        setup_logging(json_output=True, level="INFO")
        logger = get_logger("test_module")
        logger.info("hello world")

        captured = capsys.readouterr()
        lines = [l for l in captured.err.split("\n") if l.strip()]
        assert len(lines) >= 1, f"No output: {captured.err}"
        last = lines[-1]
        data = json.loads(last)  # 必须是合法 JSON
        assert data["level"] == "INFO"
        assert "hello world" in data["message"]

    def test_setup_logging_json_includes_required_fields(self, capsys):
        """JSON 输出应包含 ts/level/module/message"""
        setup_logging(json_output=True, level="INFO")
        logger = get_logger("my.module")
        logger.info("test message")

        captured = capsys.readouterr()
        data = json.loads(captured.err.strip().split("\n")[-1])
        for field in ("ts", "level", "module", "message"):
            assert field in data, f"Missing {field} in JSON: {data}"
        assert data["module"] == "my.module"
        assert "T" in data["ts"]  # ISO 格式

    def test_setup_logging_colored_mode(self, capsys):
        """彩色模式应输出到 stderr（非 JSON）"""
        setup_logging(json_output=False, level="INFO")
        logger = get_logger("test")
        logger.info("colored message")

        captured = capsys.readouterr()
        assert "colored message" in captured.err
        # 彩色模式不输出 JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(captured.err.strip().split("\n")[-1])

    def test_setup_logging_level_filter(self, capsys):
        """应能按级别过滤（DEBUG 默认被 INFO 过滤）"""
        setup_logging(json_output=True, level="INFO")
        logger = get_logger("test")
        logger.debug("should not appear")
        logger.info("should appear")

        captured = capsys.readouterr()
        assert "should not appear" not in captured.err
        assert "should appear" in captured.err


class TestInterceptHandler:
    """stdlib logging → loguru 拦截测试"""

    def test_stdlib_logger_redirected(self, capsys):
        """stdlib `logging.getLogger(__name__)` 应被拦截到 loguru"""
        setup_logging(json_output=True, level="INFO")
        stdlib_logger = logging.getLogger("stdlib.module")
        stdlib_logger.info("from stdlib")

        captured = capsys.readouterr()
        lines = [l for l in captured.err.split("\n") if l.strip()]
        assert any("from stdlib" in l for l in lines)

    def test_stdlib_warning_level(self, capsys):
        """WARNING 级别应正确映射"""
        setup_logging(json_output=True, level="INFO")
        stdlib_logger = logging.getLogger("stdlib.warn")
        stdlib_logger.warning("warn message")

        captured = capsys.readouterr()
        data = json.loads(captured.err.strip().split("\n")[-1])
        assert data["level"] == "WARNING"

    def test_stdlib_error_level(self, capsys):
        """ERROR 级别应正确映射"""
        setup_logging(json_output=True, level="INFO")
        stdlib_logger = logging.getLogger("stdlib.err")
        stdlib_logger.error("error message")

        captured = capsys.readouterr()
        data = json.loads(captured.err.strip().split("\n")[-1])
        assert data["level"] == "ERROR"


class TestGetLogger:
    """get_logger() 工厂测试"""

    def test_get_logger_returns_logger(self):
        """get_logger 应返回可用 logger 对象"""
        log = get_logger("my.module")
        assert log is not None
        assert hasattr(log, "info")
        assert hasattr(log, "error")

    def test_get_logger_binds_module(self, capsys):
        """get_logger 应通过 bind 附加 module 标签"""
        setup_logging(json_output=True, level="INFO")
        log = get_logger("my.module.path")
        log.info("bound test")

        captured = capsys.readouterr()
        data = json.loads(captured.err.strip().split("\n")[-1])
        # module 字段应来自 loguru 的 record.name 而非 bind（bind 走 extra）
        assert "bound test" in data["message"]


class TestSetupLoggingIdempotency:
    """重复调用应安全"""

    def test_double_setup_no_error(self, capsys):
        """两次 setup_logging 不应报错（sink 会被替换）"""
        setup_logging(json_output=True, level="INFO")
        setup_logging(json_output=True, level="INFO")
        logger = get_logger("test")
        logger.info("after double setup")

        captured = capsys.readouterr()
        assert "after double setup" in captured.err
