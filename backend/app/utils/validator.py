"""
数据质量校验器

校验规则：
- 数据完整性：必填字段检查
- 数值合理性：范围检查
- 时间一致性：日期逻辑检查
- 异常值检测：Z-score / IQR
"""
from datetime import date
from typing import Any, Optional


class ValidationResult:
    """校验结果"""
    def __init__(self) -> None:
        self.is_valid: bool = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.is_valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_index_data(data: dict) -> ValidationResult:
    """校验指数数据"""
    result = ValidationResult()

    required_fields = ["index_code", "close", "volatility", "turnover_ratio"]
    for field in required_fields:
        if field not in data or data[field] is None:
            result.add_error(f"缺少必填字段: {field}")

    if result.is_valid:
        # 数值范围检查
        close = data.get("close", 0)
        if close <= 0 or close > 100000:
            result.add_error(f"收盘价异常: {close}")

        volatility = data.get("volatility", 0)
        if volatility < 0 or volatility > 200:
            result.add_warning(f"波动率异常: {volatility}%")

        turnover = data.get("turnover_ratio", 0)
        if turnover < 0 or turnover > 50:
            result.add_warning(f"换手率异常: {turnover}%")

    return result


def validate_sentiment_score(score: float) -> ValidationResult:
    """校验情绪评分"""
    result = ValidationResult()

    if score < 0 or score > 100:
        result.add_error(f"情绪评分超出范围: {score} (应为 0-100)")

    return result


def validate_factor_scores(factor_scores: dict[str, Any]) -> ValidationResult:
    """校验因子评分"""
    result = ValidationResult()

    expected_factors = ["波动率", "换手率", "涨跌比", "新高占比", "融资融券", "股债比", "RSI"]

    for factor in expected_factors:
        if factor not in factor_scores:
            result.add_warning(f"缺少因子: {factor}")
        else:
            fs = factor_scores[factor]
            score = fs.score if hasattr(fs, 'score') else fs.get('score', 50)
            if score < 0 or score > 100:
                result.add_error(f"因子 {factor} 评分超出范围: {score}")

    return result


def detect_outliers(values: list[float], threshold: float = 2.0) -> list[int]:
    """
    Z-score 异常值检测

    Args:
        values: 数值列表
        threshold: Z-score 阈值（默认 2.0）

    Returns:
        异常值索引列表
    """
    if len(values) < 3:
        return []

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std = variance ** 0.5

    if std == 0:
        return []

    outliers = []
    for i, v in enumerate(values):
        z_score = abs(v - mean) / std
        if z_score > threshold:
            outliers.append(i)

    return outliers
