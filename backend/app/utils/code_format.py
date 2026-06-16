"""
代码格式统一工具模块 V1.0

统一规则：
- 数据库存储 + 后端内部：Tushare 格式（000300.SH / 399006.SZ / 110011.OF）
- 前端传参 + API 响应：Display 格式（SH000300 / SZ399006 / 110011）
- API 边界：入参 to_tushare()，出参 to_display()

格式定义：
- 指数 Tushare 格式：XXXXXX.XX（如 000300.SH, 399006.SZ）
- 指数 Display 格式：XX000000（如 SH000300, SZ399006）
- 基金 Tushare 格式：XXXXXX.OF（如 110011.OF, 510300.SH）
- 基金 Display 格式：6位纯数字（如 110011, 510300）
"""
from __future__ import annotations

import re


# ============================================================
# 指数代码格式转换
# ============================================================

# 支持的指数代码映射（Tushare 格式 → 名称）
INDEX_REGISTRY: dict[str, str] = {
    "000001.SH": "上证综指",
    "000300.SH": "沪深300",
    "000016.SH": "上证50",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
}

# Display 格式 → Tushare 格式 反向映射
_DISPLAY_TO_TUSHARE: dict[str, str] = {}
for ts_code, name in INDEX_REGISTRY.items():
    parts = ts_code.split(".")
    display_code = parts[1] + parts[0]
    _DISPLAY_TO_TUSHARE[display_code] = ts_code


def to_tushare(code: str) -> str:
    """
    任意格式 → Tushare 格式（数据库/内部使用）

    支持输入：
    - SH000300 → 000300.SH
    - 000300.SH → 000300.SH（已是 Tushare 格式，直接返回）
    - 000300 → 000300.SH（6位纯数字指数代码，默认 .SH）
    - 110011 → 110011.OF（基金代码）
    - 110011.OF → 110011.OF（已是 Tushare 格式）

    规则：
    1. 已经是 XXXXXX.XX 格式 → 直接返回
    2. SH/SZ 开头的 display 格式 → 拆分重组
    3. 6位纯数字 → 根据代码前缀判断交易所
    """
    if not code:
        return code

    code = code.strip()

    # 已经是 Tushare 格式（XXXXXX.XX）
    if "." in code:
        return code

    # Display 格式：SH000300 / SZ399006
    if code.startswith("SH") and len(code) == 8:
        return code[2:] + ".SH"
    if code.startswith("SZ") and len(code) == 8:
        return code[2:] + ".SZ"

    # 6位纯数字
    if len(code) == 6 and code.isdigit():
        return _six_digit_to_tushare(code)

    # 未知格式，原样返回
    return code


def to_display(code: str) -> str:
    """
    Tushare 格式 → Display 格式（前端/API 响应使用）

    支持输入：
    - 000300.SH → SH000300
    - 399006.SZ → SZ399006
    - 110011.OF → 110011（基金代码，6位纯数字）
    - SH000300 → SH000300（已是 Display 格式，直接返回）
    """
    if not code:
        return code

    code = code.strip()

    # 已经是 Display 格式（SH/SZ 开头，无点号）
    if "." not in code and (code.startswith("SH") or code.startswith("SZ")):
        return code

    # Tushare 格式
    if "." in code:
        parts = code.split(".")
        base = parts[0]
        suffix = parts[1]

        if suffix == "OF":
            # 场外基金 → 6位纯数字
            return base
        elif suffix in ("SH", "SZ"):
            # 指数 → XX + XXXXXX
            return suffix + base
        else:
            # 其他后缀（如 BJ 北交所）→ 同上
            return suffix + base

    # 6位纯数字（基金代码）→ 直接返回
    return code


def _six_digit_to_tushare(code: str) -> str:
    """
    6位纯数字 → Tushare 格式

    规则：
    - 000xxx, 5xxxxx → .SH（上交所指数/ETF）
    - 399xxx, 15xxxx, 16xxxx, 18xxxx → .SZ（深交所指数/ETF）
    - 其他 → .OF（场外基金）
    """
    # 上交所指数
    if code.startswith("000") and len(code) == 6:
        return f"{code}.SH"
    # 上交所 ETF/基金（51/52/56/58/50 开头）
    if code.startswith(("51", "52", "56", "58", "50")):
        return f"{code}.SH"
    # 深交所指数
    if code.startswith("399"):
        return f"{code}.SZ"
    # 深交所 ETF/基金（15/16/18 开头）
    if code.startswith(("15", "16", "18")):
        return f"{code}.SZ"
    # 默认场外基金
    return f"{code}.OF"


# ============================================================
# 便利函数
# ============================================================

def is_index_code(code: str) -> bool:
    """判断是否为指数代码（非基金代码）"""
    ts_code = to_tushare(code)
    return ts_code in INDEX_REGISTRY or (
        "." in ts_code and ts_code.split(".")[1] in ("SH", "SZ")
        and ts_code.split(".")[0].startswith(("000", "399"))
    )


def is_fund_code(code: str) -> bool:
    """判断是否为基金代码"""
    ts_code = to_tushare(code)
    return ts_code.endswith(".OF") or (
        "." in ts_code and ts_code.split(".")[1] in ("SH", "SZ")
        and not ts_code.split(".")[0].startswith(("000", "399"))
    )


def get_index_name(code: str) -> str:
    """获取指数中文名称"""
    ts_code = to_tushare(code)
    return INDEX_REGISTRY.get(ts_code, "")


def batch_to_tushare(codes: list[str]) -> list[str]:
    """批量转换为 Tushare 格式"""
    return [to_tushare(c) for c in codes]


def batch_to_display(codes: list[str]) -> list[str]:
    """批量转换为 Display 格式"""
    return [to_display(c) for c in codes]


# 默认指数代码（Display 格式，前端兼容）
DEFAULT_INDEX_CODES_DISPLAY = ["SH000001", "SH000300", "SZ399001", "SZ399006"]

# 默认指数代码（Tushare 格式，内部使用）
DEFAULT_INDEX_CODES_TUSHARE = batch_to_tushare(DEFAULT_INDEX_CODES_DISPLAY)

# 指数代码 → 权重映射（Display 格式）
INDEX_WEIGHT_MAP_DISPLAY: dict[str, float] = {
    "SH000001": 0.20,
    "SH000300": 0.30,
    "SZ399001": 0.20,
    "SZ399006": 0.30,
}
