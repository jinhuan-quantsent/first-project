"""
统一日志配置 — Loguru + JSON

设计目标：
1. 拦截 stdlib `logging` → loguru（无需修改业务代码 `logger = logging.getLogger(__name__)`）
2. 生产环境输出 JSON 格式（含 ts/level/module/message/extra）
3. 开发环境输出彩色易读格式
4. 单点配置 `setup_logging()`，在 main.py 启动时调用

用法：
    # main.py
    from app.core.logging import setup_logging
    setup_logging(json_output=True, level="INFO")
"""
import logging
import sys
import json
from typing import Any

from loguru import logger as _loguru_logger


def _json_sink(message: Any) -> None:
    """JSON 格式输出 sink"""
    record = message.record
    # 优先使用 extra.module（get_logger 绑定），否则用 loguru 内部 name
    module = record["extra"].get("module") or record["name"]
    payload = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "module": module,
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }
    # 合并其他 extra 字段（业务自定义数据，排除已用 module）
    other_extra = {k: v for k, v in record["extra"].items() if k != "module"}
    if other_extra:
        payload["extra"] = other_extra
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)


class _InterceptHandler(logging.Handler):
    """
    拦截 stdlib logging 输出 → loguru

    业务代码使用 `logger = logging.getLogger(__name__)` 即可，
    实际输出会经过 loguru，享受统一格式 + 级别控制。
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        _loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging(
    json_output: bool = False,
    level: str = "INFO",
) -> None:
    """
    配置全局日志系统

    参数：
        json_output: True=生产 JSON 格式；False=开发彩色格式
        level: 日志级别（DEBUG/INFO/WARNING/ERROR）
    """
    # 1. 移除 loguru 默认 sink
    _loguru_logger.remove()

    # 2. 添加新 sink
    if json_output:
        _loguru_logger.add(
            _json_sink,
            level=level,
            format="{message}",  # sink 内部已用 JSON，无需额外格式化
            backtrace=True,
            diagnose=False,
        )
    else:
        _loguru_logger.add(
            sys.stderr,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
            backtrace=True,
            diagnose=False,
        )

    # 3. 拦截 stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    # 4. 拦截 uvicorn / fastapi 等第三方 logger
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers = [_InterceptHandler()]
        lib_logger.propagate = False


def get_logger(name: str):
    """
    获取业务 logger（推荐用 loguru 风格）

    用法：
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("...")
    """
    return _loguru_logger.bind(module=name)


# 导出底层 loguru logger（高级用法）
logger = _loguru_logger
